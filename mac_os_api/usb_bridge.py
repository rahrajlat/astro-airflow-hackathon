"""FastAPI bridge from the Airflow Docker stack to the USB rover."""

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    import cv2
except ImportError:
    cv2 = None


CONTROLLER = Path(__file__).with_name("usb_controller.py")
VENV_PYTHON = Path(__file__).with_name(".venv") / "bin" / "python"
CONTROLLER_PYTHON = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
CAPTURE_DIR = Path(
    os.getenv(
        "ROVER_CAPTURE_DIR",
        str(Path(__file__).parent.parent / "airflow_docker" / "rover_captures"),
    )
).expanduser()
CAMERA_INDEX = int(os.getenv("USB_CAMERA_INDEX", "0"))
CAMERA_WIDTH = int(os.getenv("USB_CAMERA_WIDTH", "1280"))
CAMERA_HEIGHT = int(os.getenv("USB_CAMERA_HEIGHT", "720"))
app = FastAPI(title="Astro Mission Companion USB rover bridge",
              version="1.2.0")
controller_lock = threading.Lock()
camera_lock = threading.Lock()


class CommandResult(BaseModel):
    returncode: int
    stdout: str
    stderr: str


class DistanceResult(BaseModel):
    distance_cm: int
    controller: CommandResult


class CameraCaptureResult(BaseModel):
    captured_at: str
    filename: str
    width: int
    height: int
    mime_type: str = "image/jpeg"


@app.get("/health")
def health():
    return {
        "status": "ok",
        "controller": str(CONTROLLER),
        "python": str(CONTROLLER_PYTHON),
        "camera": {
            "opencv_installed": cv2 is not None,
            "index": CAMERA_INDEX,
            "capture_dir": str(CAPTURE_DIR),
        },
    }


def open_camera():
    if cv2 is None:
        raise HTTPException(
            status_code=503,
            detail="Camera support is unavailable; install requirements.txt and restart the bridge",
        )
    camera = cv2.VideoCapture(CAMERA_INDEX)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    if not camera.isOpened():
        camera.release()
        raise HTTPException(
            status_code=503,
            detail=f"Could not open USB camera index {CAMERA_INDEX}",
        )
    return camera


@app.get("/camera/status")
def camera_status():
    """Check whether the configured Mac camera can be opened."""
    with camera_lock:
        camera = open_camera()
        camera.release()
    return {"status": "ready", "camera_index": CAMERA_INDEX}


@app.post("/camera/capture", response_model=CameraCaptureResult)
def camera_capture():
    """Capture one JPEG frame into the shared Airflow camera directory."""
    with camera_lock:
        camera = open_camera()
        try:
            # Discard initial frames while exposure and white balance settle.
            frame = None
            for _ in range(5):
                ok, candidate = camera.read()
                if ok:
                    frame = candidate
                time.sleep(0.08)
        finally:
            camera.release()
    if frame is None:
        raise HTTPException(
            status_code=502, detail="USB camera returned no image")

    encoded_ok, encoded = cv2.imencode(
        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not encoded_ok:
        raise HTTPException(
            status_code=500, detail="Could not encode camera frame")
    captured_at = datetime.now(timezone.utc)
    filename = f"rover-{captured_at.strftime('%Y%m%dT%H%M%S%fZ')}.jpg"
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = CAPTURE_DIR / filename
    path.write_bytes(encoded.tobytes())
    height, width = frame.shape[:2]
    return CameraCaptureResult(
        captured_at=captured_at.isoformat(),
        filename=filename,
        width=width,
        height=height,
    )


@app.get("/camera/latest")
def camera_latest():
    """Download the most recently captured rover photograph."""
    captures = sorted(CAPTURE_DIR.glob("rover-*.jpg"), reverse=True)
    if not captures:
        raise HTTPException(
            status_code=404, detail="No rover photograph captured yet")
    return FileResponse(captures[0], media_type="image/jpeg", filename=captures[0].name)


@app.post("/happy", response_model=CommandResult)
def happy(duration: float | None = None):
    """Run the happy emote, optionally for a controlled duration."""
    if duration is not None and not 0 < duration <= 30:
        raise HTTPException(
            status_code=422, detail="duration must be between 0 and 30")
    return run_controller("happy", 3, duration)


@app.post("/nudge", response_model=CommandResult)
def nudge():
    """Execute: python3 usb_controller.py nudge 8."""
    return run_controller("nudge", 8)


@app.post("/sad", response_model=CommandResult)
def sad(duration: float | None = None):
    """Run the sad emote, optionally for a controlled duration."""
    if duration is not None and not 0 < duration <= 30:
        raise HTTPException(
            status_code=422, detail="duration must be between 0 and 30")
    return run_controller("sad", 3, duration)


@app.post("/move/{direction}", response_model=CommandResult)
def move(direction: str, steps: int = 1):
    """Move the rover in one direction for 1–20 discrete steps."""
    if direction not in {"forward", "backward", "left", "right"}:
        raise HTTPException(
            status_code=404, detail="Unsupported rover direction")
    if not 1 <= steps <= 20:
        raise HTTPException(
            status_code=422, detail="steps must be between 1 and 20")
    return run_controller(direction, steps)


@app.get("/distance", response_model=DistanceResult)
def distance():
    """Read the rover's forward ultrasonic distance in centimetres."""
    attempts = []
    for attempt in range(3):
        result = run_controller("distance", None)
        match = re.search(r"OK DISTANCE (\d+)", result.stdout)
        if match is not None:
            return DistanceResult(distance_cm=int(match.group(1)), controller=result)
        attempts.append({"stdout": result.stdout, "stderr": result.stderr})
        if attempt < 2:
            time.sleep(0.35)
    raise HTTPException(
        status_code=502,
        detail={"message": "Rover returned no distance reading after 3 attempts",
                "attempts": attempts},
    )


def run_controller(
    command: str, value: int | None, duration: float | None = None
) -> CommandResult:
    arguments = [str(CONTROLLER_PYTHON), str(CONTROLLER), command]
    if value is not None:
        arguments.append(str(value))
    if duration is not None:
        arguments.extend(["--duration", str(duration)])
    try:
        with controller_lock:
            result = subprocess.run(
                arguments,
                cwd=CONTROLLER.parent,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
    except subprocess.TimeoutExpired as error:
        raise HTTPException(
            status_code=504, detail="USB controller timed out") from error

    response = CommandResult(
        returncode=result.returncode,
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=response.model_dump())
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8765)
