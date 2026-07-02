#!/usr/bin/env python3
"""Render a PDF into a labeled page contact sheet for float-layout review."""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required: install it or use an environment that has PIL.") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Input PDF path")
    parser.add_argument("--out", type=Path, default=Path("/tmp/pdf-contact.png"), help="Output PNG path")
    parser.add_argument("--dpi", type=int, default=70, help="Render DPI for each page")
    parser.add_argument("--cols", type=int, default=5, help="Number of columns in the contact sheet")
    parser.add_argument("--thumb-width", type=int, default=230, help="Maximum thumbnail width")
    parser.add_argument("--thumb-height", type=int, default=300, help="Maximum thumbnail height")
    return parser.parse_args()


def render_pages(pdf: Path, out_dir: Path, dpi: int) -> list[Path]:
    if shutil.which("gs") is None:
        raise SystemExit("Ghostscript executable 'gs' is required to render PDF pages.")
    pattern = out_dir / "page-%03d.png"
    subprocess.run(
        [
            "gs",
            "-q",
            "-dNOPAUSE",
            "-dBATCH",
            "-sDEVICE=png16m",
            f"-r{dpi}",
            f"-sOutputFile={pattern}",
            str(pdf),
        ],
        check=True,
    )
    pages = sorted(out_dir.glob("page-*.png"))
    if not pages:
        raise SystemExit(f"No pages rendered from {pdf}")
    return pages


def make_contact_sheet(
    pages: list[Path],
    out: Path,
    cols: int,
    thumb_width: int,
    thumb_height: int,
) -> None:
    tile_width = thumb_width + 20
    tile_height = thumb_height + 30
    rows = math.ceil(len(pages) / cols)
    sheet = Image.new("RGB", (cols * tile_width, rows * tile_height), (240, 240, 240))

    for idx, page in enumerate(pages):
        image = Image.open(page).convert("RGB")
        image.thumbnail((thumb_width, thumb_height))
        tile = Image.new("RGB", (tile_width, tile_height), "white")
        tile.paste(image, ((tile_width - image.width) // 2, 24))
        draw = ImageDraw.Draw(tile)
        draw.text((8, 5), f"Page {idx + 1}", fill=(220, 0, 0))
        sheet.paste(tile, ((idx % cols) * tile_width, (idx // cols) * tile_height))

    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def main() -> None:
    args = parse_args()
    pdf = args.pdf.resolve()
    if not pdf.exists():
        raise SystemExit(f"PDF not found: {pdf}")
    with tempfile.TemporaryDirectory(prefix="pdf-contact-") as tmp:
        pages = render_pages(pdf, Path(tmp), args.dpi)
        make_contact_sheet(pages, args.out, args.cols, args.thumb_width, args.thumb_height)
    print(args.out)


if __name__ == "__main__":
    main()
