"""Ask a human for approval after nudging the USB desk toy."""

from datetime import datetime, timedelta
import json
import os
import time
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from airflow import DAG
from airflow.providers.standard.operators.hitl import ApprovalOperator
from airflow.providers.standard.operators.python import PythonOperator


ROBOT_BRIDGE_URL = os.getenv(
    "ROBOT_BRIDGE_URL", "http://rasberry.local:8765"
).rstrip("/")
AIRFLOW_SERVER_URL = "http://airflow-apiserver:8080"
AIRFLOW_API_URL = f"{AIRFLOW_SERVER_URL}/api/v2"


def send_usb_command(command):
    request = Request(f"{ROBOT_BRIDGE_URL}/{command}", method="POST")
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

    print(result.get("stdout") or f"USB {command} command completed")
    if result.get("stderr"):
        print(result["stderr"])
    return result


def approve_hitl_from_clap(dag_run_id):
    result = send_usb_command("nudge")
    if "OK APPROVED" not in result.get("stdout", ""):
        raise RuntimeError("The toy did not detect a clap before the approval timeout")

    username = os.getenv("AIRFLOW_API_USERNAME", "airflow")
    password = os.getenv("AIRFLOW_API_PASSWORD", "airflow")
    token_request = Request(
        f"{AIRFLOW_SERVER_URL}/auth/token",
        data=json.dumps({"username": username, "password": password}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(token_request, timeout=10) as response:
            access_token = json.loads(response.read().decode("utf-8"))["access_token"]
    except (HTTPError, URLError, KeyError) as error:
        raise RuntimeError("Could not authenticate with the Airflow API") from error

    encoded_run_id = quote(dag_run_id, safe="")
    url = (
        f"{AIRFLOW_API_URL}/dags/usb_hitl_approval/dagRuns/{encoded_run_id}"
        "/taskInstances/wait_for_approval/-1/hitlDetails"
    )
    body = json.dumps(
        {"chosen_options": ["Approve"], "params_input": {}}
    ).encode("utf-8")

    # The HITL task starts in parallel. Give it time to enter awaiting_input.
    for attempt in range(15):
        request = Request(
            url,
            data=body,
            method="PATCH",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                approval = json.loads(response.read().decode("utf-8"))
                print("Clap submitted as Airflow HITL approval")
                return approval
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code in (404, 409) and attempt < 14:
                time.sleep(2)
                continue
            raise RuntimeError(
                f"Could not approve the Airflow HITL task ({error.code}): {detail}"
            ) from error

    raise RuntimeError("Airflow HITL task did not become ready for approval")


with DAG(
    dag_id="usb_hitl_approval",
    description="Nudge the operator, wait for HITL approval, then acknowledge it",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["usb", "desk-toy", "hitl", "approval"],
) as dag:
    nudge_operator = PythonOperator(
        task_id="nudge_operator",
        python_callable=approve_hitl_from_clap,
        op_kwargs={"dag_run_id": "{{ run_id }}"},
        retries=0,
    )

    wait_for_approval = ApprovalOperator(
        task_id="wait_for_approval",
        subject="Airflow task needs your approval",
        body=(
            "The desk toy has nudged you because this workflow requires a human "
            "decision. Select **Approve** to continue or **Reject** to stop."
        ),
        defaults="Reject",
        response_timeout=timedelta(minutes=1),
    )

    approval_acknowledged = PythonOperator(
        task_id="approval_acknowledged",
        python_callable=send_usb_command,
        op_kwargs={"command": "happy"},
        retries=0,
    )

    [nudge_operator, wait_for_approval] >> approval_acknowledged
