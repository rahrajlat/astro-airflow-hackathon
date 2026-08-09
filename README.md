<div align="center">

<hr />

<h1><img src="media/dagstronaut-logo.png" alt="DAGstronaut logo" width="72" align="center" /> DAGstronaut</h1>

<blockquote><strong>It stops five centimetres from an obstacle—and waits for a human to decide what happens next.</strong></blockquote>

[![Apache Airflow](https://img.shields.io/badge/Apache_Airflow-3.3-017CEE?logo=apacheairflow&logoColor=white)](https://airflow.apache.org/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=0B1020)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Ollama](https://img.shields.io/badge/Ollama-Local_AI-111111?logo=ollama&logoColor=white)](https://ollama.com/)
[![micro:bit](https://img.shields.io/badge/micro%3Abit-Physical_Rover-00ED00?logo=microbit&logoColor=white)](https://microbit.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-D22128?logoColor=white)](LICENSE)

<hr />

**An Apache Airflow 3 DAG that drives a physical micro:bit rover: it senses with
ultrasound, reads the obstacle with a local vision model, and waits for a human
to authorize every movement. A companion Space Mission Control plugin flies the
whole DAG fleet as rockets.**

<br />

[![Apache Airflow](https://img.shields.io/badge/Apache_Airflow-3.3-017CEE?logo=apacheairflow&logoColor=white)](https://airflow.apache.org/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=0B1020)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Ollama](https://img.shields.io/badge/Ollama-Local_AI-111111?logo=ollama&logoColor=white)](https://ollama.com/)
[![micro:bit](https://img.shields.io/badge/micro%3Abit-Physical_Rover-00ED00?logo=microbit&logoColor=white)](https://microbit.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-D22128?logo=apache&logoColor=white)](LICENSE)

[Beyond the DAG 2026](https://www.astronomer.io/events/beyond-the-dag-data-engineering-hackathon-2026/) · [Apache Airflow](https://airflow.apache.org/) · [Airflow Plugins](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/plugins.html)

</div>

---

> [!NOTE]
> DAGstronaut is an independent open-source project created for
> Astronomer's **Beyond the DAG 2026** hackathon. “Astronomer” and related marks
> belong to their respective owners; this project is not an official
> Astronomer product.

## What is this project?

Most Airflow tasks can be re-run. This one can't—once a task turns a wheel, the
only undo is driving back.

That constraint is the point. `planet_exploration_rover` is an Airflow 3 DAG
that senses before it acts, asks a local vision model what it is looking at, and
then stops dead until a human authorizes the next physical move. Every reading,
every AI assessment, and every human decision lands in Airflow's own task logs
and XComs, so the whole mission is replayable after the fact.

Two connected parts make that work.

> **The rover is the spacecraft. The DAG is its flight plan. The Airflow plugin
> is Mission Control—tracking every stage, presenting the AI assessment, and
> placing the final maneuver in the hands of a human flight director.**

### 1. Planet Exploration Rover — a hardware-orchestrating Airflow DAG

The heart of the project is the `planet_exploration_rover` DAG, which controls a
real wheeled rover and coordinates a complete physical exploration mission.

The rover performs a motor systems check, moves forward one step at a time, and
sends an ultrasonic distance reading back to Airflow before every movement. At
the configured five-centimetre safety boundary, it stops and captures the
obstacle with a computer USB camera. Gemma Vision analyses the photograph and
sensor telemetry, then an Airflow HITL task asks a human flight director to
approve the next action. Airflow records outbound movement in XCom so the rover
can reverse the same number of steps and return to base.

**Airflow features used:**

- **`@task.llm` from `apache-airflow-providers-common-ai`** runs the multimodal
  assessment. The task sends the camera frame and sensor telemetry to a local
  Gemma 3 vision model and returns a Pydantic-validated `ObjectPrediction`
  through `NativeOutput`, so malformed model output fails the task instead of
  reaching the human. Only the compact assessment enters XCom—the JPEG and its
  base64 payload never touch the metadata database.
- **`HITLBranchOperator`** pauses the mission at the Flight Director's Console
  and routes execution to turn left, turn right, reverse, return to base, or
  abort. The model recommends; it cannot select the branch.
- **Jinja-templated HITL content** renders the object prediction, confidence,
  visual evidence, recommendation, and camera filename into the decision screen
  the human actually reads.
- **A named `outbound_steps` XCom**, rewritten after every successful forward
  movement, is the rover's durable mission memory. Return tasks read it to issue
  the matching number of backward motor pulses, so a mid-mission sensor failure
  still leaves a correct return distance recorded.
- **Branch-aware trigger rules** converge the mutually exclusive movement
  branches into one shared return-to-base task with
  `none_failed_min_one_success`, which then computes the inverse of whichever
  maneuver the human chose.
- **XComArg wiring** passes data by reference between a classic operator and a
  decorated task—`op_kwargs={"detection": explore.output}` feeding
  `predict_detected_object(capture.output)`—without a manual `xcom_pull`.
- **Task dependencies as safety interlocks.** The rover cannot explore before
  its systems check, photograph before detecting an obstacle, or move again
  before the human decision resolves. The graph is the safety model.
- **`max_active_runs=1`** prevents two missions from driving the same physical
  hardware at once.
- **`doc_md`** publishes the mission sequence, safety model, runtime
  architecture, and configuration table directly into the Airflow UI, so the
  DAG documents itself where an operator is standing.
- **Task logs and run history** preserve every sensor reading, bridge response,
  model assessment, human decision, and movement count—a replayable audit trail
  for an irreversible physical action.
- **A read-only Docker volume** exposes the captured photograph inside Airflow
  at `/opt/airflow/rover_captures`, keeping the camera on the Mac while the DAG
  task reads the evidence.

The physical build uses:

- A [BBC micro:bit board](https://www.keyestudio.com/collections/microbit-board)
  running the rover's [MicroPython firmware](microbit_firmware/README.md)
- A [Keyestudio micro:bit robot car](https://www.keyestudio.com/collections/microbit-car-415)
  as the mobile rover platform
- A [Keyestudio CS100A ultrasonic module](https://www.keyestudio.com/products/keyestudio-quick-connectors-ultrasonic-modulecs100a-chip-black-environment-friendly)
  for obstacle-distance telemetry
- A computer USB camera, read through OpenCV, that captures a forward-facing
  JPEG only once the ultrasonic sensor reaches the safety boundary
- Gemma 3 Vision on local Ollama, which keeps every frame and every inference on
  the same machine as the rover—no image leaves the host
- A USB connection to the [Mac USB bridge](mac_os_api/usb_bridge.py) that exposes
  rover movement, sensor, and camera operations to Airflow; see the
  [USB controller setup guide](mac_os_api/USB_CONTROLLER_README.md) for setup
  and usage

### 2. Space Mission Control — an Airflow UI plugin

The second part is the screen the mission is flown from: an
[Apache Airflow 3](https://airflow.apache.org/docs/apache-airflow/stable/index.html)
plugin that reimagines DAG monitoring as a space operations center. Each DAG is
represented as a rocket, and its real Airflow state becomes a stage of the
mission:

- Scheduled and queued DAGs prepare for launch.
- Running DAGs enter orbital transit with live mission telemetry.
- Successful DAGs land safely and join the recovery fleet.
- Failed DAGs appear in the Impact Zone for investigation and crash replay.
- Paused DAGs enter Cryogenic Hold.
- Pending HITL tasks wait at the Flight Director's Console for human input.

The plugin combines an Airflow `react_app` with a FastAPI telemetry service to
provide a command overview, animated state views, task constellations, failure
replay, resource telemetry, a Rocket Test Bench, and a rotating five-inch
mission display. It preserves native links to DAGs, runs, tasks, and logs while
giving everyday Airflow operations an Astronomer-flavoured mission language.

**Airflow features used:**

- **`AirflowPlugin`** registers the whole extension—React app, FastAPI service,
  and static assets—through Airflow's plugin manager alone, with no fork and no
  reverse proxy.
- **`react_apps`** mounts the React and TypeScript Mission Control interface as
  a native top-level page in the Airflow UI.
- **`fastapi_apps`** mounts a plugin-owned FastAPI application under
  `/mission-control-api` for mission telemetry, DAG details, host resources,
  static assets, and Rocket Test Bench requests.
- **Airflow metadata models**—`DagModel`, `DagRun`, and `TaskInstance`—provide
  real DAG configuration, latest-run state, timing, and task-instance data.
- **Airflow HITL metadata** (`HITLDetail` joined to `TaskInstance` on unanswered
  responses) builds a single cross-DAG queue of every decision currently blocked
  on a person, which is the Flight Director's Console.
- **DAG tags** select a stable rocket class such as `rocket:heavy`,
  `rocket:shuttle`, or `rocket:courier`, and power fleet filtering.
- **Task dependencies and task-instance state** create the task-constellation
  graph, progress display, mission timing, and animated failure replay.
- **Native Airflow deep links** take operators from a rocket directly to its
  DAG, current run, task instance, and logs.
- **The Airflow CLI** powers Rocket Test Bench with `airflow tasks test`,
  including logical dates and optional task parameters.
- **Live polling** keeps the plugin synchronized with changing Airflow state
  without introducing a separate monitoring database.

#### Rocket Test Bench

Space Mission Control also turns Airflow's task-test capability into a visual
rocket-testing station. An operator selects a DAG, task, and logical date in
the plugin, optionally supplies a JSON parameters object, and ignites an
isolated task test from the command deck.

The station executes the equivalent Airflow command:

```bash
airflow tasks test <DAG_ID> <TASK_ID> <LOGICAL_DATE> \
  --task-params '{"key":"value"}'
```

The plugin's FastAPI endpoint validates the request and runs the command in the
Airflow API-server environment. Bench runs are serialized to prevent unbounded
parallel subprocesses and are limited to five minutes. The station captures
the exact command, combined task logs, execution duration, exit code, and
truncation status, then presents the result as a clear **PASS** or **FAIL**
engine diagnostic. Because it uses `airflow tasks test`, the task can be tested
without creating a normal scheduled task instance or DagRun.

A secondary Raspberry Pi with a five-inch display acts as the controller's
dedicated cockpit screen. It opens the plugin's small-screen view in fullscreen
mode and rotates every ten seconds through high-level running, successful,
failed, queued, scheduled, paused, and HITL mission status. This gives the
operator an always-on, glanceable view of the Airflow fleet while the main
Mission Control interface remains available for detailed investigation. The
Raspberry Pi is used only as a cockpit display; rover commands, USB sensor data,
and camera capture continue to pass through the Mac-hosted bridge.

## Why space and rockets?

Because this hackathon is run by [Astronomer](https://www.astronomer.io/), the
plugin borrows space as its visual language. Rockets, mission stages, and a
flight director's console map cleanly onto what Airflow already does: workflows
launch, move through coordinated stages, report live state, ask for human
guidance, and either land or need recovery. The theme is not only decoration—it
makes orchestration status readable at a glance.

---

_This is the first README section. Architecture, features, the physical rover
mission, installation, screenshots, and contributor documentation will be
added after the project narrative is refined._

Test commit from ubuntu
