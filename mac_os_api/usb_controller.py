"""Control a USB-connected Keyestudio KS4036 micro:bit rover."""

import argparse
import time

import serial
from serial.tools import list_ports


def find_microbit_port():
    ports = list(list_ports.comports())
    likely = [
        port
        for port in ports
        if "micro:bit" in (port.description or "").lower()
        or "mbed" in (port.description or "").lower()
        or (port.vid, port.pid) == (0x0D28, 0x0204)
    ]
    if likely:
        return likely[0].device
    if len(ports) == 1:
        return ports[0].device
    found = ", ".join(port.device for port in ports) or "none"
    raise RuntimeError(
        "Could not identify a micro:bit serial port. "
        "Use --port PORT. Detected ports: " + found
    )


def send(ser, command):
    ser.reset_input_buffer()
    ser.write((command + "\n").encode("ascii"))
    ser.flush()
    response = ""
    # Ignore asynchronous READY/OLED messages and wait for the command's
    # terminal response. This is important when each HTTP request reopens USB.
    while True:
        line = ser.readline().decode("ascii", errors="replace").strip()
        if not line:
            break
        print(line)
        if line.startswith(("OK ", "ERR ", "Traceback")):
            response = line
            break
    if not response:
        print("(command sent; no terminal reply)")
    if response.startswith("Traceback"):
        original_timeout = ser.timeout
        ser.timeout = 0.25
        while True:
            detail = ser.readline().decode("ascii", errors="replace").strip()
            if not detail:
                break
            print(detail)
        ser.timeout = original_timeout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        choices=(
            "nudge",
            "happy",
            "sad",
            "forward",
            "backward",
            "left",
            "right",
            "distance",
        ),
    )
    parser.add_argument(
        "value",
        nargs="?",
        type=int,
        help="movement count (1-20) or emotion intensity (1-5)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        help="run the action for this many seconds",
    )
    parser.add_argument("--port", help="serial device, e.g. /dev/cu.usbmodem1102")
    args = parser.parse_args()

    port = args.port or find_microbit_port()
    if args.duration is not None and args.duration <= 0:
        parser.error("--duration must be greater than zero")
    timeout = (
        5
        if args.command == "distance"
        else max(45 if args.command == "nudge" else 30, (args.duration or 0) + 10)
    )
    with serial.Serial(port, 115200, timeout=timeout) as ser:
        time.sleep(0.5)
        print("Connected to", port)

        if args.command:
            command = args.command
            if args.command == "nudge":
                default_count = 8
                command += " " + str(
                    args.value if args.value is not None else default_count
                )
            elif args.command in (
                "happy",
                "sad",
            ):
                command += " " + str(args.value if args.value is not None else 3)
            elif args.command in ("forward", "backward", "left", "right"):
                count = args.value if args.value is not None else 1
                if not 1 <= count <= 20:
                    parser.error("movement count must be between 1 and 20")
                command += " " + str(count)
            elif args.command == "distance":
                if args.value is not None:
                    parser.error("distance does not accept a numeric value")
            elif args.value is not None:
                parser.error("this command does not accept a numeric value")
            if args.duration is not None:
                command += " duration=" + str(args.duration)
            send(ser, command)
            return

        print(
            "Enter an emotion (happy, sad, working, nervous, angry, sleepy, "
            "celebrate, recovered, airflow, neutral), demo, "
            "a movement command, lights-on, lights-off, stop, or quit."
        )
        while True:
            command = input("> ").strip().lower()
            if command in ("quit", "exit", "q"):
                return
            raw_parts = command.split()
            duration_parts = [
                part for part in raw_parts if part.startswith("duration=")
            ]
            parts = [
                part for part in raw_parts if not part.startswith("duration=")
            ]
            has_valid_duration = len(duration_parts) <= 1
            if duration_parts:
                try:
                    has_valid_duration = float(duration_parts[0].split("=", 1)[1]) > 0
                except ValueError:
                    has_valid_duration = False
            is_movement = (
                len(parts) in (1, 2)
                and parts[0] in (
                    "forward",
                    "backward",
                    "back",
                    "left",
                    "right",
                    "nudge",
                )
                and (len(parts) == 1 or parts[1].isdigit())
            )
            is_emotion = (
                len(parts) in (1, 2)
                and parts[0]
                in (
                    "happy",
                    "sad",
                    "working",
                    "nervous",
                    "angry",
                    "sleepy",
                    "celebrate",
                    "recovered",
                    "airflow",
                )
                and (len(parts) == 1 or parts[1].isdigit())
            )
            base_command = " ".join(parts)
            if has_valid_duration and (
                base_command in (
                "on",
                "off",
                "lights-on",
                "lights-off",
                "stop",
                "happy",
                "sad",
                "working",
                "nervous",
                "angry",
                "sleepy",
                "neutral",
                "demo",
                "sound-on",
                "sound-off",
                "distance",
                )
                or is_movement
                or is_emotion
            ):
                send(ser, command)
            else:
                print(
                    "Please enter an emotion, nudge N, forward N, backward N, "
                    "left N, right N, distance, "
                    "lights-on, "
                    "lights-off, stop, or quit."
                )


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        raise SystemExit("Error: " + str(error))
