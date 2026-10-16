"""Cut the interface face, YG Sans, from Mona Sans: python3 scripts/cut-ui-font.py

Mona Sans is set in every page's first paint, so its file is on the critical path of every load.
The Latin file @fontsource-variable/mona-sans ships (98 KB) carries the whole width axis (75 to
125), weights 200 to 900 and the accented letters. The app sets widths 100 to 112, weights 400
to 680 and English text, so this keeps:

- the width axis from 100 to 112.5 and the weight axis from 400 to 700,
- Basic Latin, the Latin-1 signs (no accented letters: those fall back to the system face),
  dashes, quotes, the ellipsis, the bullet, arrows up and down, the minus, the euro and trade mark,
- kerning, ligatures and the figure sets (tabular figures keep the slashed zero).

Mona Sans is licensed under the SIL Open Font License 1.1 with the Reserved Font Name "Mona", so
the cut is renamed YG Sans and keeps the copyright and licence records; the licence sits next to
the font as OFL.txt.

Needs fontTools and brotli (pip install fonttools brotli). Run from apps/web.
"""

import io
import os

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

SOURCE = "node_modules/@fontsource-variable/mona-sans/files/mona-sans-latin-standard-normal.woff2"
TARGET = "src/fonts/yg-sans-latin.woff2"

UNICODES = (
    "U+0020-007E, U+00A0-00BF, U+00D7, U+00F7, U+2013-2014, U+2018-201A, U+201C-201E, U+2022,"
    " U+2026, U+2039-203A, U+2044, U+20AC, U+2122, U+2191, U+2193, U+2212"
)
FEATURES = ["kern", "liga", "ccmp", "locl", "tnum", "pnum"]
AXES = {"wdth": (100, 112.5), "wght": (400, 700)}

FAMILY = "YG Sans"
POSTSCRIPT = "YGSans"
NOTE = (
    "YG Sans is a cut of Mona Sans for Yield Guardian: fewer glyphs and a narrower range of"
    " widths and weights. Mona Sans is by the Mona Sans Project Authors."
)


def cut_glyphs(font: TTFont) -> TTFont:
    options = subset.Options()
    options.layout_features = FEATURES
    options.hinting = False
    options.notdef_outline = True
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=subset.parse_unicodes(UNICODES))
    subsetter.subset(font)
    # The axes are limited on a fresh parse of the cut font.
    buffer = io.BytesIO()
    font.flavor = None
    font.save(buffer)
    buffer.seek(0)
    return TTFont(buffer)


def rename(font: TTFont) -> None:
    names = font["name"]
    style = "Regular"
    replacements = {
        1: FAMILY,
        3: f"{POSTSCRIPT}-{style}",
        4: f"{FAMILY} {style}",
        6: f"{POSTSCRIPT}-{style}",
        16: FAMILY,
        21: FAMILY,
        25: POSTSCRIPT,
    }
    for record in names.names:
        if record.nameID in replacements:
            record.string = replacements[record.nameID]
    names.setName(NOTE, 10, 3, 1, 0x409)
    for instance in font["fvar"].instances:
        instance.postscriptNameID = 0xFFFF
    for record in names.names:
        text = record.toUnicode()
        if "Mona" in text and record.nameID not in (0, 10, 13):
            raise SystemExit(f"name {record.nameID} still says {text!r}")


def main() -> None:
    font = cut_glyphs(TTFont(SOURCE))
    font = instancer.instantiateVariableFont(font, AXES, updateFontNames=False)
    rename(font)
    font.flavor = "woff2"
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    font.save(TARGET)
    print(TARGET, os.path.getsize(TARGET), "bytes,", len(font.getGlyphOrder()), "glyphs")


if __name__ == "__main__":
    main()
