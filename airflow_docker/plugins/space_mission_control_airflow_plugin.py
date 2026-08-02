"""Airflow 3 plugin for Space Mission Control and its telemetry API."""

from pathlib import Path
from datetime import datetime
import hashlib
import json
import mimetypes
import os
import shlex
import shutil
import subprocess
import threading
import time

from airflow.dag_processing.dagbag import DagBag
from airflow.models import DagModel, DagRun, TaskInstance
from airflow.models.hitl import HITLDetail
from airflow.plugins_manager import AirflowPlugin
from airflow.utils.session import create_session
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


MISSION_CONTROL_DIST = Path("/opt/airflow/widgets/space-mission-control/dist")
ROCKET_TYPES = ("heavy", "shuttle", "courier")
mimetypes.add_type("application/javascript", ".cjs")
mission_control_app = FastAPI(title="Space Mission Control API")
_cpu_lock = threading.Lock()
_cpu_sample = None
_task_test_lock = threading.Lock()


class TaskTestRequest(BaseModel):
    """Validated inputs accepted by the Rocket Test Bench."""

    dag_id: str = Field(min_length=1, max_length=250)
    task_id: str = Field(min_length=1, max_length=250)
    logical_date: str = Field(min_length=1, max_length=64)
    task_params: dict | None = None


def _iso(value):
    return value.isoformat() if value else None


