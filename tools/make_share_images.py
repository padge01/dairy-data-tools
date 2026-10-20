"""Draw the share images in docs/images (LinkedIn 1200x627, GitHub's social preview 1280x640) from the pen card
picture docs/images/pen-card-slide.png (the card drawn with --slide). Needs Pillow; only for the repository's own pictures, not part of the kit."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "docs" / "images"
BG, INK, GREY = (246, 245, 240), (24, 26, 24), (95, 98, 94)
FONTS = "C:/Windows/Fonts/"


def font(bold, size):
    return ImageFont.truetype(FONTS + ("segoeuib.ttf" if bold else "segoeui.ttf"), size)


def make(width, height, out, crop_ratio=None):
    card = Image.open(IMAGES / "pen-card-slide.png").convert("RGB")   # the 16:9 slide card, whole
    icon = Image.open(ROOT / "plugins/dairy-data-tools/.claude-plugin/icon.png").convert("RGB")
    s = 2
    im = Image.new("RGB", (width * s, height * s), BG)
    d = ImageDraw.Draw(im)
    pad = 60 * s
    im.paste(icon.resize((80 * s, 80 * s), Image.LANCZOS), (pad - 10 * s, pad - 10 * s))
    y = pad + 88 * s
    d.text((pad, y), "Dairy Data Tools", font=font(True, 50 * s), fill=INK)
    y += 72 * s
    for line in ("A dairy's own DairyComp and", "EZfeed records, read by", "your AI assistant."):
        d.text((pad, y), line, font=font(False, 28 * s), fill=INK)
        y += 39 * s
    y += 20 * s
    for ask in ("How is pen 21 doing?", "What's the pen's IOFC?", "Did the ration change work,", "or is it the season?"):
        d.text((pad, y), ask, font=font(False, 22 * s), fill=GREY)
        y += 30 * s
    d.text((pad, height * s - pad - 14 * s), "github.com/padge01/dairy-data-tools", font=font(True, 23 * s), fill=INK)
    d.text((pad, height * s - pad + 18 * s), "Free · for Claude and other AI assistants", font=font(False, 19 * s),
           fill=GREY)
    crop = card if crop_ratio is None else card.crop((0, 0, card.width, int(card.width * crop_ratio)))
    cw = int(width * s * 0.52)
    ch = int(crop.height * cw / crop.width)
    crop = crop.resize((cw, ch), Image.LANCZOS)
    x, yy = width * s - cw - pad // 2, (height * s - ch) // 2
    shadow = Image.new("RGBA", (cw + 60 * s, ch + 60 * s), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([30 * s, 34 * s, cw + 30 * s, ch + 34 * s], radius=18 * s,
                                             fill=(0, 0, 0, 55))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14 * s))
    im.paste(shadow, (x - 30 * s, yy - 30 * s), shadow)
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=18 * s, fill=255)
    im.paste(crop, (x, yy), mask)
    im.resize((width, height), Image.LANCZOS).save(IMAGES / out, optimize=True)


if __name__ == "__main__":
    make(1200, 627, "share-linkedin.png")
    make(1280, 640, "share-github.png")
    print("wrote", IMAGES / "share-linkedin.png", "and", IMAGES / "share-github.png")
