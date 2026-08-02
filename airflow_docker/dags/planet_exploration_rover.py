"""Orchestrate a camera-assisted physical rover mission with Apache Airflow.

The DAG checks the Mac-hosted USB bridge, moves the rover forward in discrete
steps, and stops when its ultrasonic sensor reports an obstacle at or inside
the configured safety distance. It then captures a USB-camera photograph,
asks a local Gemma vision model for a structured assessment, and pauses at an
Airflow HITL branch so a human flight director chooses the physical response.

The exploration task records every successful outbound movement in the named
``outbound_steps`` XCom. Return branches use that value to retrace the journey
in reverse; the value is an open-loop motor-pulse count, not wheel odometry or
a measurement in centimetres.

The USB rover and camera remain attached to the Mac. Airflow containers reach
the bridge through ``ROBOT_BRIDGE_URL`` and read captured JPEGs through the
read-only ``ROVER_CAPTURE_MOUNT_PATH`` Docker volume.
"""

import base64
from datetime import datetime
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from airflow import DAG
from airflow.providers.standard.operators.hitl import HITLBranchOperator
from airflow.providers.standard.operators.python import PythonOperator


ROBOT_BRIDGE_URL = os.getenv(
    "ROBOT_BRIDGE_URL", "http://host.docker.internal:8765"
).rstrip("/")
OBSTACLE_DISTANCE_CM = int(os.getenv("ROVER_OBSTACLE_DISTANCE_CM", "5"))
MAX_FORWARD_STEPS = int(os.getenv("ROVER_MAX_FORWARD_STEPS", "50"))
TURN_STEPS = int(os.getenv("ROVER_TURN_STEPS", "4"))
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL", "http://host.docker.internal:11434"
).rstrip("/")
ROVER_VISION_MODEL = os.getenv("ROVER_VISION_MODEL", "gemma3:4b")
ROVER_CAPTURE_MOUNT_PATH = Path(
    os.getenv("ROVER_CAPTURE_MOUNT_PATH", "/opt/airflow/rover_captures")
)


class ObjectPrediction(BaseModel):
    """Validate the navigation assessment returned by the vision model.

    Supplying this schema to Ollama constrains Gemma to produce a compact,
    serializable result suitable for XCom and the HITL decision screen.
    """

    predicted_object: str = Field(
        description="Likely terrain feature, such as wall, rock, or large obstruction"
    )
    confidence_percent: int = Field(ge=0, le=100)
    evidence: str = Field(description="Short explanation grounded in the image and readings")
    recommended_action: str = Field(
        description="One of turn left, turn right, move backward, return to base, or abort"
    )


def bridge_request(path, method="GET", timeout=15):
    """Call the Mac rover bridge and decode its JSON response.

    Args:
        path: Bridge path beginning with ``/``, optionally including a query.
        method: HTTP method used for the request.
        timeout: Maximum number of seconds to wait for the bridge.

    Returns:
        The decoded JSON response from the FastAPI bridge.

    Raises:
        RuntimeError: If the bridge rejects the request or cannot be reached.
    """
    request = Request(f"{ROBOT_BRIDGE_URL}{path}", method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Rover bridge failed ({error.code}): {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Rover bridge is offline at {ROBOT_BRIDGE_URL}") from error


def analyse_object_photo(**context):
    """Capture and classify the obstacle using the mounted USB-camera photo.

    The bridge writes a JPEG on the Mac and returns only capture metadata. This
    task waits briefly for Docker Desktop to expose that file through the
    read-only Airflow mount, base64-encodes it for Ollama's chat API, and asks
    ``ROVER_VISION_MODEL`` for an ``ObjectPrediction``. Only the small validated
    result and capture metadata are returned to XCom; image bytes are excluded.

    Args:
        **context: Airflow runtime context containing the task instance used to
            pull the ultrasonic detection result.

    Returns:
        A prediction dictionary containing the object, confidence, evidence,
        recommended action, vision model, and camera capture metadata.

    Raises:
        RuntimeError: If the mounted image is missing or empty, Ollama is
            unavailable, or Gemma returns output that fails schema validation.
    """
    detection = context["ti"].xcom_pull(task_ids="explore_until_object")
    capture = bridge_request("/camera/capture", method="POST", timeout=30)
    filename = Path(capture["filename"]).name
    image_path = ROVER_CAPTURE_MOUNT_PATH / filename
    # Docker Desktop file sharing can take a moment to expose a newly written file.
    for _ in range(10):
        if image_path.is_file():
            break
        time.sleep(0.2)
    if not image_path.is_file():
        raise RuntimeError(
            f"Captured image is not visible inside Airflow at {image_path}. "
            "Recreate the containers so the rover_captures volume is mounted."
        )
    image_bytes = image_path.read_bytes()
    if not image_bytes:
        raise RuntimeError(f"Captured image is empty: {image_path}")
    image_base64 = base64.b64encode(image_bytes).decode("ascii")
    prompt = (
        "You are a cautious planetary-rover navigation analyst. Inspect the attached "
        f"forward-camera image. The ultrasonic sensor reports an obstacle at "
        f"{detection['distance_cm']} cm after {detection['forward_steps']} forward "
        "steps. Identify only what is visually supportable, acknowledge uncertainty, "
        "and recommend exactly one action: turn left, turn right, move backward, "
        "return to base, or abort. Prefer return to base when confidence is low or "
        "the route appears unsafe."
    )
    payload = json.dumps(
        {
            "model": ROVER_VISION_MODEL,
            "stream": False,
            "format": ObjectPrediction.model_json_schema(),
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_base64],
                }
            ],
            "options": {"temperature": 0.1},
        }
    ).encode("utf-8")
    request = Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=120) as response:
            ollama_response = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Vision model {ROVER_VISION_MODEL} failed ({error.code}): {detail}"
        ) from error
    except URLError as error:
        raise RuntimeError(f"Ollama is offline at {OLLAMA_BASE_URL}") from error

    content = ollama_response.get("message", {}).get("content", "")
    try:
        prediction = ObjectPrediction.model_validate_json(content)
    except Exception as error:
        raise RuntimeError(f"Vision model returned invalid structured output: {content}") from error
    result = prediction.model_dump()
    result["camera_capture"] = capture
    result["camera_capture"]["airflow_path"] = str(image_path)
    result["vision_model"] = ROVER_VISION_MODEL
    print(json.dumps(result, indent=2))
    return result


