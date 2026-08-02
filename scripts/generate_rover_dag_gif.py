"""Generate the animated planet-exploration DAG explainer for the README."""

from __future__ import annotations

from math import pi, sin
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "media/planet-exploration-rover.gif"
WIDTH, HEIGHT = 960, 480
FRAME_MS = 110
STAGES = (
    ("SYSTEM CHECK", "LEFT · RIGHT · READY", "#a889ff"),
    ("EXPLORE", "MOVE 1 STEP", "#33d6ff"),
    ("SENSE", "DISTANCE ≤ 5 CM", "#ffb84d"),
    ("CAPTURE", "USB CAMERA", "#62dfff"),
    ("ANALYSE", "GEMMA VISION", "#d8a8ff"),
    ("HITL", "HUMAN DECISION", "#ffd34f"),
    ("ACT", "SAFE MANEUVER", "#62e39b"),
    ("RETURN", "XCOM STEPS", "#62e39b"),
)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    family = "Arial Bold.ttf" if bold else "Arial.ttf"
    return ImageFont.truetype(f"/System/Library/Fonts/Supplemental/{family}", size)


TITLE, HEADING, BODY, SMALL, TINY = font(20, True), font(16, True), font(12), font(10, True), font(8, True)


def background() -> Image.Image:
    image = Image.new("RGBA", (WIDTH, HEIGHT), "#090918")
    draw = ImageDraw.Draw(image)
    random.seed(73)
    for _ in range(100):
        x, y = random.randrange(WIDTH), random.randrange(55, 335)
        shade = random.randrange(80, 185)
        draw.point((x, y), fill=(shade, shade, min(255, shade + 30), 190))
    draw.ellipse((-100, 330, 1060, 680), fill="#342736", outline="#70505d", width=2)
    draw.ellipse((630, 365, 810, 405), fill="#211b27", outline="#4a3744")
    draw.ellipse((90, 382, 270, 425), fill="#211b27", outline="#4a3744")
    draw.text((25, 17), "PLANET EXPLORATION ROVER", font=TITLE, fill="#f7f6fb")
    draw.text((WIDTH - 25, 21), "AIRFLOW PHYSICAL MISSION", font=SMALL, fill="#8e8b9d", anchor="ra")
    return image


def draw_rover(frame: Image.Image, x: float, y: float, angle: float = 0, glow: str = "#33d6ff") -> None:
    rover = Image.new("RGBA", (155, 105))
    draw = ImageDraw.Draw(rover)
    draw.rounded_rectangle((25, 38, 128, 76), radius=10, fill="#edf0f3", outline="#79818d", width=3)
    draw.rectangle((43, 25, 105, 48), fill="#dbe0e6", outline="#79818d", width=2)
    draw.rectangle((52, 31, 75, 45), fill="#16293b", outline=glow, width=2)
    draw.ellipse((82, 30, 98, 46), fill="#172736", outline="#83e6ff", width=2)
    draw.line((112, 38, 124, 13), fill="#bec6cf", width=3)
    draw.ellipse((119, 7, 130, 18), fill=glow, outline="#ffffff")
    for wheel_x in (39, 111):
        draw.ellipse((wheel_x - 18, 66, wheel_x + 18, 101), fill="#181822", outline="#777382", width=3)
        draw.ellipse((wheel_x - 7, 77, wheel_x + 7, 91), fill="#4e4c59")
    draw.rectangle((14, 48, 27, 61), fill="#ffb42b", outline="#ffd781")
    rotated = rover.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    shadow = Image.new("RGBA", frame.size)
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.ellipse((x - 62, y + 34, x + 62, y + 49), fill="#00000088")
    frame.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(5)))
    frame.alpha_composite(rotated, (int(x - rotated.width / 2), int(y - rotated.height / 2)))


def stage_bar(draw: ImageDraw.ImageDraw, active: int) -> None:
    left, gap = 25, 5
    width = (WIDTH - 50 - gap * (len(STAGES) - 1)) / len(STAGES)
    for index, (title, subtitle, color) in enumerate(STAGES):
        x = left + index * (width + gap)
        selected = index == active
        complete = index < active
        fill = "#29283b" if not selected else "#36344b"
        outline = color if selected else "#48465a"
        draw.rounded_rectangle((x, 64, x + width, 110), radius=5, fill=fill, outline=outline, width=2 if selected else 1)
        draw.ellipse((x + 8, 76, x + 16, 84), fill=color if selected or complete else "#555366")
        draw.text((x + 21, 72), title, font=TINY, fill="#ffffff" if selected else "#9a98a8")
        draw.text((x + 8, 91), subtitle, font=font(6, True), fill=color if selected else "#696778")


