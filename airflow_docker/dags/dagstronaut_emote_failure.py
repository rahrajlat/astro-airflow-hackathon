"""DAGstronaut Demo 2: a failed task triggers the distress emote."""

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


def signal_failure(context):
    """Run the physical sad emote after the task fails."""
    request = Request(
        f"{ROBOT_BRIDGE_URL}/sad?duration={EMOTE_DURATION_SECONDS}",
        method="POST",
    )
    try:
        with urlopen(request, timeout=50) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Sad emote failed ({error.code}): {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Robot bridge is offline at {ROBOT_BRIDGE_URL}") from error
    print(f"DAGstronaut signalled task failure: {result}")


def fail_demo_task():
    raise RuntimeError(
        "Intentional Demo 2 failure: DAGstronaut should signal distress"
    )


with DAG(
    dag_id="dagstronaut_emote_failure",
    description="One failed task triggers DAGstronaut's sad emote",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["dagstronaut", "robot-buddy", "emote", "failure"],
) as dag:
    PythonOperator(
        task_id="fail_demo_task",
        python_callable=fail_demo_task,
        on_failure_callback=signal_failure,
        retries=0,
    )
