"""Generate the compact animated DAGstronaut logo used by the README."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "media" / "dagstronaut-logo.png"
OUTPUT = ROOT / "media" / "dagstronaut-logo-animated.gif"

CANVAS_SIZE = 420
FRAME_COUNT = 36
FRAME_DURATION_MS = 70
LOGO_HEIGHT = 330
BACKGROUND = (4, 13, 31, 255)


def glow_circle(size: int, color: tuple[int, int, int], opacity: int) -> Image.Image:
    """Return a softly blurred circular glow on a transparent layer."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inset = max(2, size // 4)
    ImageDraw.Draw(layer).ellipse(
        (inset, inset, size - inset, size - inset), fill=(*color, opacity)
    )
    return layer.filter(ImageFilter.GaussianBlur(max(2, size // 8)))


def main() -> None:
    logo = Image.open(SOURCE).convert("RGBA")
    logo_width = round(logo.width * LOGO_HEIGHT / logo.height)
    logo = logo.resize((logo_width, LOGO_HEIGHT), Image.Resampling.LANCZOS)

    stars = (
        (42, 52, 1),
        (77, 118, 2),
        (349, 62, 1),
        (383, 147, 2),
        (48, 281, 1),
        (368, 334, 1),
        (112, 375, 1),
        (306, 390, 2),
    )
    frames: list[Image.Image] = []

    for index in range(FRAME_COUNT):
        phase = 2 * math.pi * index / FRAME_COUNT
        frame = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), BACKGROUND)
        draw = ImageDraw.Draw(frame)

        for star_index, (x, y, radius) in enumerate(stars):
            twinkle = 105 + round(95 * (0.5 + 0.5 * math.sin(phase + star_index)))
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=(122, 224, 255, twinkle),
            )

        bob = round(4 * math.sin(phase))
        tilt = 1.2 * math.sin(phase)
        animated_logo = logo.rotate(
            tilt, resample=Image.Resampling.BICUBIC, expand=True
        )
        x = (CANVAS_SIZE - animated_logo.width) // 2
        y = (CANVAS_SIZE - animated_logo.height) // 2 + bob + 8

        # Pulse behind the three workflow nodes already drawn into the emblem.
        pulse = 0.5 + 0.5 * math.sin(phase)
        node_positions = ((210, 58), (93, 137), (327, 137))
        for node_index, (node_x, node_y) in enumerate(node_positions):
            local = 0.5 + 0.5 * math.sin(phase - node_index * 0.8)
            size = 34 + round(12 * local)
            glow = glow_circle(size, (39, 226, 220), 55 + round(80 * local))
            frame.alpha_composite(
                glow, (node_x - glow.width // 2, node_y - glow.height // 2 + bob)
            )

        frame.alpha_composite(animated_logo, (x, y))

        # A warm status light breathes once per loop.
        status = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        status_draw = ImageDraw.Draw(status)
        radius = 3 + round(2 * pulse)
        status_draw.ellipse(
            (210 - radius, 334 + bob - radius, 210 + radius, 334 + bob + radius),
            fill=(255, 180, 35, 150 + round(90 * pulse)),
        )
        frame = Image.alpha_composite(frame, status.filter(ImageFilter.GaussianBlur(2)))
        frame = ImageEnhance.Contrast(frame).enhance(1.02)
        frames.append(frame.convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT))

    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_DURATION_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
