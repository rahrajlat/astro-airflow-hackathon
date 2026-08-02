"""Generate a fraud-review brief with Common AI, then request HITL approval."""

from datetime import datetime, timedelta
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from airflow import DAG
from airflow.providers.common.ai.operators.llm import LLMOperator
from airflow.providers.standard.operators.hitl import ApprovalOperator
from airflow.providers.standard.operators.python import PythonOperator


DAG_ID = "ai_generated_fraud_review_hitl"
HITL_TASK_ID = "human_approval"
ROBOT_BRIDGE_URL = os.getenv(
    "ROBOT_BRIDGE_URL", "http://host.docker.internal:8765"
).rstrip("/")
AIRFLOW_SERVER_URL = "http://airflow-apiserver:8080"


class ApprovalBrief(BaseModel):
    """Structured content shown to the human reviewer in Airflow."""

    subject: str = Field(description="A short approval question")
    body: str = Field(description="A concise Markdown review brief")


def collect_transaction_evidence():
    print("Collecting transaction, customer, device, and location evidence...")
    time.sleep(3)
    evidence = {
        "case_id": "FR-9482",
        "customer": "Northwind Trading",
        "amount": "GBP 18,750.00",
        "risk_score": 87,
        "device": "New device first seen 12 minutes ago",
        "location": "Payment originated outside the customer's usual region",
        "account_age": "6 years",
        "previous_chargebacks": 0,
        "reason": "New device and unusually large international payment",
    }
    print(f"Evidence package ready for {evidence['case_id']}")
    return evidence


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
            "Cannot reach the robot bridge running on the Mac at "
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
                print("Clap accepted as the Airflow HITL approval")
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
    print("AI brief is ready; nudging the human reviewer...")
    result = send_usb_command("nudge")
    print(result.get("stdout") or "Nudge completed")
    if "OK APPROVED" in result.get("stdout", ""):
        return submit_hitl_approval(dag_run_id)
    print("No clap detected; approval remains available in the Airflow UI")
    return {"clap_detected": False}


def celebrate_dag_success(context):
    print("AI-assisted DAG succeeded; running the happy emote for 10 seconds...")
    result = send_usb_command("happy", duration=10)
    print(result.get("stdout") or "Ten-second happy emote completed")


def release_payment():
    print("Human approval received. Releasing the held payment...")
    time.sleep(4)
    print("Payment released and audit event recorded")


def notify_finance_team():
    print("Preparing the final decision notification...")
    time.sleep(2)
    print("Finance and customer-support teams notified")


with DAG(
    dag_id=DAG_ID,
    description="Use Common AI with local Ollama to generate a native HITL review",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["common-ai", "ollama", "llama", "hitl", "fraud", "rocket:shuttle"],
    on_success_callback=celebrate_dag_success,
) as dag:
    collect_evidence = PythonOperator(
        task_id="collect_transaction_evidence",
        python_callable=collect_transaction_evidence,
    )

    generate_approval_brief = LLMOperator(
        task_id="generate_approval_brief",
        llm_conn_id="ollama_local",
        prompt="""
        Create the human approval brief for this payment-fraud case.

        Evidence:
        {{ ti.xcom_pull(task_ids='collect_transaction_evidence') | tojson }}

        The subject must be a short question. The body must use clear Markdown and
        include the case, customer, amount, risk score, main reason, and the most
        decision-relevant supporting evidence. End by asking the reviewer to approve
        release or reject it. Do not invent facts and do not make the decision.
        """,
        system_prompt=(
            "You are a payments risk analyst preparing accurate, concise evidence "
            "for a human decision. You never approve or reject the payment yourself."
        ),
        output_type=ApprovalBrief,
        serialize_output=True,
        agent_params={
            "retries": 2,
            "model_settings": {"temperature": 0.2},
        },
    )

    human_approval = ApprovalOperator(
        task_id=HITL_TASK_ID,
        subject=(
            "{{ ti.xcom_pull(task_ids='generate_approval_brief')['subject'] }}"
        ),
        body="{{ ti.xcom_pull(task_ids='generate_approval_brief')['body'] }}",
        defaults="Reject",
        response_timeout=timedelta(minutes=5),
    )

    nudge_reviewer = PythonOperator(
        task_id="nudge_reviewer",
        python_callable=request_physical_approval,
        op_kwargs={"dag_run_id": "{{ run_id }}"},
        retries=0,
    )

    release = PythonOperator(
        task_id="release_payment",
        python_callable=release_payment,
    )

    notify = PythonOperator(
        task_id="notify_finance_team",
        python_callable=notify_finance_team,
    )

    collect_evidence >> generate_approval_brief
    generate_approval_brief >> [nudge_reviewer, human_approval]
    human_approval >> release >> notify
