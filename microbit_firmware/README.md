# Astro Mission Companion — micro:bit Firmware

This directory contains the MicroPython firmware that runs on the micro:bit in
the Keyestudio KS4036 rover. It is the hardware-facing layer of Astro Mission
Control: it drives the motors and RGB lights, reads the ultrasonic sensor,
animates the optional OLED, and accepts commands from the Mac over USB serial.

The Airflow stack does not communicate with the micro:bit directly. Commands
follow this path:

```text
Airflow DAG or Mission Control UI
             ↓ HTTP
        usb_bridge.py on the Mac
             ↓ subprocess
        usb_controller.py
             ↓ USB serial at 115200 baud
        microbit_firmware/main.py
             ↓ I2C and GPIO
        KS4036 rover hardware
```

## How the firmware works

`main.py` is a small, synchronous command server. It owns the rover hardware
for as long as the micro:bit is powered and translates one serial command at a
time into motor, sensor, light, display, or sound operations.

### 1. Startup leaves the rover safe

The firmware initializes the USB UART at `115200` baud and immediately writes
zero to all four motor registers. It then scans the I2C bus for an optional OLED,
draws its idle eyes when one is present, and emits the `READY` and `OLED` status
lines. The rover does not move during startup.

### 2. The main loop assembles serial commands

The bottom of `main.py` contains the firmware's event loop. It reads the UART
one byte at a time, accumulating bytes until it receives a carriage return or
newline. The completed ASCII line is passed to `handle()`. While no command is
waiting, the loop updates the OLED's idle blink animation.

```text
USB bytes → newline received → handle(command) → hardware action → OK/ERR reply
```

Commands execute synchronously: the firmware finishes the current action and
stops its motors before reading the next command. The Mac controller therefore
waits for the terminal `OK ...` or `ERR ...` response before considering a
request complete.

### 3. `handle()` validates and dispatches the request

`handle()` lowercases and tokenizes the line, extracts an optional
`duration=SECONDS` value, validates counts or intensity, and dispatches to the
matching function:

| Command family | Firmware functions | Hardware used |
| --- | --- | --- |
| Movement | `forward()`, `backward()`, `left()`, `right()` | Motor controller and LED matrix |
| Sensing | `distance_cm()` | P14 trigger and P15 echo |
| Expressions | `happy()`, `sad()`, `play()` | Motors, RGB lights, OLED, LEDs, and speaker |
| Interaction | `nudge()` | Motors, ultrasonic sensor, microphone, displays, lights, and speaker |

Invalid input returns a specific error such as `ERR MOVE 1 TO 20` without
starting the requested action.

### 4. Motor commands become timed I2C writes

The Keyestudio motor controller is an I2C device at address `0x30` (`48` in the
code). The helper `reg(register, value)` writes a motor or RGB value to one of
its registers. Forward and backward movement energize opposite motor channels;
turning drives the wheels in opposite directions so the rover rotates.

A movement count is implemented as repeated `100 ms` pulses. For example,
`forward 5` applies forward motor values five times and then calls `stop()`,
which clears all four motor registers. Forward, backward, nudge, and timed
expression paths also use `finally` cleanup so their motors are cleared if the
action exits early; each individual turn pulse explicitly stops after its
sleep completes.

### 5. Results travel back up the stack

After the hardware function completes, `handle()` creates one response line,
such as `OK FORWARD 5` or `OK DISTANCE 29`. The UART loop writes it over USB;
`usb_controller.py` reads that terminal line; and `usb_bridge.py` exposes the
result to Airflow as an HTTP response. This gives each Airflow movement or
sensor task a definite completion signal from the physical rover.

## Supported hardware

- Keyestudio KS4036 micro:bit smart rover
- micro:bit V2, required for the built-in microphone used by `nudge`
- Ultrasonic sensor connected to the rover's P14/P15 interface
- Optional 128×64 SSD1306-compatible I2C OLED
- USB data cable connecting the micro:bit to the Mac

The optional OLED is detected automatically at I2C address `0x3C` or `0x3D`.
The KS4036 motor and light controller uses the separate I2C address `0x30`.

## Flash the firmware

