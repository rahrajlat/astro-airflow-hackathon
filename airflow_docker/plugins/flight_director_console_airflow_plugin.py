"""Airflow 3 plugin for the rover Flight Director Console."""

import mimetypes
import os
from pathlib import Path

from airflow.plugins_manager import AirflowPlugin
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


CONSOLE_DIST = Path("/opt/airflow/widgets/flight-director-console/dist")
ROVER_CAPTURE_DIR = Path(
    os.getenv("ROVER_CAPTURE_MOUNT_PATH", "/opt/airflow/rover_captures")
)

mimetypes.add_type("application/javascript", ".cjs")
flight_director_app = FastAPI(title="Flight Director Console API")


@flight_director_app.get("/health")
def health():
    """Report whether the dedicated console service is available."""
    return {"status": "ok"}


@flight_director_app.get("/rover-captures/{filename}")
def rover_capture_image(filename: str):
    """Serve one immutable rover JPEG used as HITL decision evidence."""
    candidate = Path(filename)
    if (
        candidate.name != filename
        or not filename.startswith("rover-")
        or candidate.suffix.lower() not in {".jpg", ".jpeg"}
    ):
        raise HTTPException(status_code=404, detail="Rover capture not found")

    capture_root = ROVER_CAPTURE_DIR.resolve()
    image_path = (capture_root / filename).resolve()
    if image_path.parent != capture_root or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Rover capture not found")

    return FileResponse(
        image_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


flight_director_app.mount(
    "/assets",
    StaticFiles(directory=CONSOLE_DIST, html=True),
    name="flight_director_assets",
)


class FlightDirectorConsoleAirflowPlugin(AirflowPlugin):
    """Register the console as a focused, native Airflow React application."""

    name = "flight_director_console"
    fastapi_apps = [
        {
            "app": flight_director_app,
            "url_prefix": "/flight-director-api",
            "name": "Flight Director Console API",
        }
    ]
    react_apps = [
        {
            "name": "Flight Director Console",
            "bundle_url": "/flight-director-api/assets/flight-director-console-v1.umd.cjs",
            "destination": "nav",
            "url_route": "flight-director-console",
            "category": "browse",
            "nav_top_level": True,
        }
    ]
