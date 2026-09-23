"""Create the multidisciplinary handover figure without solver dependencies."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 2640, 1000
NAVY = "#102a3b"
TEAL = "#176b70"
TEXT = "#344b5b"
BOXES = [
    (70, "Design variables", ("camber, twist, hinge", "geometry and schedule"), "#d9edf7"),
    (530, "OpenVSP geometry", ("explicit .vsp3 artifact", "with units and provenance"), "#d9edf7"),
    (990, "VSPAERO", ("fixed-lift trim, CDiw,", "spanwise loads and bending"), "#e7f2e2"),
    (1450, "Structure / actuator", ("mass, strain, force, stroke,", "energy and realized shape"), "#fff0d5"),
    (1910, "Optimization", ("objective, g(x) <= 0,", "exact validation and archive"), "#eadff2"),
]
BOX_W, BOX_H, BOX_Y = 360, 280, 410


def font(size: int, bold: bool = False):
    names = [
        "arialbd.ttf" if bold else "arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def centered(draw, xy, text, selected_font, fill):
    draw.text(xy, text, font=selected_font, fill=fill, anchor="mm")


def arrow(draw, start, end, fill=TEAL, width=5):
    draw.line([start, end], fill=fill, width=width)
    x, y = end
    draw.polygon([(x, y), (x - 22, y - 13), (x - 22, y + 13)], fill=fill)


def draw_png(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    centered(
        draw,
        (WIDTH / 2, 105),
        "ARGUS multidisciplinary optimization interface",
        font(47, True),
        NAVY,
    )
    centered(
        draw,
        (WIDTH / 2, 180),
        "Stable typed records separate the search algorithm from discipline-specific solvers",
        font(25),
        TEXT,
    )

    for x, title, details, color in BOXES:
        draw.rounded_rectangle(
            (x, BOX_Y, x + BOX_W, BOX_Y + BOX_H),
            radius=24,
            fill=color,
            outline="#15344a",
            width=4,
        )
        centered(draw, (x + BOX_W / 2, BOX_Y + 92), title, font(25, True), NAVY)
        centered(draw, (x + BOX_W / 2, BOX_Y + 173), details[0], font(20), TEXT)
        centered(draw, (x + BOX_W / 2, BOX_Y + 210), details[1], font(20), TEXT)

    for left, right in zip(BOXES, BOXES[1:]):
        arrow(
            draw,
            (left[0] + BOX_W + 18, BOX_Y + BOX_H / 2),
            (right[0] - 18, BOX_Y + BOX_H / 2),
        )

    draw.arc((250, 615, 2320, 970), start=2, end=178, fill=TEAL, width=6)
    draw.polygon([(253, 790), (275, 773), (281, 800)], fill=TEAL)
    centered(
        draw,
        (WIDTH / 2, 905),
        "next candidate / updated design variables",
        font(23),
        TEAL,
    )
    centered(
        draw,
        (1450, 748),
        "versioned JSON request / result contract",
        font(20),
        "#805c1b",
    )
    image.save(path, dpi=(220, 220))


def draw_pdf(path: Path) -> None:
    png_path = path.with_suffix(".png")
    with Image.open(png_path) as image:
        image.convert("RGB").save(path, "PDF", resolution=220.0)


def main() -> None:
    output_dir = Path(__file__).resolve().parents[1] / "docs" / "images"
    output_dir.mkdir(parents=True, exist_ok=True)
    png_path = output_dir / "coupled_workflow.png"
    draw_png(png_path)
    draw_pdf(output_dir / "coupled_workflow.pdf")


if __name__ == "__main__":
    main()
