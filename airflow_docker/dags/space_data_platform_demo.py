"""Realistic data engineering workloads for Space Mission Control.

Choose an avatar with a rocket:heavy, rocket:shuttle, or rocket:courier tag.
"""

from datetime import datetime, timedelta
import time

from airflow import DAG
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.standard.operators.python import PythonOperator


START_DATE = datetime(2026, 1, 1)
EVERY_MINUTE = timedelta(minutes=1)


def process_batch(dataset: str, seconds: int = 3, **_context):
    print(f"{dataset}: processing batch")
    time.sleep(seconds)
    print(f"{dataset}: batch committed")


def reject_invalid_settlement(**_context):
    time.sleep(7)
    raise RuntimeError(
        "Settlement control total does not match the payment processor ledger"
    )


def intermittent_schema_drift(logical_date=None, **_context):
    time.sleep(6)
    minute = logical_date.minute if logical_date else datetime.now().minute
    if minute % 2 == 0:
        raise RuntimeError("Partner feed schema drift: required customer_id is missing")
    print("Partner feed passed its data contract")


def recover_after_retry(ti=None, **_context):
    time.sleep(5)
    if ti and ti.try_number == 1:
        raise RuntimeError("Transient source replication slot timeout")
    print("CDC replication slot recovered")


with DAG(
    dag_id="customer_360_incremental_refresh",
    description="Build the incremental customer 360 dimensional model",
    schedule=EVERY_MINUTE,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["space-mission-control", "customer-data", "rocket:heavy"],
) as customer_360_incremental_refresh:
    extract_customer_changes = PythonOperator(
        task_id="extract_customer_changes",
        python_callable=process_batch,
        op_kwargs={"dataset": "Customer CDC", "seconds": 75},
    )
    publish_customer_dimensions = EmptyOperator(task_id="publish_customer_dimensions")
    extract_customer_changes >> publish_customer_dimensions


with DAG(
    dag_id="clickstream_sessionization_hourly",
    description="Sessionize raw product clickstream events",
    schedule=EVERY_MINUTE,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["space-mission-control", "product-analytics", "rocket:shuttle"],
) as clickstream_sessionization_hourly:
    PythonOperator(
        task_id="sessionize_events",
        python_callable=process_batch,
        op_kwargs={"dataset": "Clickstream events", "seconds": 95},
    )


with DAG(
    dag_id="warehouse_fact_orders_backfill",
    description="Merge order facts into the analytics warehouse",
    schedule=EVERY_MINUTE,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["space-mission-control", "warehouse", "rocket:courier"],
) as warehouse_fact_orders_backfill:
    PythonOperator(
        task_id="merge_fact_orders",
        python_callable=process_batch,
        op_kwargs={"dataset": "Fact orders", "seconds": 125},
    )


with DAG(
    dag_id="realtime_fraud_feature_pipeline",
    description="Build fraud-model features across parallel transaction partitions",
    schedule=EVERY_MINUTE,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["space-mission-control", "machine-learning", "rocket:heavy"],
) as realtime_fraud_feature_pipeline:
    start_fraud_build = EmptyOperator(task_id="start_feature_build")
    feature_partitions = [
        PythonOperator(
            task_id=f"build_transaction_partition_{partition}",
            python_callable=process_batch,
            op_kwargs={"dataset": f"Fraud partition {partition}", "seconds": 24},
        )
        for partition in range(1, 7)
    ]
    publish_fraud_features = EmptyOperator(task_id="publish_feature_view")
    start_fraud_build >> feature_partitions >> publish_fraud_features


with DAG(
    dag_id="finance_daily_ledger_reconciliation",
    description="Reconcile warehouse balances against the finance ledger",
    schedule=EVERY_MINUTE,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["space-mission-control", "finance", "rocket:shuttle"],
) as finance_daily_ledger_reconciliation:
    PythonOperator(
        task_id="reconcile_ledger_balances",
        python_callable=process_batch,
        op_kwargs={"dataset": "Finance ledger", "seconds": 5},
    )


