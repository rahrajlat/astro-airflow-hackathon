# Space Mission Control

A standalone space-themed Airflow operations dashboard for the Astronomer Beyond the DAG 2026 wildcard. It provides an overview, unified visualization, seven state pages, activity windows, fullscreen mode, live polling, task-planet graphs, native Airflow deep links, and a live CPU/memory/disk resource cockpit.

## Mission language

- Running: **Orbital Transit** / rockets in transit
- Queued: **Launch Complex** / fueled and awaiting a worker
- Scheduled: **Flight Manifest** / awaiting a launch window
- Success: **Recovery Fleet** / mission accomplished
- Failed: **Impact Zone** / crashed rockets
- Paused: **Cryogenic Hold**
- HITL: **Flight Director's Console** / crew authorization

## Build and open

```sh
cd airflow_docker/widgets/space-mission-control
pnpm install
pnpm typecheck
pnpm build
cd ../..
docker compose restart airflow-apiserver
```

Open `http://localhost:8080/plugin/space-mission-control`. The widget uses its dedicated `/mission-control-api/dags` telemetry endpoint and is served from `/mission-control-api/assets`.

The active fleet uses the fire-exhaust cartoon assets `public/rocket-heavy-cartoon-fire-v2.png`, `public/rocket-shuttle-cartoon-fire-v2.png`, and `public/rocket-courier-cartoon-fire-v2.png`. Earlier cartoon and realistic rocket sets remain available as alternate visual treatments.

## Choose a rocket avatar

Add one supported rocket tag to any DAG:

```python
with DAG(
    dag_id="customer_360_incremental_refresh",
    tags=["rocket:heavy"],
    # ...
):
    ...
```

Supported tags are `rocket:heavy`, `rocket:shuttle`, and `rocket:courier`. DAGs without a rocket tag receive a stable avatar derived from their DAG ID. Running DAGs display a live crew-comms timer based on the current DagRun start time.

## Filter by DAG tag

The dashboard builds its tag selector dynamically from Airflow DAG metadata. Each option includes the number of matching DAGs, and selecting a tag filters every dashboard view and state count.

## Rocket Test Bench

Open **Rocket Test Bench** from the dashboard navigation to run a single task with
`airflow tasks test`. Select a DAG and task, set its logical date, and optionally
provide a JSON object that is passed to Airflow as `--task-params`. The console
shows the exact command, exit code, duration, and combined task output. Tests are
limited to five minutes and are serialized in the API server.
