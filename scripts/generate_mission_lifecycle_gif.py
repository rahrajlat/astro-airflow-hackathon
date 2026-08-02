"""Generate the README mission-lifecycle animation from repository artwork."""

from __future__ import annotations

from math import pi, sin
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ROCKET_PATH = ROOT / "airflow_docker/widgets/space-mission-control/public/rocket-shuttle-cartoon-fire-v2.png"
OUTPUT_PATH = ROOT / "media/mission-lifecycle.gif"
WIDTH, HEIGHT = 960, 420
FRAME_MS = 100
FRAMES_PER_OUTCOME = 38


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "Arial Bold.ttf" if bold else "Arial.ttf"
    return ImageFont.truetype(f"/System/Library/Fonts/Supplemental/{name}", size)


TITLE = font(20, True)
LABEL = font(14, True)
SMALL = font(10, True)
TINY = font(9)


def base_frame() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#080817")
    pixels = image.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            glow = max(0, 1 - ((x - 500) ** 2 / 500**2 + (y - 210) ** 2 / 290**2))
            pixels[x, y] = (8 + int(12 * glow), 8 + int(14 * glow), 23 + int(25 * glow))
    draw = ImageDraw.Draw(image)
    random.seed(42)
    for _ in range(125):
        x, y = random.randrange(WIDTH), random.randrange(55, HEIGHT - 20)
        shade = random.randrange(75, 180)
        draw.ellipse((x, y, x + 1, y + 1), fill=(shade, shade, min(255, shade + 25)))
    draw.text((30, 18), "EVERY DAG HAS A FLIGHT PATH", font=TITLE, fill="#f7f6fb")
    draw.text((WIDTH - 30, 22), "POWERED BY APACHE AIRFLOW", font=SMALL, fill="#8b899b", anchor="ra")
    return image


def node(draw: ImageDraw.ImageDraw, x: int, title: str, subtitle: str, active: bool, color: str) -> None:
    fill = color if active else "#393849"
    outline = color if active else "#5a586a"
    draw.ellipse((x - 18, 302, x + 18, 338), fill=fill, outline=outline, width=2)
    if active:
        draw.ellipse((x - 25, 295, x + 25, 345), outline=color, width=1)
    draw.text((x, 354), title, font=LABEL, fill="#ffffff" if active else "#9997a8", anchor="ma")
    draw.text((x, 373), subtitle, font=TINY, fill=color if active else "#656374", anchor="ma")


def explosion(frame: Image.Image, x: int, y: int, scale: float) -> None:
    layer = Image.new("RGBA", frame.size)
    draw = ImageDraw.Draw(layer)
    colors = ("#ffefad", "#ffd43b", "#ff792e", "#bb293b")
    for index, color in enumerate(colors):
        radius = int((48 - index * 9) * scale)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    smoke = Image.new("RGBA", frame.size)
    smoke_draw = ImageDraw.Draw(smoke)
    for dx, dy, radius in ((-30, -30, 22), (0, -48, 29), (31, -26, 20)):
        smoke_draw.ellipse((x + dx - radius, y + dy - radius, x + dx + radius, y + dy + radius), fill="#6e6875bb")
    frame.alpha_composite(layer.filter(ImageFilter.GaussianBlur(1.2)))
    frame.alpha_composite(smoke.filter(ImageFilter.GaussianBlur(4)))


def make_frames() -> list[Image.Image]:
    rocket = Image.open(ROCKET_PATH).convert("RGBA")
    rocket.thumbnail((205, 137), Image.Resampling.LANCZOS)
    frames: list[Image.Image] = []
    positions = (130, 390, 650, 855)
    for outcome in ("LAND",):
        outcome_color = "#62e39b" if outcome == "LAND" else "#ff5f67"
        for index in range(FRAMES_PER_OUTCOME):
            progress = index / (FRAMES_PER_OUTCOME - 1)
            frame = base_frame().convert("RGBA")
            draw = ImageDraw.Draw(frame)
            draw.line((positions[0], 320, positions[-1], 320), fill="#6a687b", width=2)
            draw.line((positions[2], 320, positions[-1], 320), fill=outcome_color, width=3)
            stage = min(3, int(progress * 4))
            node(draw, positions[0], "LAUNCH", "SCHEDULED → QUEUED", stage == 0, "#ffb84d")
            node(draw, positions[1], "TRANSIT", "RUNNING", stage == 1, "#33d6ff")
            node(draw, positions[2], "DECISION", "TASK OUTCOME", stage == 2, "#ffd34f")
            node(draw, positions[3], outcome, "SUCCESS" if outcome == "LAND" else "FAILED", stage == 3, outcome_color)
            route_x = 75 + progress * 805
            arc_y = 238 - sin(progress * pi) * 105
            ship = rocket.copy()
            if outcome == "CRASH" and progress > 0.84:
                ship = ship.rotate(-28 * (progress - 0.84) / 0.16, expand=True, resample=Image.Resampling.BICUBIC)
            frame.alpha_composite(ship, (int(route_x - ship.width / 2), int(arc_y - ship.height / 2)))
            state_text = ("MISSION ACCOMPLISHED" if outcome == "LAND" else "IMPACT DETECTED") if stage == 3 else ("ORBITAL TRANSIT" if stage == 1 else "MISSION IN PROGRESS")
            draw.rounded_rectangle((30, 72, 260, 112), radius=6, fill="#171625dd", outline=outcome_color if stage == 3 else "#4c4a60")
            draw.text((44, 84), state_text, font=SMALL, fill=outcome_color if stage == 3 else "#d8d6e0")
            if outcome == "LAND" and progress > 0.88:
                draw.ellipse((825, 244, 890, 256), fill="#62e39b44", outline="#62e39b")
                draw.text((858, 270), "PAYLOAD RECOVERED", font=SMALL, fill="#62e39b", anchor="ma")
            if outcome == "CRASH" and progress > 0.88:
                explosion(frame, 855, 250, min(1, (progress - 0.88) / 0.08))
            draw.rectangle((30, 402, WIDTH - 30, 405), fill="#29283a")
            draw.rectangle((30, 402, 30 + int((WIDTH - 60) * progress), 405), fill=outcome_color if stage == 3 else "#33d6ff")
            frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=128))
        frames.extend([frames[-1].copy() for _ in range(10)])
    return frames


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    frames = make_frames()
    frames[0].save(
        OUTPUT_PATH,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
