#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1200
HEIGHT = 675
BACKGROUND = "#F7F9FC"
INK = "#172B4D"
MUTED = "#5F6B7A"
BLUE = "#DDEBFF"
GREEN = "#DDF7EA"
PINK = "#FDE1EF"
LINE = "#B8C4D6"


def _font(size: int, *, bold: bool = False):
    candidates = [
        Path(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf"
        ),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _frame(step: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((60, 44, 1140, 630), radius=24, fill="white", outline=LINE, width=2)
    draw.rounded_rectangle((60, 44, 1140, 106), radius=24, fill=INK)
    draw.rectangle((60, 82, 1140, 106), fill=INK)
    for index, color in enumerate(("#FF7B72", "#F2CC60", "#56D364")):
        draw.ellipse((88 + index * 34, 66, 104 + index * 34, 82), fill=color)
    draw.text((190, 62), "proofline · stale decision demo", font=_font(20, bold=True), fill="white")

    y = 144
    draw.text((92, y), "$ proofline demo stale-decision", font=_font(25, bold=True), fill=INK)
    lines = [
        ("1", "ADR-007 approved", "with requirement.md:42–48", BLUE),
        ("2", "Requirement changed", "a new immutable source version", GREEN),
        ("3", "Citation checked", "approved quote no longer resolves", PINK),
    ]
    y = 205
    for index, (number, title, detail, color) in enumerate(lines, start=1):
        active = step >= index
        fill = color if active else "#F1F3F6"
        text_color = INK if active else "#8993A4"
        draw.rounded_rectangle((92, y, 1108, y + 76), radius=14, fill=fill)
        draw.ellipse((112, y + 19, 150, y + 57), fill=INK if active else LINE)
        draw.text((125, y + 25), number, font=_font(16, bold=True), fill="white")
        draw.text((174, y + 13), title, font=_font(23, bold=True), fill=text_color)
        draw.text((174, y + 43), detail, font=_font(18), fill=MUTED if active else "#9CA5B3")
        y += 91

    if step >= 4:
        draw.rounded_rectangle((92, 489, 1108, 594), radius=14, fill=PINK, outline="#9C5E7B")
        draw.text((118, 507), "Decision requires review", font=_font(27, bold=True), fill=INK)
        draw.text(
            (118, 550),
            "requirement.md:42-48 changed after this decision was approved.",
            font=_font(20),
            fill=INK,
        )
    else:
        draw.text((92, 526), "Verifying exact evidence…", font=_font(22), fill=MUTED)
    return image


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "docs/assets/stale-decision-demo.gif"
    frames = [_frame(step) for step in (1, 2, 3, 4, 4)]
    frames[0].save(
        target,
        save_all=True,
        append_images=frames[1:],
        duration=[900, 900, 900, 2200, 900],
        loop=0,
        optimize=True,
    )


if __name__ == "__main__":
    main()
