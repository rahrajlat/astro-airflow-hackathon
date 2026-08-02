# USB Rover Controller

`usb_controller.py` is the Mac-side command-line controller for the
Keyestudio KS4036 micro:bit rover. It discovers the rover's USB serial port,
sends newline-delimited commands to the firmware in `main.py`, and prints the
firmware response.

It can be used directly from a terminal or indirectly through `usb_bridge.py`
for Airflow and the Astro Mission Companion UI.

## Requirements

- A Keyestudio KS4036 rover with a micro:bit
- The repository's `main.py` flashed to the micro:bit
- The rover powered on and connected to the Mac by USB
- Python 3 and `pyserial`

Install the Python dependencies from the repository root:

```bash
python3 -m pip install -r requirements.txt
```

If another application has the micro:bit serial console open, close it first.
Only one process can control the serial port at a time.

## Quick start

Move the rover using discrete movement steps:

```bash
python3 usb_controller.py forward 5
python3 usb_controller.py backward 5
python3 usb_controller.py left 2
python3 usb_controller.py right 2
```

Read the ultrasonic sensor:

```bash
python3 usb_controller.py distance
```

Run an animated rover emotion:

```bash
python3 usb_controller.py happy 3
python3 usb_controller.py sad 3
```

The controller automatically stops after each movement command. A movement
count must be between 1 and 20. It represents a short motor pulse, not a fixed
physical distance; wheel slip, battery level, and the surface affect travel.

## Command reference

```text
python3 usb_controller.py COMMAND [VALUE] [--duration SECONDS] [--port DEVICE]
```

| Command | Value | Default | Purpose |
| --- | ---: | ---: | --- |
| `forward` | 1–20 steps | 1 | Move forward |
| `backward` | 1–20 steps | 1 | Move backward |
| `left` | 1–20 steps | 1 | Turn left |
| `right` | 1–20 steps | 1 | Turn right |
| `distance` | None | — | Read forward ultrasonic distance in centimetres |
| `nudge` | Count | 8 | Run the proximity-and-clap interaction |
| `happy` | Intensity 1–5 | 3 | Run the happy animation |
| `sad` | Intensity 1–5 | 3 | Run the sad animation |

`--duration` adds a positive time limit understood by the rover firmware:

```bash
python3 usb_controller.py happy 4 --duration 10
python3 usb_controller.py forward 1 --duration 2.5
```

## Interactive mode

Run the script without a command:

```bash
python3 usb_controller.py
```

Interactive mode accepts movement and sensor commands plus the firmware's
extended behaviours:

```text
forward 5             backward 5
left 2                right 2
distance              stop
lights-on             lights-off
happy 3               sad 3
working               nervous
angry                 sleepy
celebrate             recovered
airflow               neutral
demo                   sound-on
sound-off              quit
```

A duration can be appended in firmware format:

```text
happy 4 duration=10
forward 1 duration=2.5
```

## Selecting the serial port

The controller normally detects a micro:bit or mbed USB device automatically.
If detection is ambiguous, specify the device explicitly:

```bash
python3 usb_controller.py forward 1 --port /dev/cu.usbmodem1102
```

On macOS, list likely ports with:

```bash
ls /dev/cu.usbmodem*
```

## Using the HTTP bridge

`usb_bridge.py` exposes the controller to Airflow running in Docker. Start it
on the Mac from the repository root:

```bash
python3 usb_bridge.py
```

The bridge listens on port `8765`. Example requests:

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/distance
curl -X POST "http://127.0.0.1:8765/move/forward?steps=5"
curl -X POST "http://127.0.0.1:8765/move/backward?steps=5"
```

Airflow containers reach the Mac bridge at
`http://host.docker.internal:8765`. The bridge serializes requests so two UI or
DAG actions cannot write to USB simultaneously.

## USB camera and vision analysis

The bridge can capture a forward-facing USB-camera frame when the rover finds
an obstacle. Install the updated requirements and make sure macOS grants camera
permission to the terminal or Python process running the bridge:

```bash
python3 -m pip install -r requirements.txt
ollama pull gemma3:4b
python3 usb_bridge.py
```

Check the camera and take a test photograph:

```bash
curl http://127.0.0.1:8765/camera/status
curl -X POST http://127.0.0.1:8765/camera/capture
open http://127.0.0.1:8765/camera/latest
```

Camera captures are stored in `rover_captures/` and excluded from Git. Docker
Compose mounts that directory read-only at `/opt/airflow/rover_captures`. The
rover DAG reads the JPEG there and sends it directly to Gemma; neither the JPEG
nor its base64 representation is stored in Airflow XCom.

The default camera is index `0`, at 1280×720. If the Mac's built-in camera is
selected instead of the USB camera, stop the bridge and restart it with another
index:

```bash
USB_CAMERA_INDEX=1 python3 usb_bridge.py
```

Optional settings are:

```bash
USB_CAMERA_INDEX=1
USB_CAMERA_WIDTH=1280
USB_CAMERA_HEIGHT=720
ROVER_CAPTURE_DIR=/path/to/captures
ROVER_VISION_MODEL=gemma3:4b
```

If `ROVER_CAPTURE_DIR` is customized, set the same host directory when
recreating Compose so the Mac bridge and Airflow share the same files.

The `planet_exploration_rover` DAG captures a frame after ultrasonic detection,
sends the frame and measured distance to the local Ollama vision model, and
shows the structured assessment in the HITL decision task. The human still
chooses the physical action, including returning to base using the outbound
step count stored in XCom.

## Serial protocol

The controller opens the port at `115200` baud and sends ASCII commands ending
in a newline. It ignores startup messages such as `READY` and waits for a
terminal response beginning with `OK`, `ERR`, or `Traceback`.

Typical distance response:

```text
OK DISTANCE 29
```

A distance of `0` means the ultrasonic sensor received no valid echo. It does
not mean that the path is clear.

## Troubleshooting

### The micro:bit is not detected

- Confirm the USB cable supports data, not only charging.
- Confirm the micro:bit appears under `/dev/cu.usbmodem*`.
- Close the micro:bit Python Editor serial console.
- Pass the exact device using `--port`.

### Permission denied or port busy

Close any other terminal, editor, or bridge process using the serial port. Run
only one instance of `usb_controller.py` unless commands are coordinated by
`usb_bridge.py`.

### Distance returns zero or the bridge reports 502

- Check that the ultrasonic sensor is connected correctly.
- Point it at a broad, solid surface for testing.
- Avoid measuring immediately after motor movement; vibration and electrical
  noise can disrupt a reading.
- Verify the firmware in `main.py` is the current version.

### The rover travels unevenly

A step is time-based and is not wheel-encoder positioning. Charge the battery,
test on a level surface, and adjust the motor trim constants in `main.py` if
the rover consistently pulls to one side.

## Safety

Test with the rover on the floor in a clear area. Keep it within reach, use
small step counts first, and send `stop` in interactive mode if movement does
not finish as expected. The ultrasonic sensor should be treated as a safety
aid, not as a guarantee of collision avoidance.
