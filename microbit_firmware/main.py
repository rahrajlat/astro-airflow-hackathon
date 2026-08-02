from microbit import Image, display, i2c, microphone, pin14, pin15, running_time, sleep, uart
from utime import sleep_us
import machine
import music
OLED_ADDRS = (60, 61)
OLED_LETTERS = 'ABCDEFGHIKLNOPRSTUVWY'
OLED_FONT = '7e1111117e7f494949363e414141227f4141221c7f494949417f090909013e4149497a7f0808087f00417f41007f081422417f404040407f020c107f3e4141413e7f090909067f09192946464949493101017f01013f4040403f1f2040201f7f2018207f0708700807'
EYE_OPEN = '00000000e0f8cceefefcf8e00000000000000000071f3f7f7f3f1f0700000000'
EYE_CLOSED = '00000080c0808080808080c08000000000000001030101010101010301000000'
HAPPY_MOUTH = '00000000000000003060c080000000000000000000000000000000000000000080c06030000000000000000000000000000000000000000103060c1830306060c0c0c0c060603030180c0603010000000000000000000000'
SAD_MOUTH = '0000000000000000000000000000008080c0c060603030306060c0c080800000000000000000000000000000000000000000000000180c06060303010100000000000000000000000101030306060c180000000000000000'
NUDGE_MOUTH = '000000000000000000000000000000000000c060303030303060c0000000000000000000000000000000000000000000000000000000000000000000000003060c0c0c0c0c06030000000000000000000000000000000000'
OLED_ADDR = None
NEXT_BLINK = 0
BLINK_CLOSED = False

def oled_command(address, *values):
    i2c.write(address, bytearray((0,) + values))

def oled_data(address, values):
    for start in range(0, len(values), 16):
        i2c.write(address, bytearray((64,)) + values[start:start + 16])

def oled_show(word):
    global OLED_ADDR
    if OLED_ADDR is None:
        devices = i2c.scan()
        for candidate in OLED_ADDRS:
            if candidate in devices:
                OLED_ADDR = candidate
                break
    if OLED_ADDR is None:
        return False
    address = OLED_ADDR
    oled_command(address, 174, 213, 128, 168, 63, 211, 0, 64, 141, 20, 32, 0, 161, 200, 218, 18, 129, 127, 217, 241, 219, 64, 164, 166, 175)
    oled_command(address, 33, 0, 127, 34, 0, 7)
    blank = bytearray(128)
    for _ in range(8):
        oled_data(address, blank)
    if word in ('IDLE', 'BLINK'):
        if word == 'BLINK':
            eye = EYE_CLOSED
        else:
            eye = EYE_OPEN
        eyes = bytearray()
        for page in range(2):
            start = page * 32
            for eye_number in range(2):
                for offset in range(start, start + 32, 2):
                    eyes.append(int(eye[offset:offset + 2], 16))
                if eye_number == 0:
                    for _ in range(12):
                        eyes.append(0)
        oled_command(address, 33, 42, 85, 34, 3, 4)
        oled_data(address, eyes)
        return True
    if word in ('HAPPY1', 'HAPPY2', 'SAD1', 'SAD2', 'NUDGE1', 'NUDGE2'):
        source = EYE_CLOSED if word[-1] == '2' else EYE_OPEN
        if word[0] == 'H':
            mouth = HAPPY_MOUTH
        elif word[0] == 'S':
            mouth = SAD_MOUTH
        else:
            mouth = NUDGE_MOUTH
        face = bytearray()
        for page in range(2):
            for eye_number in range(2):
                for column in range(16):
                    offset = page * 32 + column * 2
                    face.append(int(source[offset:offset + 2], 16))
                if eye_number == 0:
                    for _ in range(12):
                        face.append(0)
        for offset in range(0, len(mouth), 2):
            face.append(int(mouth[offset:offset + 2], 16))
        oled_command(address, 33, 42, 85, 34, 2, 5)
        oled_data(address, face)
        return True
    top = bytearray()
    bottom = bytearray()
    for character in word:
        font_start = OLED_LETTERS.index(character) * 10
        for font_offset in range(font_start, font_start + 10, 2):
            column = int(OLED_FONT[font_offset:font_offset + 2], 16)
            expanded = 0
            for bit in range(7):
                if column & 1 << bit:
                    expanded |= 3 << bit * 2
            low = expanded & 255
            high = expanded >> 8 & 255
            top.append(low)
            top.append(low)
            bottom.append(high)
            bottom.append(high)
        top.append(0)
        top.append(0)
        bottom.append(0)
        bottom.append(0)
    start = (128 - len(top)) // 2
    oled_command(address, 33, start, start + len(top) - 1, 34, 3, 4)
    oled_data(address, top)
    oled_data(address, bottom)
    return True

