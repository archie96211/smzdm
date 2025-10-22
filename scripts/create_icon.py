#!/usr/bin/env python3
"""Generate a small Windows icon used by the tray and PyInstaller build."""

from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    assets_dir = Path(__file__).resolve().parents[1] / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    for size in sizes:
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        scale = size / 64
        draw.rounded_rectangle(
            tuple(int(v * scale) for v in (6, 6, 58, 58)),
            radius=int(16 * scale),
            fill=(30, 41, 59, 255),
        )
        draw.rounded_rectangle(
            tuple(int(v * scale) for v in (12, 14, 52, 50)),
            radius=int(10 * scale),
            fill=(14, 165, 233, 255),
        )
        draw.polygon(
            [(int(x * scale), int(y * scale)) for x, y in [(20, 35), (29, 24), (35, 32), (44, 20), (47, 24), (35, 41), (29, 33), (22, 41)]],
            fill=(255, 255, 255, 255),
        )
        draw.ellipse(
            tuple(int(v * scale) for v in (43, 13, 52, 22)),
            fill=(34, 197, 94, 255),
        )
        images.append(image)
    images[-1].save(assets_dir / "icon.ico", sizes=[(size, size) for size in sizes])


if __name__ == "__main__":
    main()