with DAG(
    dag_id="crm_account_snapshot_publish",
    description="Publish the latest CRM account snapshot for analytics",
    schedule=EVERY_MINUTE,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["space-mission-control", "crm", "rocket:courier"],
) as crm_account_snapshot_publish:
    snapshot = PythonOperator(
        task_id="build_account_snapshot",
        python_callable=process_batch,
        op_kwargs={"dataset": "CRM accounts", "seconds": 4},
    )
    publish = EmptyOperator(task_id="publish_snapshot")
    snapshot >> publish


with DAG(
    dag_id="marketing_attribution_model_refresh",
    description="Refresh multi-touch marketing attribution models",
    schedule=EVERY_MINUTE,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["space-mission-control", "marketing", "rocket:shuttle"],
) as marketing_attribution_model_refresh:
    PythonOperator(
        task_id="calculate_channel_attribution",
        python_callable=process_batch,
        op_kwargs={"dataset": "Marketing attribution", "seconds": 8},
    )


with DAG(
    dag_id="payments_settlement_control",
    description="Validate processor settlements against payment control totals",
    schedule=EVERY_MINUTE,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["space-mission-control", "payments", "rocket:heavy"],
) as payments_settlement_control:
    PythonOperator(
        task_id="validate_settlement_control_total",
        python_callable=reject_invalid_settlement,
    )


with DAG(
    dag_id="partner_feed_data_contract_monitor",
    description="Validate inbound partner data against its schema contract",
    schedule=EVERY_MINUTE,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["space-mission-control", "data-quality", "rocket:courier"],
) as partner_feed_data_contract_monitor:
    PythonOperator(
        task_id="validate_partner_schema",
        python_callable=intermittent_schema_drift,
    )


with DAG(
    dag_id="inventory_cdc_replication",
    description="Replicate inventory changes from the operational database",
    schedule=EVERY_MINUTE,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["space-mission-control", "cdc", "rocket:shuttle"],
) as inventory_cdc_replication:
    PythonOperator(
        task_id="replicate_inventory_changes",
        python_callable=recover_after_retry,
        retries=1,
        retry_delay=timedelta(seconds=25),
    )


with DAG(
    dag_id="legacy_erp_full_extract",
    description="Paused legacy ERP full-table extraction",
    schedule=EVERY_MINUTE,
    start_date=START_DATE,
    catchup=False,
    is_paused_upon_creation=True,
    tags=["space-mission-control", "paused", "rocket:heavy"],
) as legacy_erp_full_extract:
    PythonOperator(
        task_id="extract_legacy_erp_tables",
        python_callable=process_batch,
        op_kwargs={"dataset": "Legacy ERP", "seconds": 6},
    )


with DAG(
    dag_id="historical_orders_ad_hoc_backfill",
    description="Paused ad-hoc historical order backfill",
    schedule=EVERY_MINUTE,
    start_date=START_DATE,
    catchup=False,
    is_paused_upon_creation=True,
    tags=["space-mission-control", "paused", "rocket:courier"],
) as historical_orders_ad_hoc_backfill:
    PythonOperator(
        task_id="backfill_historical_orders",
        python_callable=process_batch,
        op_kwargs={"dataset": "Historical orders", "seconds": 6},
    )


with DAG(
    dag_id="pii_tokenization_key_rotation",
    description="Paused PII tokenization-key rotation workflow",
    schedule=EVERY_MINUTE,
    start_date=START_DATE,
    catchup=False,
    is_paused_upon_creation=True,
    tags=["space-mission-control", "security", "paused", "rocket:shuttle"],
) as pii_tokenization_key_rotation:
    PythonOperator(
        task_id="rotate_tokenization_keys",
        python_callable=process_batch,
        op_kwargs={"dataset": "PII token vault", "seconds": 6},
    )
