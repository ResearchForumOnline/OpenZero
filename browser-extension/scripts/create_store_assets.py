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

    # Convenient standalone copy for dashboards that show an icon upload slot.
    with Image.open(ICON_DIR / "icon-128.png") as icon:
        icon.save(STORE_DIR / "extension-icon-128x128.png", optimize=True)

    marquee = Image.new("RGB", (1400, 560), "#020503")
    marquee_draw = ImageDraw.Draw(marquee)
    marquee_draw.rectangle((0, 0, 1400, 12), fill="#00ff6a")
    for radius, color in ((430, "#05120b"), (310, "#082015"), (210, "#0b301d")):
        marquee_draw.ellipse((260 - radius, 280 - radius, 260 + radius, 280 + radius), fill=color)
    draw_mark(marquee, (120, 120, 440, 440))

    # Abstract browser panels communicate the feature without locale-specific copy.
    panels = [
        (560, 92, 1260, 216, "#0f172a", "#2563eb"),
        (620, 238, 1300, 352, "#101d2b", "#f4d35e"),
        (545, 374, 1210, 486, "#0d2017", "#00ff6a"),
    ]
    for left, top, right, bottom, fill, accent in panels:
        marquee_draw.rounded_rectangle(
            (left, top, right, bottom),
            radius=22,
            fill=fill,
            outline="#31513b",
            width=3,
        )
        marquee_draw.ellipse((left + 24, top + 25, left + 48, top + 49), fill=accent)
        marquee_draw.rounded_rectangle(
            (left + 70, top + 25, right - 30, top + 45),
            radius=9,
            fill="#365064",
        )
        marquee_draw.rounded_rectangle(
            (left + 26, top + 66, right - 120, top + 83),
            radius=8,
            fill="#203446",
        )
        marquee_draw.rounded_rectangle(
            (right - 94, top + 62, right - 28, top + 90),
            radius=10,
            fill=accent,
        )
    marquee.save(STORE_DIR / "marquee-promo-1400x560.png", optimize=True)


def main() -> None:
    make_icons()
    make_promo()
    print(f"Created icons in {ICON_DIR}")
    print(f"Created promo image in {STORE_DIR}")


if __name__ == "__main__":
    main()
