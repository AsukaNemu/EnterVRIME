from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (Path("C:/Windows/Fonts/msyhbd.ttc"), Path("C:/Windows/Fonts/segoeuib.ttf")):
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (256, 256), "#07111f")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((12, 12, 244, 244), radius=58, fill="#22d3ee")
    draw.rounded_rectangle((30, 30, 226, 226), radius=44, fill="#0b1e35")
    draw.text((128, 123), "中", anchor="mm", font=font(112), fill="#f8fafc")
    draw.rounded_rectangle((58, 194, 198, 210), radius=8, fill="#22d3ee")
    image.save(ASSETS / "EnterVRIME.png")
    image.save(
        ASSETS / "EnterVRIME.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    main()
