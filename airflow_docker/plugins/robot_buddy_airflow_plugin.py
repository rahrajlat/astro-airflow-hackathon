"""Airflow 3 plugin that embeds the Astro Mission Companion control panel."""

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import mimetypes
import os

from airflow.plugins_manager import AirflowPlugin
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles


ROBOT_BRIDGE_URL = os.getenv(
    "ROBOT_BRIDGE_URL", "http://host.docker.internal:8765"
).rstrip("/")
ROBOT_COMMANDS = {"happy", "sad", "nudge"}
ROVER_DIRECTIONS = {"forward", "backward", "left", "right"}
REACT_DIST = Path("/opt/airflow/widgets/robot-buddy/dist")

mimetypes.add_type("application/javascript", ".cjs")

robot_buddy_app = FastAPI(title="Astro Mission Companion API")


@robot_buddy_app.get("/health")
def health():
    try:
        with urlopen(f"{ROBOT_BRIDGE_URL}/health", timeout=3) as response:
            bridge = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError):
        return {"status": "offline", "bridge": None}
    return {"status": "online", "bridge": bridge}


@robot_buddy_app.post("/command/{command}")
def send_robot_command(command: str):
    if command not in ROBOT_COMMANDS:
        raise HTTPException(status_code=404, detail="Unsupported robot command")

    request = Request(f"{ROBOT_BRIDGE_URL}/{command}", method="POST")
    try:
        with urlopen(request, timeout=50) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=502, detail=detail) from error
    except URLError as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "Astro Mission Companion is offline. Check usb_bridge.py on the Mac "
                f"at {ROBOT_BRIDGE_URL}."
            ),
        ) from error

    return {"command": command, "status": "completed", "result": result}


@robot_buddy_app.post("/move/{direction}")
def move_rover(direction: str, steps: int = 1):
    if direction not in ROVER_DIRECTIONS:
        raise HTTPException(status_code=404, detail="Unsupported rover direction")
    if not 1 <= steps <= 20:
        raise HTTPException(status_code=422, detail="steps must be between 1 and 20")

    request = Request(
        f"{ROBOT_BRIDGE_URL}/move/{direction}?steps={steps}", method="POST"
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=502, detail=detail) from error
    except URLError as error:
        raise HTTPException(
            status_code=503,
            detail=f"Astro Mission Companion is offline at {ROBOT_BRIDGE_URL}.",
        ) from error
    return {
        "direction": direction,
        "steps": steps,
        "status": "completed",
        "result": result,
    }


robot_buddy_app.mount(
    "/assets",
    StaticFiles(directory=REACT_DIST, html=True),
    name="robot_buddy_assets",
)


class RobotBuddyPlugin(AirflowPlugin):
    name = "astro_mission_companion"

    fastapi_apps = [
        {
            "app": robot_buddy_app,
            "url_prefix": "/robot-buddy-api",
            "name": "Astro Mission Companion API",
        }
    ]

    react_apps = [
        {
            "name": "Astro Mission Companion",
            "bundle_url": "/robot-buddy-api/assets/main.umd.cjs?theme=astro-rover-v1",
            "destination": "nav",
            "url_route": "robot-buddy",
            "category": "browse",
            "nav_top_level": True,
        }
    ]