1. Turn the rover's motor power off or lift its wheels clear of the surface.
2. Connect the micro:bit to the Mac with a USB data cable.
3. Open the [micro:bit Python Editor](https://python.microbit.org/).
4. Replace the editor contents with [`main.py`](main.py).
5. Select **Send to micro:bit** and wait for flashing to complete.
6. Close the editor's serial console before using `usb_controller.py`.
7. Reinstall the micro:bit if necessary, connect USB, and power on the rover.

At startup, the firmware stops all motors and sends:

```text
READY KS4036 V2
OLED IDLE
```

If no supported OLED is found, the second line is:

```text
OLED NOT FOUND
```

## Serial protocol

The firmware listens at `115200` baud for newline-terminated ASCII commands.
Commands are case-insensitive because the firmware normalizes them to lower
case. Each completed command returns one terminal line beginning with `OK` or
`ERR`.

| Command | Valid value | Behavior | Example response |
| --- | --- | --- | --- |
| `forward N` | 1–20 | Move forward for `N` motor pulses | `OK FORWARD 5` |
| `backward N` | 1–20 | Move backward for `N` motor pulses | `OK BACKWARD 5` |
| `back N` | 1–20 | Alias for backward | `OK BACK 5` |
| `left N` | 1–20 | Turn left for `N` pulses | `OK LEFT 2` |
| `right N` | 1–20 | Turn right for `N` pulses | `OK RIGHT 2` |
| `distance` | None | Read the ultrasonic sensor in centimetres | `OK DISTANCE 29` |
| `happy N` | Intensity 1–5 | Play the happy movement, light, OLED, and sound routine | `OK HAPPY` |
| `sad N` | Intensity 1–5 | Play the sad routine | `OK SAD` |
| `nudge N` | 1–20 seconds | Approach a nearby object, then wait for clap approval | `OK APPROVED` |

Movement and emotion values are optional. Movement defaults to `1`, emotion
intensity defaults to `3`, and `nudge` defaults to `8` seconds.

Examples using the repository's Mac controller:

```bash
python3 usb_controller.py forward 5
python3 usb_controller.py left 2
python3 usb_controller.py distance
python3 usb_controller.py happy 3
```

## Movement model

The rover does not have wheel encoders. A “step” is a timed motor pulse of
`100 ms`, not a fixed distance. For example, `forward 5` drives the motors for
approximately 500 ms before stopping.

Travel varies with:

- Battery charge
- Floor material and wheel slip
- Motor differences
- Rover weight
- Wheel alignment

The firmware applies a small right-motor trim to help straight-line travel:

```python
LEFT_MOTOR_TRIM = 0
RIGHT_MOTOR_TRIM = -4
```

Tune these constants cautiously if the rover consistently pulls to one side.
The Airflow DAG stores step counts in XCom so it can issue the same number of
backward pulses when returning to base; this is open-loop retracing rather than
precise odometry.

## Ultrasonic distance measurement

The sensor trigger is connected to P14 and its echo to P15. The firmware:

1. Sends a 10-microsecond trigger pulse on P14.
2. Measures the returning echo pulse on P15.
3. Divides the round-trip time in microseconds by 58.

```python
pulse = machine.time_pulse_us(pin15, 1, 35000)
distance = pulse // 58 if pulse > 0 else 0
```

Sound travels approximately `0.0343 cm/µs`. Because it travels to the object
and back, the one-way distance is approximately:

```text
distance_cm = echo_time_us × 0.0343 ÷ 2
            ≈ echo_time_us ÷ 58
```

For example, an echo time of 580 µs represents an object about 10 cm away.
A result of `0` means no valid echo was received within the 35 ms timeout; it
must not be interpreted as a clear path or a literal zero-centimetre distance.

## OLED and micro:bit display

When the optional OLED is present, it shows animated eyes while idle and face
frames during happy, sad, and nudge behaviors. I2C display failures are caught
so the rover can continue operating without the OLED.

The micro:bit LED matrix indicates the current physical action:

- North arrow — moving forward or running nudge
- South arrow — moving backward
- West arrow — turning left
- East arrow — turning right
- Happy or sad face — emotion routine
- Music note — nudge is waiting for clap approval

## Nudge and clap approval

The `nudge` behavior demonstrates sensor-driven human interaction:

1. Between 10 and 35 cm, the rover makes short forward movements.
2. Between 4 and 10 cm, it stops and listens for a clap.
3. A detected clap produces `OK APPROVED` and a success animation.
4. If approval is not detected before the deadline, it returns
   `ERR APPROVAL TIMEOUT`.

The microphone threshold is calculated from ambient sound when listening
begins, with safe minimum and maximum limits.

## Timed behaviors

`happy`, `sad`, and `nudge` understand an optional `duration=SECONDS` token:

```text
happy 3 duration=10
sad 2 duration=5
nudge 8 duration=12
```

For happy and sad, the duration limits and repeats the routine. For nudge, it
sets the active approach duration. The current movement handlers use their
step count and do not use the `duration` token.

## Safety behavior

- Motors are stopped immediately during firmware startup.
- Movement routines use `finally` blocks to stop motors after completion.
- Emotion routines stop motors and sound when their deadline expires.
- Movement commands are restricted to 1–20 steps.
- Ultrasonic timeouts return an invalid reading instead of claiming the path is
  clear.

Always test with the rover on the floor in a clear area, begin with one or two
steps, and keep it within reach. Disconnect motor power before modifying or
reconnecting hardware.

## Troubleshooting

### No serial response

- Confirm the USB cable supports data.
- Close the micro:bit Python Editor serial console.
- Reflash this `main.py` and reconnect the micro:bit.
- Confirm `usb_controller.py` selected the correct `/dev/cu.usbmodem*` port.

### `OLED NOT FOUND`

- The OLED is optional; movement and sensing still work.
- Check 3V, GND, SDA, and SCL connections.
- Confirm the module uses I2C address `0x3C` or `0x3D`.

### Distance is always zero

- Confirm the ultrasonic trigger and echo connections.
- Test against a broad, solid object rather than angled or soft material.
- Keep the sensor still while taking a reading.
- Check that the sensor has unobstructed forward visibility.

### Rover moves in the wrong direction

- Verify the micro:bit and motor connectors are installed in the expected
  orientation.
- Test `forward 1`, `backward 1`, `left 1`, and `right 1` individually.
- Do not increase step counts until every direction is correct.
