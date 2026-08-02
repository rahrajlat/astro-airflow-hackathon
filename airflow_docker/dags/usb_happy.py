"""Trigger the USB desk toy's happy emotion from Airflow."""

from datetime import datetime
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator


ROBOT_BRIDGE_URL = os.getenv(
    "ROBOT_BRIDGE_URL", "http://rasberry.local:8765"
).rstrip("/")


def send_happy_command():
    request = Request(f"{ROBOT_BRIDGE_URL}/happy", method="POST")
    try:
        with urlopen(request, timeout=50) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"USB bridge failed ({error.code}): {detail}") from error
    except URLError as error:
        raise RuntimeError(
            "Cannot reach the robot bridge on the Raspberry Pi at "
            f"{ROBOT_BRIDGE_URL}."
        ) from error

    print(result.get("stdout") or "USB happy command completed")
    if result.get("stderr"):
        print(result["stderr"])
    return result


with DAG(
    dag_id="usb_happy",
    description="Run the happy emotion through the Raspberry Pi robot bridge",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["usb", "desk-toy", "hitl"],
) as dag:
    happy = PythonOperator(
        task_id="happy",
        python_callable=send_happy_command,
        retries=0,
    )
