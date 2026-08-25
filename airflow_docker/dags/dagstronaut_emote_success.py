"""DAGstronaut Demo 2: a successful task triggers the happy emote."""

from datetime import datetime
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator


ROBOT_BRIDGE_URL = os.getenv(
    "ROBOT_BRIDGE_URL", "http://host.docker.internal:8765"
).rstrip("/")
EMOTE_DURATION_SECONDS = int(os.getenv("DAGSTRONAUT_EMOTE_DURATION", "5"))


def celebrate_success(context):
    """Run the physical happy emote after the task succeeds."""
    request = Request(
        f"{ROBOT_BRIDGE_URL}/happy?duration={EMOTE_DURATION_SECONDS}",
        method="POST",
    )
    try:
        with urlopen(request, timeout=50) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Happy emote failed ({error.code}): {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Robot bridge is offline at {ROBOT_BRIDGE_URL}") from error
    print(f"DAGstronaut celebrated successful task: {result}")


def complete_demo_task():
    print("Demo task completed: DAGstronaut should celebrate")


with DAG(
    dag_id="dagstronaut_emote_success",
    description="One successful task triggers DAGstronaut's happy emote",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["dagstronaut", "robot-buddy", "emote", "success"],
) as dag:
    PythonOperator(
        task_id="complete_demo_task",
        python_callable=complete_demo_task,
        on_success_callback=celebrate_success,
    )