def move_in_chunks(direction, steps):
    """Move in batches that respect the bridge's 20-step command limit.

    Args:
        direction: One of the movement directions supported by the bridge.
        steps: Total number of discrete motor pulses to execute.

    Returns:
        A list containing the bridge response for every movement batch.
    """
    remaining = steps
    responses = []
    while remaining > 0:
        chunk = min(remaining, 20)
        responses.append(
            bridge_request(f"/move/{direction}?steps={chunk}", method="POST", timeout=30)
        )
        remaining -= chunk
        if remaining:
            time.sleep(0.4)
    return responses


def systems_check():
    """Verify bridge health and test steering without changing rover heading.

    The rover turns left two steps, right four steps, then left two steps. This
    exercises both steering directions and leaves it approximately aligned with
    its original launch heading. Because the rover has no wheel encoders, this
    is a functional motor check rather than a calibrated orientation test.

    Returns:
        Bridge health data and a summary of the movement check for XCom.
    """
    health = bridge_request("/health")
    print(f"Astro Mission Companion online: {health}")
    print("Testing left motor response")
    bridge_request("/move/left?steps=2", method="POST")
    time.sleep(0.4)
    print("Testing right motor response and crossing the centre heading")
    bridge_request("/move/right?steps=4", method="POST")
    time.sleep(0.4)
    print("Returning to original launch heading")
    bridge_request("/move/left?steps=2", method="POST")
    return {"bridge": health, "movement_check": "left 2, right 4, left 2"}


def explore_until_obstacle(**context):
    """Advance one step at a time until an ultrasonic obstacle is detected.

    A distance reading is taken before every forward movement. Readings at or
    below ``OBSTACLE_DISTANCE_CM`` stop exploration immediately. A zero reading
    means that no valid echo was received, so three consecutive invalid samples
    fail the task rather than being interpreted as a clear path.

    After each successful forward command, the function updates the named
    ``outbound_steps`` XCom. Updating it incrementally preserves the best-known
    return distance even if a later sensor request fails.

    Args:
        **context: Airflow runtime context containing the task instance used to
            push the outbound-step XCom.

    Returns:
        Detection distance, forward-step count, and all ultrasonic samples.

    Raises:
        RuntimeError: If the sensor repeatedly returns invalid data or no object
            is detected within ``MAX_FORWARD_STEPS``.
    """
    ti = context["ti"]
    invalid_readings = 0
    samples = []
    ti.xcom_push(key="outbound_steps", value=0)
    for step in range(MAX_FORWARD_STEPS + 1):
        distance = int(bridge_request("/distance")["distance_cm"])
        samples.append({"step": step, "distance_cm": distance})
        print(f"Survey step {step}: object distance={distance} cm")

        # A zero reading means no echo, not a clear path. Fail safely rather
        # than driving without a working distance measurement.
        if distance <= 0:
            invalid_readings += 1
            if invalid_readings >= 3:
                raise RuntimeError("Ultrasonic sensor returned three invalid readings")
            time.sleep(0.3)
            continue

        invalid_readings = 0
        if distance <= OBSTACLE_DISTANCE_CM:
            print(f"Object detected at {distance} cm after {step} forward steps")
            return {
                "object_found": True,
                "distance_cm": distance,
                "forward_steps": step,
                "samples": samples,
            }

        if step == MAX_FORWARD_STEPS:
            break
        bridge_request("/move/forward?steps=1", method="POST")
        ti.xcom_push(key="outbound_steps", value=step + 1)
        # Let motor vibration/electrical noise settle before the next ultrasonic ping.
        time.sleep(0.6)

    raise RuntimeError(
        f"No object detected within the {MAX_FORWARD_STEPS}-step safety limit"
    )