def oled_emotion(word):
    try:
        oled_show(word)
    except OSError:
        pass

def idle_blink():
    global NEXT_BLINK, BLINK_CLOSED
    now = running_time()
    if now >= NEXT_BLINK:
        BLINK_CLOSED = not BLINK_CLOSED
        oled_emotion('BLINK' if BLINK_CLOSED else 'IDLE')
        NEXT_BLINK = now + (180 if BLINK_CLOSED else 2200)
CAR = 48
MOTOR_REGS = (1, 2, 3, 4)
FWD_SPEED = 70
STEP_PAUSE_MS = 100
NUDGE_DURATION_MS = 180
HAPPY_WIGGLE_MS = 140
SAD_SPEED = 45
SAD_SHUFFLE_MS = 180
SAD_SHAKE_MS = 250
LEFT_MOTOR_TRIM = 0
RIGHT_MOTOR_TRIM = -4
INTENSITY = 3
SOUND = True
left_state = (255, 255, 255)
right_state = (255, 255, 255)
DEADLINE = None

class ActionFinished(Exception):
    pass

def reg(register, value):
    i2c.write(CAR, bytearray([register, value & 255]), repeat=False)

def stop():
    for register in MOTOR_REGS:
        reg(register, 0)

def mv(speed, trim):
    return max(0, min(255, speed + trim))

