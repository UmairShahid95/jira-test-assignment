"""Generate a placeholder email screenshot for documentation purposes."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    width, height = 1200, 700
    background_color = (245, 247, 250)
    header_color = (58, 80, 107)
    text_color = (33, 37, 41)
    accent_color = (69, 123, 157)

    image = Image.new("RGB", (width, height), background_color)
    draw = ImageDraw.Draw(image)

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font_large = ImageFont.truetype(font_path, 48)
    font_medium = ImageFont.truetype(font_path, 28)
    font_small = ImageFont.truetype(font_path, 22)

    draw.rectangle([(0, 0), (width, 120)], fill=header_color)
    draw.text((40, 35), "Inbox - Project Lead", font=font_large, fill=(255, 255, 255))

    draw.rectangle([(60, 160), (width - 60, height - 60)], fill=(255, 255, 255), outline=(209, 217, 224), width=3)

    draw.text((100, 200), "From: Scalable Capital Reports", font=font_medium, fill=accent_color)
    draw.text((100, 240), "Subject: Weekly Jira Report for SCAL (2024-06-03 - 2024-06-10)", font=font_medium, fill=text_color)
    draw.text((100, 290), "Hi Alex,", font=font_medium, fill=text_color)

    body_lines = [
        "Here is the weekly summary for SCAL:",
        " • Issues created: 12",
        " • Issues resolved: 9",
        " • Issues currently open: 5",
        "",
        "Issue Links:",
        "  - SCAL-123",
        "  - SCAL-118",
        "  - SCAL-117",
        "  - SCAL-110",
    ]

    y = 340
    for line in body_lines:
        draw.text((120, y), line, font=font_small, fill=text_color)
        y += 40

    output_path = Path(__file__).with_name("sample-email.png")
    image.save(output_path)
    print(f"Saved {output_path}")


if __name__ == "__main__":
    main()