def execute_avoidance(direction):
    """Execute the human-selected local avoidance maneuver.

    Left and right decisions turn by ``TURN_STEPS`` and then travel five steps
    along the new heading. A backward decision reverses five steps without a
    turn. The returned movement metadata lets ``return_to_base`` undo the
    maneuver before retracing the original outbound path.

    Args:
        direction: ``left``, ``right``, or ``backward``.

    Returns:
        Movement counts and raw bridge responses describing the maneuver.

    Raises:
        ValueError: If an unsupported direction is supplied.
    """
    print(f"Flight director selected: {direction}")
    if direction in {"left", "right"}:
        turn_result = bridge_request(
            f"/move/{direction}?steps={TURN_STEPS}", method="POST"
        )
        print(f"Turn complete; advancing 5 steps on the new heading")
        forward_result = bridge_request("/move/forward?steps=5", method="POST")
        return {
            "turn_direction": direction,
            "turn_steps": TURN_STEPS,
            "forward_steps": 5,
            "turn_result": turn_result,
            "forward_result": forward_result,
        }
    if direction == "backward":
        result = bridge_request("/move/backward?steps=5", method="POST")
        return {"backward_steps": 5, "backward_result": result}
    raise ValueError(f"Unsupported avoidance direction: {direction}")


def abort_mission():
    """Record a no-movement flight-director decision and keep the rover stopped."""
    print("Flight director aborted movement; rover remains stopped")
    return {"status": "aborted", "movement": "none"}


def return_to_base_now(**context):
    """Immediately retrace the recorded outbound path using its XCom step count.

    This is a selectable HITL branch. It pulls ``outbound_steps`` directly from
    ``explore_until_object`` and issues the same number of backward pulses. Its
    confirmation flag tells the shared return task not to reverse the path a
    second time.

    Args:
        **context: Airflow runtime context containing the task instance.

    Returns:
        Confirmation of arrival and the number of backward steps executed.
    """
    ti = context["ti"]
    outbound_steps = int(
        ti.xcom_pull(task_ids="explore_until_object", key="outbound_steps") or 0
    )
    print(f"AI/HITL selected return to base: reversing {outbound_steps} outbound steps")
    if outbound_steps:
        move_in_chunks("backward", outbound_steps)
    return {
        "returned_to_base": True,
        "backward_steps": outbound_steps,
        "source_xcom_key": "outbound_steps",
    }


def return_to_base(**context):
    """Undo the selected branch maneuver and return to the recorded launch base.

    For a turn-and-advance branch, the rover first reverses the five-step
    diversion and applies the inverse turn before backing through the outbound
    steps. For a backward branch, already-reversed steps are subtracted and an
    overshoot is corrected forward. An immediate-return branch is recognized as
    complete and is not repeated. Abort branches simply reverse the full
    outbound count.

    This is open-loop navigation: the algorithm assumes backward motor pulses
    approximately cancel forward pulses. It cannot compensate for wheel slip,
    turns caused by uneven motors, or a displaced rover.

    Args:
        **context: Airflow runtime context used to pull detection, branch choice,
            branch result, and named outbound-step XComs.

    Returns:
        A return summary containing the reversed step count and branch metadata.

    Raises:
        RuntimeError: If the immediate-return branch does not confirm completion.
    """
    ti = context["ti"]
    detection = ti.xcom_pull(task_ids="explore_until_object")
    decision = ti.xcom_pull(task_ids="flight_director_decision")
    if isinstance(decision, (list, tuple)):
        decision = decision[0] if decision else "abort_and_hold_position"
    outbound_steps = int(
        ti.xcom_pull(task_ids="explore_until_object", key="outbound_steps")
        or detection["forward_steps"]
    )
    action = ti.xcom_pull(task_ids=decision) or {}
    print(f"Return-to-base sequence after {decision}; outbound={outbound_steps} steps")

    if decision in {"turn_left_then_move_five", "turn_right_then_move_five"}:
        # Back out of the five-step diversion, then restore the original heading.
        diversion_steps = int(action.get("forward_steps", 0))
        turn_steps = int(action.get("turn_steps", 0))
        turn_direction = action.get("turn_direction")
        if diversion_steps:
            move_in_chunks("backward", diversion_steps)
        inverse = "right" if turn_direction == "left" else "left"
        if turn_steps:
            move_in_chunks(inverse, turn_steps)
        remaining_backward = outbound_steps
    elif decision == "move_backward_five":
        # The selected action already travelled toward base. Correct an overshoot.
        action_backward_steps = int(action.get("backward_steps", 0))
        if outbound_steps < action_backward_steps:
            move_in_chunks("forward", action_backward_steps - outbound_steps)
            remaining_backward = 0
        else:
            remaining_backward = outbound_steps - action_backward_steps
    elif decision == "return_to_base_now":
        if not action.get("returned_to_base"):
            raise RuntimeError("Return-to-base branch did not confirm arrival")
        remaining_backward = 0
    else:
        remaining_backward = outbound_steps

    if remaining_backward:
        move_in_chunks("backward", remaining_backward)
    print("Rover returned to the recorded launch base")
    return {
        "status": "at base",
        "outbound_steps_reversed": outbound_steps,
        "decision_reversed": decision,
        "action_xcom": action,
    }


