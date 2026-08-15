# Flight Director Console

A focused Airflow React app that monitors only the DAGstronaut
`planet_exploration_rover` DAG. It shows the current mission stage, run metadata,
task progress, and task states. When `flight_director_decision` becomes active,
the display automatically switches to a physical human-in-the-loop approval
workflow and submits exactly one selected branch through Airflow's supported
`PATCH .../hitlDetails` endpoint.

The console never calls the rover bridge and cannot move the rover directly.
Airflow remains the authoritative state machine and audit record.

## Build

```sh
cd airflow_docker/widgets/flight-director-console
pnpm install
pnpm typecheck
pnpm build
```

Open `/plugin/flight-director-console` in Airflow. The layout is designed for a
five-inch touchscreen and includes a fullscreen control.
