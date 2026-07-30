"""Create deterministic OpenZero Tab Pilot icons and Web Store promo artwork."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "assets" / "icons"
STORE_DIR = ROOT / "store-assets"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    windows = Path("C:/Windows/Fonts")
    candidates = [
        windows / ("segoeuib.ttf" if bold else "segoeui.ttf"),
        windows / ("arialbd.ttf" if bold else "arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def rounded_rectangle(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int) -> None:
    draw.rounded_rectangle(box, radius=radius, fill="#050505", outline="#1c4930", width=max(1, radius // 9))


def draw_mark(canvas: Image.Image, box: tuple[int, int, int, int]) -> None:
    draw = ImageDraw.Draw(canvas)
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    rounded_rectangle(draw, box, max(3, width // 7))
    points = [
        (left + int(width * 0.25), top + int(height * 0.30)),
        (left + int(width * 0.75), top + int(height * 0.30)),
        (left + int(width * 0.25), top + int(height * 0.70)),
        (left + int(width * 0.75), top + int(height * 0.70)),
    ]
    gold = [(x + max(1, width // 36), y + max(1, height // 36)) for x, y in points]
    stroke = max(2, int(width * 0.12))
    draw.line(gold, fill="#d4af37", width=max(1, stroke // 6), joint="curve")
    draw.line(points, fill="#00ff6a", width=stroke, joint="curve")


def make_icons() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    for size in (16, 32, 48, 128):
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        padding = max(1, round(size * 0.125))
        draw_mark(image, (padding, padding, size - padding - 1, size - padding - 1))
        image.save(ICON_DIR / f"icon-{size}.png", optimize=True)


def make_promo() -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (440, 280), "#030705")
    draw = ImageDraw.Draw(image)
    for radius, color in ((190, "#06150d"), (135, "#092315"), (82, "#0b2e1a")):
        draw.ellipse((330 - radius, -90 - radius, 330 + radius, -90 + radius), fill=color)
    draw.rectangle((0, 0, 440, 6), fill="#00ff6a")
    draw_mark(image, (28, 30, 126, 128))
    draw.text((150, 42), "OPENZERO", fill="#f5fff8", font=font(28, bold=True))
    draw.text((150, 78), "TAB PILOT", fill="#00ff6a", font=font(23, bold=True))
    draw.text((30, 160), "ONE TAB. EXPLICIT CONSENT.", fill="#f5fff8", font=font(20, bold=True))
    draw.text((30, 194), "Visible, bounded browser work", fill="#b9d5c1", font=font(17))
    draw.text((30, 224), "with your self-hosted OpenZero node.", fill="#b9d5c1", font=font(17))
    image.save(STORE_DIR / "small-promo-440x280.png", optimize=True)


def main() -> None:
    make_icons()
    make_promo()
    print(f"Created icons in {ICON_DIR}")
    print(f"Created promo image in {STORE_DIR}")


if __name__ == "__main__":
    main()
