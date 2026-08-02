# Python control for the Keyestudio KS4036

For the complete command reference, HTTP bridge setup, and troubleshooting,
see [USB_CONTROLLER_README.md](USB_CONTROLLER_README.md).

This first version controls both RGB headlights on the KS4036 smart car from
Python over the micro:bit's USB serial connection.

## 1. Put the firmware on the micro:bit

1. Remove the micro:bit from the car, or leave the car's power switch **off**
   while flashing.
2. Open the [micro:bit Python Editor](https://python.microbit.org/).
3. Replace the editor contents with `main.py` from this repository.
4. Connect the micro:bit by USB and choose **Send to micro:bit**.
5. Put the micro:bit back in the car and turn the car's power switch on.
   Keep USB connected to the computer.

The micro:bit display shows `N` when the headlights are off and `Y` when they
are on.

If a 128x64 SSD1306 I2C OLED is connected to `GND`, `3V`, `SCL`, and `SDA`,
the firmware detects it at address `0x3C` or `0x3D` and shows **HELLO** at
startup. Upload `main.py` to the micro:bit. The OLED shares
the I2C bus with the car controller, whose separate address is `0x30`.

The car's controller remembers the last headlight state across a micro:bit
serial reset. The lights therefore remain on until `lights-off` is sent or the
car's power is removed.

## 2. Install the computer-side dependency

```bash
python3 -m pip install -r requirements.txt
```

## 3. Control the headlights

Run one command:

```bash
python3 usb_controller.py lights-on
python3 usb_controller.py lights-off
```

Or enter interactive mode:

```bash
python3 usb_controller.py
```

Move forward five short steps and stop:

```bash
python3 usb_controller.py forward 5
python3 usb_controller.py backward 5
```

The car uses ordinary DC motors, so a "step" means a 250 ms movement pulse
followed by a 100 ms pause. Between 1 and 20 steps may be requested.

Give the car one very short forward nudge:

```bash
python3 usb_controller.py nudge
```

Multiple nudges can be requested with `nudge 3`. Each nudge is a 100 ms motor
pulse followed by an immediate stop.

Play the happy behaviour:

```bash
python3 usb_controller.py happy
```

The car shows a smile, wiggles left and right three times, alternates its RGB
headlights, then stops with both headlights yellow.

Play the sad behaviour:

```bash
python3 usb_controller.py sad
```

The car shows a sad face, slowly pulses its red headlights, makes two small
backward shuffles, gently shakes left and right, then stops with dim red
headlights.

Other emotions:

```bash
python3 usb_controller.py working
python3 usb_controller.py nervous
python3 usb_controller.py angry
python3 usb_controller.py sleepy
python3 usb_controller.py neutral
python3 usb_controller.py celebrate
python3 usb_controller.py recovered
python3 usb_controller.py airflow
```

- `working` — calm blue breathing lights; no movement
- `nervous` — confused face, alternating yellow lights, and a quick jitter
- `angry` — angry face, flashing red lights, and a forceful shake
- `sleepy` — sleeping face and a slow fade to dim blue; no movement
- `neutral` — resting face, dim white headlights, and stopped motors
- `celebrate` — colourful victory dance for a complete DAG success
- `recovered` — green lights and a confident move after recovery
- `airflow` — rotating 5×5 pinwheel with Airflow-inspired RGB colours

Emotion intensity can be set from 1 (subtle) to 5 (dramatic):

```bash
python3 usb_controller.py happy 1
python3 usb_controller.py angry 5
python3 usb_controller.py airflow 4 --duration 10
```

Any action can be given a duration in seconds:

```bash
python3 usb_controller.py happy 3 --duration 10
python3 usb_controller.py lights-on --duration 5
python3 usb_controller.py forward --duration 2.5
```

Timed emotions repeat until their deadline. Timed headlights restore their
previous colour afterward. For timed forward/backward commands, duration
replaces the step count and the motors stop automatically. Continuous movement
is limited to 10 seconds; other actions are limited to 60 seconds.

Run the complete emotion showcase:

```bash
python3 usb_controller.py demo
```

Each emotion has a short tune that plays alongside its lights and movement.
Sound can be enabled or muted without reflashing:

```bash
python3 usb_controller.py sound-on
python3 usb_controller.py sound-off
```

On a micro:bit V2, sound uses the built-in speaker. On a micro:bit V1, the
`music` module outputs through pin P0 and requires an external buzzer/speaker.

Emotion routines always stop the motors when they finish and restore the
headlight colour that was active before the emotion. `neutral` and `demo` are
intentional resting-state commands and leave their final lighting in place.

The script normally finds the micro:bit automatically. If it cannot, provide
the serial device explicitly:

```bash
python3 usb_controller.py --port /dev/cu.usbmodem1102 on
```

On macOS, `ls /dev/cu.usbmodem*` will show likely device names. Do not keep the
Python Editor's serial console open while running the controller, because only
one program can use the serial port at a time.

## Protocol

The computer sends newline-terminated ASCII commands:

- `on` — both RGB headlights turn white
- `off` — both RGB headlights turn off
- `lights-on` / `lights-off` — explicit aliases for the two commands above
- `stop` — clear the retained motor PWM state
- `forward N` — move forward for `N` short pulses, then stop
- `backward N` (or `back N`) — reverse for `N` short pulses, then stop
- `nudge N` — make `N` very short forward movements; the default is one
- `happy` — smile, wiggle, animate the headlights, and stop safely
- `sad` — pulse red, shuffle backward, shake left/right, and stop safely
- `working` — calm blue breathing animation
- `nervous` — yellow jitter animation
- `angry` — red forceful shake animation
- `sleepy` — dim blue resting animation
- `neutral` — enter the persistent resting state
- `celebrate` — colourful full-success dance
- `recovered` — green recovery animation
- `airflow` — spin an Airflow-inspired pinwheel on the LED matrix
- `demo` — preview the complete emotion library
- `sound-on` / `sound-off` — enable or mute emotion tunes

The micro:bit replies with `OK LIGHTS ON`, `OK LIGHTS OFF`, or an error.