def ec(base):
    return max(1, (base * INTENSITY + 2) // 3)

def et(milliseconds):
    return max(40, milliseconds * (INTENSITY + 2) // 5)

def es(speed):
    return max(25, min(100, speed + (INTENSITY - 3) * 8))

def tune(notes, loop=False):
    if SOUND:
        music.play(notes, wait=False, loop=loop)

def nap(milliseconds):
    if DEADLINE is None:
        sleep(milliseconds)
        return
    remaining = DEADLINE - running_time()
    if remaining <= 0:
        raise ActionFinished()
    sleep(min(milliseconds, remaining))
    if milliseconds >= remaining:
        raise ActionFinished()

def distance_cm():
    pin14.write_digital(0)
    sleep_us(2)
    pin14.write_digital(1)
    sleep_us(10)
    pin14.write_digital(0)
    pulse = machine.time_pulse_us(pin15, 1, 35000)
    return pulse // 58 if pulse > 0 else 0

def nudge(seconds):
    display.show(Image.ARROW_N)
    end = running_time() + seconds * 1000
    frame = False
    approved = False
    waiting_for_clap = False
    clap_threshold = 180
    listen_after = 0
    try:
        while running_time() < end:
            if waiting_for_clap:
                stop()
                display.show(Image.MUSIC_QUAVER)
                if running_time() >= listen_after and microphone.sound_level() >= clap_threshold:
                    approved = True
                    break
                sleep(20)
                continue
            distance = distance_cm()
            oled_emotion('NUDGE2' if frame else 'NUDGE1')
            frame = not frame
            if 4 <= distance <= 10:
                waiting_for_clap = True
                end = running_time() + 25000
                clap_threshold = max(120, min(230, microphone.sound_level() + 60))
                listen_after = running_time() + 300
                continue
            if 10 < distance <= 35:
                reg(1, 0)
                reg(2, mv(FWD_SPEED, LEFT_MOTOR_TRIM))
                reg(3, mv(FWD_SPEED, RIGHT_MOTOR_TRIM))
                reg(4, 0)
                sleep(NUDGE_DURATION_MS)
                stop()
            else:
                stop()
                sleep(120)
    finally:
        stop()
    if approved:
        oled_emotion('HAPPY1')
        both(255, 0, 255)
        tune(['C5:1', 'E5:1', 'G5:2'])
        display.show(Image.YES)
        sleep(500)
        both(255, 255, 255)
    else:
        display.show('S')
    return approved

def left_light(red, green, blue):
    global left_state
    left_state = (red, green, blue)
    reg(8, red)
    reg(7, green)
    reg(6, blue)

def right_light(red, green, blue):
    global right_state
    right_state = (red, green, blue)
    reg(9, red)
    reg(10, green)
    reg(5, blue)

def both(red, green, blue):
    left_light(red, green, blue)
    right_light(red, green, blue)

def turn_left(speed, duration):
    reg(1, mv(speed, LEFT_MOTOR_TRIM))
    reg(2, 0)
    reg(3, mv(speed, RIGHT_MOTOR_TRIM))
    reg(4, 0)
    nap(duration)
    stop()

def turn_right(speed, duration):
    reg(1, 0)
    reg(2, mv(speed, LEFT_MOTOR_TRIM))
    reg(3, 0)
    reg(4, mv(speed, RIGHT_MOTOR_TRIM))
    nap(duration)
    stop()

def forward(count):
    display.show(Image.ARROW_N)
    oled_emotion('IDLE')
    try:
        for _ in range(count):
            reg(1, 0)
            reg(2, mv(FWD_SPEED, LEFT_MOTOR_TRIM))
            reg(3, mv(FWD_SPEED, RIGHT_MOTOR_TRIM))
            reg(4, 0)
            nap(STEP_PAUSE_MS)
    finally:
        stop()

def backward(count):
    display.show(Image.ARROW_S)
    oled_emotion('IDLE')
    try:
        for _ in range(count):
            reg(1, mv(FWD_SPEED, LEFT_MOTOR_TRIM))
            reg(2, 0)
            reg(3, 0)
            reg(4, mv(FWD_SPEED, RIGHT_MOTOR_TRIM))
            nap(STEP_PAUSE_MS)
    finally:
        stop()

def left(count):
    display.show(Image.ARROW_W)
    for _ in range(count):
        turn_left(FWD_SPEED, STEP_PAUSE_MS)

def right(count):
    display.show(Image.ARROW_E)
    for _ in range(count):
        turn_right(FWD_SPEED, STEP_PAUSE_MS)

def happy():
    oled_emotion('HAPPY1')
    display.show(Image.HAPPY)
    tune(['C5:1', 'E5:1', 'G5:1', 'C6:2'])
    for _ in range(ec(3)):
        oled_emotion('HAPPY1')
        both(255, 0, 255)
        turn_left(es(FWD_SPEED), et(HAPPY_WIGGLE_MS))
        both(255, 255, 255)
        nap(60)
        oled_emotion('HAPPY2')
        both(255, 0, 255)
        turn_right(es(FWD_SPEED), et(HAPPY_WIGGLE_MS))
        both(255, 255, 255)
        nap(60)
    both(255, 0, 255)

def sad():
    oled_emotion('SAD1')
    display.show(Image.SAD)
    tune(['E4:2', 'D4:2', 'C4:4'])
    for _ in range(ec(2)):
        oled_emotion('SAD1')
        for red in (220, 180, 140, 100):
            left_light(red, 255, 255)
            right_light(red, 255, 255)
            nap(80)
        reg(1, mv(SAD_SPEED, LEFT_MOTOR_TRIM))
        reg(2, 0)
        reg(3, 0)
        reg(4, mv(SAD_SPEED, RIGHT_MOTOR_TRIM))
        nap(et(SAD_SHUFFLE_MS))
        stop()
        oled_emotion('SAD2')
        nap(180)
    for _ in range(ec(2)):
        turn_left(es(SAD_SPEED), et(SAD_SHAKE_MS))
        nap(80)
        turn_right(es(SAD_SPEED), et(SAD_SHAKE_MS))
        nap(80)
    left_light(180, 255, 255)
    right_light(180, 255, 255)

def play(emotion, intensity, duration_ms=None, restore_lights=True):
    global DEADLINE, INTENSITY
    saved_left = left_state
    saved_right = right_state
    INTENSITY = intensity
    DEADLINE = running_time() + duration_ms if duration_ms is not None else None
    stop()
    try:
        if duration_ms is None:
            emotion()
        else:
            while True:
                emotion()
                nap(50)
    except ActionFinished:
        pass
    finally:
        DEADLINE = None
        stop()
        music.stop()
        if restore_lights:
            left_light(saved_left[0], saved_left[1], saved_left[2])
            right_light(saved_right[0], saved_right[1], saved_right[2])

def handle(command):
    parts = command.strip().lower().split()
    duration_ms = None
    clean = []
    for part in parts:
        if part.startswith('duration='):
            try:
                duration_ms = int(float(part.split('=', 1)[1]) * 1000)
            except ValueError:
                return 'ERR DURATION'
        else:
            clean.append(part)
    parts = clean
    if not parts:
        return None
    if parts[0] in ('happy', 'sad'):
        try:
            intensity = int(parts[1]) if len(parts) == 2 else 3
        except ValueError:
            return 'ERR INTENSITY'
        if intensity < 1 or intensity > 5:
            return 'ERR INTENSITY 1 TO 5'
        play(happy if parts[0] == 'happy' else sad, intensity, duration_ms)
        return 'OK ' + parts[0].upper()
    if parts[0] == 'nudge':
        try:
            count = int(parts[1]) if len(parts) == 2 else 8
        except ValueError:
            return 'ERR NUDGE COUNT'
        if count < 1 or count > 20:
            return 'ERR NUDGE 1 TO 20'
        approved = nudge(min(20, max(1, duration_ms // 1000 if duration_ms else count)))
        return 'OK APPROVED' if approved else 'ERR APPROVAL TIMEOUT'
    if parts[0] in ('forward', 'backward', 'back', 'left', 'right'):
        try:
            count = int(parts[1]) if len(parts) == 2 else 1
        except ValueError:
            return 'ERR MOVE COUNT'
        if count < 1 or count > 20:
            return 'ERR MOVE 1 TO 20'
        movement = {
            'forward': forward,
            'backward': backward,
            'back': backward,
            'left': left,
            'right': right,
        }[parts[0]]
        movement(count)
        return 'OK ' + parts[0].upper() + ' ' + str(count)
    if parts[0] == 'distance':
        distance = distance_cm()
        return 'OK DISTANCE ' + str(distance)
    return 'ERR USE HAPPY SAD NUDGE FORWARD BACKWARD LEFT RIGHT OR DISTANCE'
uart.init(baudrate=115200)
stop()
try:
    oled_found = oled_show('IDLE')
except OSError:
    oled_found = False
uart.write('READY KS4036 V2\n')
uart.write('OLED IDLE\n' if oled_found else 'OLED NOT FOUND\n')
NEXT_BLINK = running_time() + 2200
line = b''
while True:
    idle_blink()
    if uart.any():
        char = uart.read(1)
        if char in (b'\n', b'\r'):
            if line:
                response = handle(line.decode('ascii'))
                line = b''
                if response:
                    uart.write(response + '\n')
        elif char:
            line += char