def _read_cpu_times():
    with open("/proc/stat", encoding="utf-8") as stat_file:
        values = [int(value) for value in stat_file.readline().split()[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def _read_memory():
    values = {}
    with open("/proc/meminfo", encoding="utf-8") as meminfo:
        for line in meminfo:
            name, value = line.split(":", 1)
            values[name] = int(value.strip().split()[0]) * 1024
    total = values["MemTotal"]
    available = values.get("MemAvailable", values.get("MemFree", 0))
    return total, total - available


@mission_control_app.get("/resources")
def system_resources():
    """Return live host/container resource readings for the command cockpit."""
    global _cpu_sample
    total_memory, used_memory = _read_memory()
    disk = shutil.disk_usage("/opt/airflow")
    cpu_total, cpu_idle = _read_cpu_times()
    with _cpu_lock:
        previous = _cpu_sample
        _cpu_sample = (cpu_total, cpu_idle)
    if previous and cpu_total > previous[0]:
        cpu_percent = 100 * (1 - (cpu_idle - previous[1]) / (cpu_total - previous[0]))
    else:
        load = os.getloadavg()[0]
        cpu_percent = 100 * load / max(os.cpu_count() or 1, 1)
    return {
        "cpu_percent": round(max(0, min(cpu_percent, 100)), 1),
        "memory_percent": round(100 * used_memory / total_memory, 1),
        "memory_used_bytes": used_memory,
        "memory_total_bytes": total_memory,
        "disk_percent": round(100 * disk.used / disk.total, 1),
        "disk_used_bytes": disk.used,
        "disk_total_bytes": disk.total,
        "load_1m": round(os.getloadavg()[0], 2),
        "cpu_count": os.cpu_count() or 1,
        "timestamp": time.time(),
    }


@mission_control_app.get("/dags")
def mission_dags():
    """Return current DAG missions, including paused and pending-HITL DAGs."""
    with create_session() as session:
        models = session.query(DagModel).filter(DagModel.is_stale.is_(False)).all()
        runs = session.query(DagRun).order_by(DagRun.logical_date.desc()).limit(1000).all()
        pending_hitl_dag_ids = {
            dag_id
            for (dag_id,) in (
                session.query(TaskInstance.dag_id)
                .join(HITLDetail, HITLDetail.ti_id == TaskInstance.id)
                .filter(HITLDetail.responded_at.is_(None))
                .distinct()
                .all()
            )
        }
        latest = {}
        for run in runs:
            latest.setdefault(run.dag_id, run)

        dags = []
        for model in models:
            run = latest.get(model.dag_id)
            tags = sorted(tag.name for tag in model.tags)
            configured_rocket = next(
                (
                    tag.name.split(":", 1)[1]
                    for tag in model.tags
                    if tag.name.startswith("rocket:")
                    and tag.name.split(":", 1)[1] in ROCKET_TYPES
                ),
                None,
            )
            stable_index = int(
                hashlib.sha256(model.dag_id.encode("utf-8")).hexdigest()[:8], 16
            ) % len(ROCKET_TYPES)
            raw_state = str(run.state).lower() if run and run.state else "scheduled"
            if model.is_paused:
                state = "paused"
            elif model.dag_id in pending_hitl_dag_ids:
                state = "hitl"
            else:
                state = raw_state if raw_state in {"running", "queued", "success", "failed"} else "scheduled"
            dags.append(
                {
                    "dag_id": model.dag_id,
                    "tags": tags,
                    "vehicle_type": configured_rocket or ROCKET_TYPES[stable_index],
                    "state": state,
                    "run_id": run.run_id if run else None,
                    "start_time": _iso(run.start_date) if run else None,
                    "updated_at": _iso(run.end_date or run.start_date) if run else None,
                    "next_run": _iso(model.next_dagrun),
                }
            )
    return {"dags": dags}


@mission_control_app.get("/dags/{dag_id}/details")
def dag_mission_details(dag_id: str):
    """Return the latest run and real task graph for the mission drawer."""
    with create_session() as session:
        run = (
            session.query(DagRun)
            .filter(DagRun.dag_id == dag_id)
            .order_by(DagRun.logical_date.desc())
            .first()
        )
        instances = (
            session.query(TaskInstance)
            .filter(TaskInstance.dag_id == dag_id)
            .filter(TaskInstance.run_id == run.run_id)
            .all()
            if run
            else []
        )

    instance_by_task = {}
    for instance in instances:
        current = instance_by_task.get(instance.task_id)
        if current is None or instance.map_index > current.map_index:
            instance_by_task[instance.task_id] = instance

    dag = DagBag(safe_mode=True).get_dag(dag_id)
    tasks = []
    if dag:
        for task in dag.tasks:
            instance = instance_by_task.get(task.task_id)
            tasks.append(
                {
                    "task_id": task.task_id,
                    "operator": task.task_type,
                    "state": str(instance.state).lower() if instance and instance.state else "none",
                    "try_number": instance.try_number if instance else 0,
                    "start_time": _iso(instance.start_date) if instance else None,
                    "end_time": _iso(instance.end_date) if instance else None,
                    "upstream": sorted(task.upstream_task_ids),
                    "downstream": sorted(task.downstream_task_ids),
                }
            )
    else:
        for instance in instances:
            tasks.append(
                {
                    "task_id": instance.task_id,
                    "operator": instance.operator or "Task",
                    "state": str(instance.state).lower() if instance.state else "none",
                    "try_number": instance.try_number,
                    "start_time": _iso(instance.start_date),
                    "end_time": _iso(instance.end_date),
                    "upstream": [],
                    "downstream": [],
                }
            )
    return {
        "dag_id": dag_id,
        "run_id": run.run_id if run else None,
        "run_state": str(run.state).lower() if run and run.state else "scheduled",
        "start_time": _iso(run.start_date) if run else None,
        "end_time": _iso(run.end_date) if run else None,
        "tasks": tasks,
    }


@mission_control_app.post("/task-test")
def run_task_test(request: TaskTestRequest):
    """Run one known Airflow task with ``airflow tasks test`` and return its output."""
    dag = DagBag(safe_mode=True).get_dag(request.dag_id)
    if dag is None:
        raise HTTPException(status_code=404, detail="DAG was not found")
    if request.task_id not in dag.task_ids:
        raise HTTPException(status_code=404, detail="Task was not found in this DAG")
    try:
        logical_date = datetime.fromisoformat(request.logical_date.replace("Z", "+00:00"))
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Logical date must be ISO 8601") from error

    command = [
        "airflow",
        "tasks",
        "test",
        request.dag_id,
        request.task_id,
        logical_date.isoformat(),
    ]
    if request.task_params is not None:
        command.extend(["--task-params", json.dumps(request.task_params, separators=(",", ":"))])

    started = time.monotonic()
    try:
        # Serialize bench runs so the API server cannot be used to create an
        # unbounded number of local task processes.
        with _task_test_lock:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                timeout=300,
            )
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        truncated = len(output) > 200_000
        if truncated:
            output = output[-200_000:]
        return {
            "command": shlex.join(command),
            "exit_code": completed.returncode,
            "duration_seconds": round(time.monotonic() - started, 2),
            "output": output,
            "truncated": truncated,
        }
    except subprocess.TimeoutExpired as error:
        output = "\n".join(
            value.decode(errors="replace") if isinstance(value, bytes) else value or ""
            for value in (error.stdout, error.stderr)
        ).strip()
        raise HTTPException(
            status_code=504,
            detail={"message": "Task test exceeded the 5 minute limit", "output": output[-200_000:]},
        ) from error
    except OSError as error:
        raise HTTPException(status_code=500, detail=f"Could not start Airflow CLI: {error}") from error


mission_control_app.mount(
    "/assets",
    StaticFiles(directory=MISSION_CONTROL_DIST, html=True),
    name="mission_control_assets",
)


class SpaceMissionControlAirflowPlugin(AirflowPlugin):
    name = "space_mission_control"
    fastapi_apps = [
        {
            "app": mission_control_app,
            "url_prefix": "/mission-control-api",
            "name": "Space Mission Control API",
        }
    ]
    react_apps = [
        {
            "name": "Space Mission Control",
            "bundle_url": "/mission-control-api/assets/mission-control-v1.umd.cjs?renderer=react-dom-v11&feature=five-inch-display-v2",
            "destination": "nav",
            "url_route": "space-mission-control",
            "category": "browse",
            "nav_top_level": True,
        }
    ]
