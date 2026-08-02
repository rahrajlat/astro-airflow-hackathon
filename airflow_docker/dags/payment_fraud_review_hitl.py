"""Real-life payment fraud review simulation with physical HITL approval."""

from datetime import datetime, timedelta
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from airflow import DAG
from airflow.providers.standard.operators.hitl import ApprovalOperator
from airflow.providers.standard.operators.python import PythonOperator


DAG_ID = "payment_fraud_review_hitl"
HITL_TASK_ID = "manager_approval"
ROBOT_BRIDGE_URL = os.getenv(
    "ROBOT_BRIDGE_URL", "http://rasberry.local:8765"
).rstrip("/")
AIRFLOW_SERVER_URL = "http://airflow-apiserver:8080"


def receive_payment_batch():
    print("Receiving the latest payment batch from the checkout platform...")
    time.sleep(3)
    batch = {"batch_id": "PAY-2026-0801", "transactions": 1248}
    print(f"Received {batch['transactions']} transactions in {batch['batch_id']}")
    return batch


def run_fraud_checks():
    print("Running velocity, location, device, and account-risk checks...")
    time.sleep(5)
    case = {
        "case_id": "FR-9482",
        "customer": "Northwind Trading",
        "amount": "GBP 18,750.00",
        "risk_score": 87,
        "reason": "New device and unusually large international payment",
    }
    print(f"Flagged {case['case_id']} with risk score {case['risk_score']}/100")
    return case


def prepare_review_case():
    print("Collecting customer history and supporting transaction evidence...")
    time.sleep(3)
    print("Manual-review package is ready for the payments manager")


def send_usb_command(command, duration=None):
    url = f"{ROBOT_BRIDGE_URL}/{command}"
    if duration is not None:
        url += f"?duration={duration}"
    request = Request(url, method="POST")
    try:
        with urlopen(request, timeout=50) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"USB bridge failed ({error.code}): {detail}") from error
    except URLError as error:
        raise RuntimeError(
            "Cannot reach the robot bridge on the Raspberry Pi at "
            f"{ROBOT_BRIDGE_URL}."
        ) from error


def get_airflow_access_token():
    username = os.getenv("AIRFLOW_API_USERNAME", "airflow")
    password = os.getenv("AIRFLOW_API_PASSWORD", "airflow")
    request = Request(
        f"{AIRFLOW_SERVER_URL}/auth/token",
        data=json.dumps({"username": username, "password": password}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))["access_token"]
    except (HTTPError, URLError, KeyError) as error:
        raise RuntimeError("Could not authenticate with the Airflow API") from error


def submit_hitl_approval(dag_run_id):
    token = get_airflow_access_token()
    encoded_run_id = quote(dag_run_id, safe="")
    url = (
        f"{AIRFLOW_SERVER_URL}/api/v2/dags/{DAG_ID}/dagRuns/{encoded_run_id}"
        f"/taskInstances/{HITL_TASK_ID}/-1/hitlDetails"
    )
    body = json.dumps(
        {"chosen_options": ["Approve"], "params_input": {}}
    ).encode("utf-8")

    for attempt in range(15):
        request = Request(
            url,
            data=body,
            method="PATCH",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                print("Clap accepted as the manager's Airflow HITL approval")
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code in (404, 409) and attempt < 14:
                time.sleep(2)
                continue
            raise RuntimeError(
                f"Could not approve the HITL task ({error.code}): {detail}"
            ) from error

    raise RuntimeError("The HITL request did not become ready for approval")


def request_physical_approval(dag_run_id):
    print("Sending the desk toy to request the manager's attention...")
    result = send_usb_command("nudge")
    print(result.get("stdout") or "Nudge completed")
    if "OK APPROVED" in result.get("stdout", ""):
        return submit_hitl_approval(dag_run_id)
    print("No clap detected; approval remains available in the Airflow UI")
    return {"clap_detected": False}


def celebrate_dag_success(context):
    print("DAG succeeded; running the happy emote for 10 seconds...")
    result = send_usb_command("happy", duration=10)
    print(result.get("stdout") or "Ten-second happy emote completed")


def release_payment():
    print("Approval received. Releasing the held payment...")
    time.sleep(4)
    print("Payment GBP 18,750.00 released successfully")


def update_financial_ledger():
    print("Posting the approved payment to the financial ledger...")
    time.sleep(3)
    print("Ledger and audit trail updated")


def notify_customer():
    print("Preparing payment confirmation for Northwind Trading...")
    time.sleep(2)
    print("Customer notified: payment approved and processed")


with DAG(
    dag_id=DAG_ID,
    description="Simulate fraud review with Airflow HITL and clap approval",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["payments", "fraud", "hitl", "simulation", "desk-toy"],
    on_success_callback=celebrate_dag_success,
) as dag:
    receive_batch = PythonOperator(
        task_id="receive_payment_batch",
        python_callable=receive_payment_batch,
    )

    fraud_checks = PythonOperator(
        task_id="run_fraud_checks",
        python_callable=run_fraud_checks,
    )

    prepare_case = PythonOperator(
        task_id="prepare_manual_review",
        python_callable=prepare_review_case,
    )

    nudge_manager = PythonOperator(
        task_id="nudge_manager",
        python_callable=request_physical_approval,
        op_kwargs={"dag_run_id": "{{ run_id }}"},
        retries=0,
    )

    manager_approval = ApprovalOperator(
        task_id=HITL_TASK_ID,
        subject="Approve high-value payment release?",
        body=(
            "**Case:** FR-9482  \n"
            "**Customer:** Northwind Trading  \n"
            "**Amount:** GBP 18,750.00  \n"
            "**Risk score:** 87/100  \n"
            "**Reason:** New device and unusually large international payment.  \n\n"
            "Review the case and approve the release, or reject it to stop processing."
        ),
        defaults="Reject",
        response_timeout=timedelta(minutes=2),
    )

    release = PythonOperator(
        task_id="release_payment",
        python_callable=release_payment,
    )

    update_ledger = PythonOperator(
        task_id="update_financial_ledger",
        python_callable=update_financial_ledger,
    )

    customer_notification = PythonOperator(
        task_id="notify_customer",
        python_callable=notify_customer,
    )

    receive_batch >> fraud_checks >> prepare_case
    prepare_case >> [nudge_manager, manager_approval]
    manager_approval >> release >> update_ledger >> customer_notification