def mission_report(**context):
    """Combine sensor, vision, decision, and return telemetry into a final report.

    Args:
        **context: Airflow runtime context used to pull upstream task results.

    Returns:
        A JSON-serializable mission summary, also printed to the task log.
    """
    detection = context["ti"].xcom_pull(task_ids="explore_until_object")
    return_journey = context["ti"].xcom_pull(task_ids="return_to_base")
    prediction = context["ti"].xcom_pull(task_ids="predict_detected_object")
    report = {
        "mission": "planet_exploration_rover",
        "object_distance_cm": detection["distance_cm"],
        "steps_before_detection": detection["forward_steps"],
        "camera_assessment": prediction,
        "return_journey": return_journey,
        "status": "flight-director action completed",
    }
    print(json.dumps(report, indent=2))
    return report


with DAG(
    dag_id="planet_exploration_rover",
    description="Explore, photograph an obstacle, analyse it with vision AI, then reroute",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["astro", "physical-rover", "ultrasonic", "usb-camera", "vision-ai", "rocket:courier"],
) as dag:
    check = PythonOperator(task_id="systems_check", python_callable=systems_check)
    explore = PythonOperator(
        task_id="explore_until_object",
        python_callable=explore_until_obstacle,
        execution_timeout=None,
    )
    predict = PythonOperator(
        task_id="predict_detected_object",
        python_callable=analyse_object_photo,
    )

    choose_action = HITLBranchOperator(
        task_id="flight_director_decision",
        subject="Rover obstacle detected — choose avoidance action",
        body="""
        ### AI terrain assessment

        **Prediction:** {{ ti.xcom_pull(task_ids='predict_detected_object')['predicted_object'] }}

        **Confidence:** {{ ti.xcom_pull(task_ids='predict_detected_object')['confidence_percent'] }}%

        **Evidence:** {{ ti.xcom_pull(task_ids='predict_detected_object')['evidence'] }}

        **AI recommendation:** {{ ti.xcom_pull(task_ids='predict_detected_object')['recommended_action'] }}

        **Camera frame:** {{ ti.xcom_pull(task_ids='predict_detected_object')['camera_capture']['filename'] }}

        The prediction combines a USB-camera image with ultrasonic distance telemetry.
        Select the physical action the rover should execute.
        """,
        options=[
            "turn_left_then_move_five",
            "turn_right_then_move_five",
            "move_backward_five",
            "return_to_base_now",
            "abort_and_hold_position",
        ],
        defaults="abort_and_hold_position",
    )

    turn_left = PythonOperator(
        task_id="turn_left_then_move_five",
        python_callable=execute_avoidance,
        op_kwargs={"direction": "left"},
    )
    turn_right = PythonOperator(
        task_id="turn_right_then_move_five",
        python_callable=execute_avoidance,
        op_kwargs={"direction": "right"},
    )
    reverse = PythonOperator(
        task_id="move_backward_five",
        python_callable=execute_avoidance,
        op_kwargs={"direction": "backward"},
    )
    abort = PythonOperator(
        task_id="abort_and_hold_position",
        python_callable=abort_mission,
    )
    immediate_return = PythonOperator(
        task_id="return_to_base_now",
        python_callable=return_to_base_now,
    )
    report = PythonOperator(
        task_id="publish_mission_report",
        python_callable=mission_report,
    )
    return_base = PythonOperator(
        task_id="return_to_base",
        python_callable=return_to_base,
        trigger_rule="none_failed_min_one_success",
    )

    check >> explore >> predict >> choose_action
    choose_action >> [turn_left, turn_right, reverse, immediate_return, abort] >> return_base >> report
