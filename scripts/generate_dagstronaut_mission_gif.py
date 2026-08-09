"""Generate the README animation explaining the DAGstronaut mission loop."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "media" / "dagstronaut-mascot-sprite.png"
OUTPUT = ROOT / "media" / "dagstronaut-mission-loop-v3.gif"

WIDTH = 900
HEIGHT = 400
OUTPUT_HEIGHT = 360
FRAMES = 90
DURATION_MS = 75
BACKGROUND = (3, 12, 29)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for name in names:
        if Path(name).is_file():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


TITLE = load_font(25, bold=True)
SMALL = load_font(15, bold=True)
TINY = load_font(12)


def centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(((WIDTH - (box[2] - box[0])) // 2, y), text, font=font, fill=fill)


def rounded_panel(
    image: Image.Image,
    box: tuple[int, int, int, int],
    outline: tuple[int, int, int],
) -> ImageDraw.ImageDraw:
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(box, radius=18, fill=(7, 25, 48), outline=outline, width=3)
    return draw


def main() -> None:
    mascot = Image.open(SOURCE).convert("RGBA")
    visible = mascot.getchannel("A").getbbox()
    if visible is None:
        raise RuntimeError("DAGstronaut mascot has no visible pixels")
    mascot = mascot.crop(visible)
    mascot_width = 245
    mascot_height = round(mascot.height * mascot_width / mascot.width)
    mascot = mascot.resize((mascot_width, mascot_height), Image.Resampling.LANCZOS)

    stars = ((35, 45), (91, 87), (166, 38), (261, 72), (351, 34),
             (445, 62), (537, 31), (625, 80), (717, 42), (813, 67), (871, 32))
    stage_x = (80, 265, 450, 635, 820)
    stage_labels = ("MOVE", "DETECT", "AI REVIEW", "HUMAN APPROVAL", "RETURN TO BASE")
    output_frames: list[Image.Image] = []

    for frame_index in range(FRAMES):
        phase = frame_index / FRAMES * math.tau
        canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
        draw = ImageDraw.Draw(canvas)

        for star_index, (x, y) in enumerate(stars):
            light = 100 + round(100 * (0.5 + 0.5 * math.sin(phase + star_index)))
            draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(55, light, min(255, light + 35)))

        # Mission timeline remains visible throughout the loop.
        timeline_y = 352
        draw.line((stage_x[0], timeline_y, stage_x[-1], timeline_y), fill=(26, 91, 124), width=4)
        active_stage = min(4, frame_index // 18)
        for index, (x, label) in enumerate(zip(stage_x, stage_labels)):
            complete = index < active_stage
            active = index == active_stage
            color = (45, 224, 216) if active else ((38, 156, 157) if complete else (18, 55, 78))
            radius = 12 if active else 9
            draw.ellipse((x - radius, timeline_y - radius, x + radius, timeline_y + radius),
                         fill=color, outline=(157, 248, 243), width=2)
            text_box = draw.textbbox((0, 0), label, font=TINY)
            draw.text((x - (text_box[2] - text_box[0]) // 2, 372), label,
                      font=TINY, fill=(163, 206, 220) if index <= active_stage else (76, 112, 132))

        # The obstacle stays fixed while the rover and decision layers change.
        rock = ((690, 275), (710, 205), (754, 165), (801, 197), (826, 275))
        draw.polygon(rock, fill=(54, 65, 82), outline=(112, 137, 155))
        draw.ellipse((742, 210, 760, 226), fill=(28, 36, 51))
        draw.ellipse((788, 238, 800, 249), fill=(30, 38, 53))
        draw.line((40, 278, 860, 278), fill=(26, 70, 90), width=3)

        if frame_index < 18:
            local = frame_index / 17
            rover_x = round(40 + 330 * (local * local * (3 - 2 * local)))
            bob = round(3 * math.sin(local * math.tau * 2))
            rover_y = 278 - mascot_height + bob
            for streak in range(3):
                draw.line((rover_x - 42 + streak * 10, 225 + streak * 12,
                           rover_x - 12, 225 + streak * 12), fill=(17, 93, 125), width=2)
            canvas.paste(mascot, (rover_x, rover_y), mascot)
            centered_text(draw, "ROVER MOVES", 38, TITLE, (130, 234, 242))

        elif frame_index < 36:
            rover_x = 370
            rover_y = 278 - mascot_height
            canvas.paste(mascot, (rover_x, rover_y), mascot)
            local = (frame_index - 18) / 18
            sensor_origin = (rover_x + mascot_width - 12, 205)
            for ring in range(3):
                radius = 18 + ring * 17 + round(5 * math.sin(local * math.tau))
                draw.arc((sensor_origin[0] - radius, sensor_origin[1] - radius,
                          sensor_origin[0] + radius, sensor_origin[1] + radius),
                         -42, 42, fill=(52, 229, 222), width=3)
            centered_text(draw, "OBSTACLE DETECTED", 38, TITLE, (255, 190, 83))

        elif frame_index < 54:
            rover_x = 370
            rover_y = 278 - mascot_height
            canvas.paste(mascot, (rover_x, rover_y), mascot)
            rounded_panel(canvas, (575, 72, 850, 250), (40, 206, 216))
            draw = ImageDraw.Draw(canvas)
            draw.rectangle((600, 104, 714, 202), fill=(13, 39, 58), outline=(72, 198, 207), width=2)
            draw.polygon(((620, 190), (645, 140), (672, 190)), fill=(87, 98, 111))
            draw.ellipse((684, 119, 699, 134), fill=(255, 178, 47))
            scan_y = 110 + ((frame_index - 36) * 6) % 84
            draw.line((602, scan_y, 712, scan_y), fill=(63, 246, 226), width=3)
            draw.text((732, 112), "AI", font=TITLE, fill=(122, 237, 241))
            draw.text((732, 150), "IMAGE", font=SMALL, fill=(224, 242, 247))
            draw.text((732, 174), "REVIEW", font=SMALL, fill=(224, 242, 247))
            centered_text(draw, "AI REVIEWS CAMERA EVIDENCE", 36, TITLE, (130, 234, 242))

        elif frame_index < 72:
            rover_x = 370
            rover_y = 278 - mascot_height
            canvas.paste(mascot, (rover_x, rover_y), mascot)
            rounded_panel(canvas, (570, 72, 850, 250), (255, 181, 49))
            draw = ImageDraw.Draw(canvas)
            pulse = 0.5 + 0.5 * math.sin((frame_index - 54) / 18 * math.tau)
            hand_color = (255, 197 + round(30 * pulse), 103)
            # A simple raised-hand approval symbol with a confirmed check.
            draw.rounded_rectangle((614, 120, 669, 203), radius=18, fill=hand_color)
            for finger in range(4):
                x = 611 + finger * 15
                draw.rounded_rectangle((x, 96 - finger % 2 * 5, x + 12, 154), radius=6, fill=hand_color)
            draw.ellipse((731, 109, 806, 184), fill=(18, 96, 75), outline=(70, 238, 182), width=3)
            draw.line((751, 147, 767, 163), fill=(225, 255, 242), width=7)
            draw.line((767, 163, 791, 128), fill=(225, 255, 242), width=7)
            draw.text((706, 202), "APPROVED", font=SMALL, fill=(99, 238, 187))
            centered_text(draw, "HUMAN FLIGHT DIRECTOR APPROVES", 36, TITLE, (255, 202, 103))

        else:
            local = (frame_index - 72) / 17
            eased = local * local * (3 - 2 * local)
            rover_x = round(370 - 330 * eased)
            bob = round(3 * math.sin(local * math.tau * 2))
            rover_y = 278 - mascot_height + bob
            canvas.paste(mascot, (rover_x, rover_y), mascot)
            # The rover retraces its recorded motor pulses in reverse.
            for streak in range(3):
                streak_y = 222 + streak * 12
                draw.line((rover_x + mascot_width + 12, streak_y,
                           rover_x + mascot_width + 46 - streak * 8, streak_y),
                          fill=(17, 93, 125), width=2)
            draw.line((rover_x - 18, 198, rover_x - 34, 198), fill=(69, 235, 204), width=4)
            draw.line((rover_x - 34, 198, rover_x - 25, 189), fill=(69, 235, 204), width=4)
            draw.line((rover_x - 34, 198, rover_x - 25, 207), fill=(69, 235, 204), width=4)
            centered_text(draw, "RETURNING TO BASE", 38, TITLE, (99, 238, 187))

        compact = canvas.resize((WIDTH, OUTPUT_HEIGHT), Image.Resampling.LANCZOS)
        output_frames.append(compact.quantize(colors=112, method=Image.Quantize.MEDIANCUT))

    output_frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=output_frames[1:],
        duration=DURATION_MS,
        loop=0,
        optimize=True,
        disposal=1,
    )
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
