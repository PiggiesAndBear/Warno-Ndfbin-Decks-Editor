# -*- coding: utf-8 -*-
"""Render ``app.ico`` from ``icon-source.jpg``.

Why this is hand-rolled instead of a one-line library conversion:

* **PyInstaller copies each ``.ico`` entry verbatim** into an ``RT_ICON``
  resource (``PyInstaller/utils/win32/icon.py`` -> ``CopyIcons_FromIco`` reads
  ``dwBytesInRes`` bytes and writes them unchanged).  A PNG-compressed entry
  therefore ships as a PNG resource, which the shell accepts for the 256 px
  slot and is less reliable about below it.  Every entry written here is a
  plain 32-bit BGRA DIB, which is what the format was designed around.
* Pillow is not installed in the build venv, and Qt already is a dependency.
  Qt decodes the JPEG and does the resampling; this file only has to write a
  6-byte container header, one 16-byte directory entry per size, and one
  ``BITMAPINFOHEADER`` plus pixels per image.

    python make_icon.py [source.jpg] [out.ico]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

HERE = Path(__file__).resolve().parent

#: Windows asks for 16/32/48 in the shell, 20/24/40 under DPI scaling, and
#: 256 in Explorer's extra-large view.  64/128 are for Alt-Tab and the store.
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def square_crop(img: QImage) -> QImage:
    """Centre-crop to a square so the icon is not stretched.

    The source is a photo (817x655 here) and it is already roughly composed
    around the subject, so the centre is the honest crop; nothing is invented.
    """
    side = min(img.width(), img.height())
    x = (img.width() - side) // 2
    y = (img.height() - side) // 2
    return img.copy(x, y, side, side)


def downscale(img: QImage, size: int) -> QImage:
    """Resample in powers of two before the last step.

    A single 655 -> 16 ``SmoothTransformation`` samples far apart and drops
    detail unevenly; halving repeatedly keeps the average and costs nothing
    noticeable at these sizes.
    """
    out = img
    while out.width() > size * 2:
        out = out.scaled(max(size, out.width() // 2),
                         max(size, out.height() // 2),
                         Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return out.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def dib(img: QImage) -> bytes:
    """One ``.ico`` entry payload: BITMAPINFOHEADER + BGRA pixels + AND mask.

    ``biHeight`` is doubled because a DIB icon entry stacks the colour bitmap
    and the 1-bit AND mask in one image; the mask is all zeroes here because
    the alpha channel is what actually carries transparency, and Windows only
    consults the mask for the legacy non-alpha path.
    """
    w, h = img.width(), img.height()
    if img.format() != QImage.Format_ARGB32:
        img = img.convertToFormat(QImage.Format_ARGB32)
    header = struct.pack("<IiiHHIIiiII",
                         40, w, h * 2, 1, 32, 0, w * h * 4, 0, 0, 0, 0)
    raw = bytes(img.constBits())
    stride = w * 4
    xor = bytearray()
    for y in range(h - 1, -1, -1):            # DIB rows are stored bottom-up
        xor += raw[y * stride:(y + 1) * stride]
    mask_row = ((w + 31) // 32) * 4          # 1 bpp, rows padded to 4 bytes
    return header + bytes(xor) + bytes(mask_row * h)


def build_ico(img: QImage, sizes=SIZES) -> bytes:
    """Assemble a multi-size ``.ico`` container."""
    blobs = [dib(downscale(img, s)) for s in sizes]
    offset = 6 + 16 * len(sizes)
    entries = bytearray()
    for size, blob in zip(sizes, blobs):
        # 0 in the width/height byte means 256 — the field is one byte wide.
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0,
                               1, 32, len(blob), offset)
        offset += len(blob)
    return struct.pack("<HHH", 0, 1, len(sizes)) + bytes(entries) + b"".join(blobs)


def contact_sheet(img: QImage,
                  sizes=(256, 128, 64, 48, 32, 24, 20, 16)) -> QImage:
    """Render every size on the two backgrounds it has to read on.

    An icon that looks right on white and disappears on a dark taskbar is a
    common miss, so both strips are drawn.  Each row is one band tall and the
    sizes are laid out descending, sharing a baseline so the small ones can be
    compared at a glance.
    """
    pad, gap, label_h = 14, 18, 16
    cell_h = max(sizes)
    band_h = cell_h + label_h + pad
    width = pad * 2 + sum(sizes) + gap * (len(sizes) - 1)
    sheet = QImage(width, band_h * 2 + pad, QImage.Format_ARGB32)
    sheet.fill(QColor(246, 246, 248))
    p = QPainter(sheet)
    font = QFont()
    font.setPointSize(8)
    p.setFont(font)
    for band, bg in enumerate((QColor(246, 246, 248), QColor(30, 32, 36))):
        y0 = pad // 2 + band * band_h
        x = pad
        for s in sizes:
            top = y0 + (cell_h - s)          # common baseline
            p.fillRect(x, top, s, s, bg)
            p.drawImage(x, top, downscale(img, s))
            p.setPen(QColor(110, 110, 110) if band == 0
                     else QColor(160, 160, 160))
            p.drawText(x, y0 + cell_h + label_h - 2, f"{s}px")
            x += s + gap
    p.end()
    return sheet


def qt_app():
    """A ``QGuiApplication``, because drawing text without one segfaults.

    ``QPainter`` on a ``QImage`` works with no application object, but the
    moment it lays out a font it reaches for the platform plugin and takes the
    process down instead of raising.  Returns ``None`` when no platform can be
    initialised, and the caller then skips the labelled preview.
    """
    app = QGuiApplication.instance()
    if app is not None:
        return app
    try:
        return QGuiApplication([])
    except Exception as exc:                       # noqa: BLE001
        print(f"note: no GUI platform ({exc}); skipping the labelled preview")
        return None


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "icon-source.jpg"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "app.ico"
    app = qt_app()
    img = QImage(str(src))
    if img.isNull():
        print(f"FAILED: cannot read {src}")
        return 1
    cropped = square_crop(img)
    out.write_bytes(build_ico(cropped))
    downscale(cropped, 256).save(str(HERE / "icon-256.png"))
    if app is not None:
        contact_sheet(cropped).save(str(HERE / "icon-preview.png"))

    # Read the container back the same way PyInstaller will, so a malformed
    # header fails here rather than inside a 90-second build.
    from PyInstaller.utils.win32.icon import IconFile
    parsed = IconFile(str(out))
    ok = len(parsed.images) == len(SIZES)
    print(f"{src.name}  {img.width()}x{img.height()}"
          f"  -> crop {cropped.width()}x{cropped.height()}")
    print(f"wrote {out.name}  {out.stat().st_size:,} bytes"
          f"  {len(SIZES)} entries")
    print("PyInstaller IconFile parses all entries:", ok)
    print("sizes:", ", ".join(str(e.bWidth or 256) for e in parsed.entries))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