def telemetry(draw: ImageDraw.ImageDraw, active: int, outbound: int) -> None:
    title, subtitle, color = STAGES[active]
    draw.rounded_rectangle((25, 125, 290, 188), radius=6, fill="#181725e8", outline=color, width=2)
    draw.text((40, 139), f"TASK {active + 1} / {len(STAGES)}", font=TINY, fill=color)
    draw.text((40, 153), title, font=HEADING, fill="#ffffff")
    draw.text((278, 145), subtitle, font=TINY, fill="#a8a5b4", anchor="ra")
    draw.text((278, 165), f"XCOM OUTBOUND_STEPS = {outbound}", font=TINY, fill="#62e39b", anchor="ra")


def make_frames() -> list[Image.Image]:
    frames: list[Image.Image] = []
    stage_frames = 9
    outbound = 0
    for active in range(len(STAGES)):
        for local in range(stage_frames):
            phase = local / (stage_frames - 1)
            frame = background()
            draw = ImageDraw.Draw(frame)
            stage_bar(draw, active)
            if active == 1:
                outbound = min(4, 1 + local // 2)
            shown_outbound = 4 if active > 1 else outbound
            telemetry(draw, active, shown_outbound)

            if active == 0:
                rover_x = 160 + sin(phase * 2 * pi) * 18
                angle = sin(phase * 2 * pi) * 7
            elif active < 7:
                rover_x = 180 + min(1, (active - 1 + phase) / 2) * 470
                angle = sin(phase * pi) * -2
            else:
                rover_x = 650 - phase * 490
                angle = 0
            rover_y = 326 - sin((rover_x - 100) / 150) * 7
            draw.line((150, 372, 650, 372), fill="#62e39b55", width=2)
            for marker in range(5):
                x = 160 + marker * 118
                reached = marker <= shown_outbound
                draw.ellipse((x - 5, 367, x + 5, 377), fill="#62e39b" if reached else "#4c4958")
                draw.text((x, 387), str(marker), font=TINY, fill="#62e39b" if reached else "#666474", anchor="ma")

            if active >= 2:
                draw.rounded_rectangle((724, 267, 842, 350), radius=8, fill="#3e3138", outline="#ffb84d", width=2)
                draw.text((783, 285), "OBSTACLE", font=SMALL, fill="#ffca72", anchor="ma")
                draw.text((783, 307), "5 CM", font=TITLE, fill="#ffffff", anchor="ma")
            if active == 3:
                draw.rectangle((675, 204, 726, 240), fill="#222231", outline="#62dfff", width=2)
                draw.ellipse((690, 210, 714, 234), outline="#62dfff", width=3)
                draw.line((701, 240, 701, 267), fill="#62dfff", width=2)
                if local % 3 == 1:
                    draw.rectangle((0, 0, WIDTH, HEIGHT), fill="#ffffff55")
            if active == 4:
                draw.rounded_rectangle((665, 198, 875, 248), radius=6, fill="#221d31", outline="#d8a8ff", width=2)
                draw.text((680, 210), "GEMMA VISION", font=SMALL, fill="#d8a8ff")
                draw.text((680, 228), "OBJECT: SAFE OBSTACLE · 91%", font=TINY, fill="#ffffff")
            if active == 5:
                draw.rounded_rectangle((645, 193, 888, 253), radius=7, fill="#302a1b", outline="#ffd34f", width=2)
                draw.text((661, 207), "FLIGHT DIRECTOR", font=SMALL, fill="#ffd34f")
                draw.text((661, 229), "✓ RETURN TO BASE", font=BODY, fill="#ffffff")
            if active == 6:
                draw.text((650, 238), "SAFE ACTION CONFIRMED", font=SMALL, fill="#62e39b", anchor="ma")
            if active == 7:
                draw.rounded_rectangle((350, 215, 610, 260), radius=7, fill="#173126", outline="#62e39b", width=2)
                draw.text((480, 228), f"REVERSING {4 - min(4, int(phase * 5))} STEPS", font=SMALL, fill="#ffffff", anchor="ma")
                draw.text((480, 245), "REPLAYING XCOM PATH", font=TINY, fill="#62e39b", anchor="ma")
                if phase > 0.82:
                    draw.text((160, 235), "BASE REACHED ✓", font=HEADING, fill="#62e39b", anchor="ma")

            draw_rover(frame, rover_x, rover_y, angle, STAGES[active][2])
            draw.rectangle((25, 458, WIDTH - 25, 462), fill="#29283a")
            overall = (active + phase) / len(STAGES)
            draw.rectangle((25, 458, 25 + int((WIDTH - 50) * overall), 462), fill=STAGES[active][2])
            frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=128))
    frames.extend([frames[-1].copy() for _ in range(12)])
    return frames


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames = make_frames()
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
