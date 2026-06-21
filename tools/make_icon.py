"""Build-time: render assets/icon.ico from the display font. Pillow is a build-
only dependency. Run once with: py tools/make_icon.py"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "assets" / "fonts" / "PirataOne-Regular.ttf"
OUT = ROOT / "assets" / "icon.ico"
BG = (28, 18, 8, 255)        # #1C1208 (matches the runtime tray tile)
FG = (224, 123, 57, 255)     # #E07B39 brass


def render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), BG)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(FONT), int(size * 0.6))
    box = draw.textbbox((0, 0), "MG", font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    draw.text(((size - w) / 2 - box[0], (size - h) / 2 - box[1]), "MG",
              font=font, fill=FG)
    return img


def main() -> None:
    base = render(256)
    base.save(OUT, format="ICO",
              sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
