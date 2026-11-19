"""生成 Chrome 扩展图标。

- icons/            默认 / BiliNote 工作台
- icons/youtube/    YouTube 页面
- icons/bilibili/   B 站页面

用法：python tools/make-icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 512
ICON_DIR = Path(__file__).resolve().parents[1] / "icons"
SIZES = (128, 48, 32, 16)

BOLT = [
    (304, 56),
    (136, 296),
    (240, 296),
    (208, 456),
    (392, 208),
    (280, 208),
    (320, 56),
]


def lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


def gradient(top, bottom, glow=None):
    image = Image.new("RGB", (SIZE, SIZE))
    pixels = image.load()
    for y in range(SIZE):
        for x in range(SIZE):
            t = (x / (SIZE - 1) * 0.35) + (y / (SIZE - 1) * 0.65)
            r = lerp(top[0], bottom[0], t)
            g = lerp(top[1], bottom[1], t)
            b = lerp(top[2], bottom[2], t)
            if glow:
                distance = ((x - SIZE * 0.88) ** 2 + (y - SIZE * 0.1) ** 2) ** 0.5
                k = max(0.0, 1 - distance / (SIZE * 0.75)) * 0.18
                r, g, b = lerp(r, glow[0], k), lerp(g, glow[1], k), lerp(b, glow[2], k)
            pixels[x, y] = (r, g, b)
    return image


def rounded_icon(top, bottom, glow=None):
    background = gradient(top, bottom, glow)
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=112, fill=255)
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.paste(background, (0, 0), mask)
    return icon


def make_bilinote():
    icon = rounded_icon((139, 92, 246), (79, 70, 229), (103, 232, 249))
    ImageDraw.Draw(icon).polygon(BOLT, fill=(245, 243, 255, 255))
    return icon


def make_youtube():
    icon = rounded_icon((255, 78, 69), (196, 48, 43))
    ImageDraw.Draw(icon).polygon(
        [(196, 132), (196, 380), (392, 256)],
        fill=(255, 255, 255, 255),
    )
    return icon


def make_bilibili():
    icon = rounded_icon((0, 161, 214), (251, 114, 153))
    draw = ImageDraw.Draw(icon)
    # 天线
    draw.line((190, 170, 132, 96), fill=(255, 255, 255, 255), width=20)
    draw.line((322, 170, 380, 96), fill=(255, 255, 255, 255), width=20)
    draw.ellipse((117, 81, 147, 111), fill=(255, 255, 255, 255))
    draw.ellipse((365, 81, 395, 111), fill=(255, 255, 255, 255))
    # 电视机身
    draw.rounded_rectangle((100, 150, 412, 405), radius=54, fill=(255, 255, 255, 255))
    # 两只眼睛
    draw.ellipse((171, 254, 219, 302), fill=(0, 161, 214, 255))
    draw.ellipse((293, 254, 341, 302), fill=(0, 161, 214, 255))
    return icon


def make_zhihu():
    icon = rounded_icon((23, 114, 246), (11, 79, 209))
    draw = ImageDraw.Draw(icon)
    font = None
    for path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        try:
            font = ImageFont.truetype(path, 250)
            break
        except OSError:
            continue
    if font:
        text = "知"
        box = draw.textbbox((0, 0), text, font=font)
        x = (SIZE - (box[2] - box[0])) / 2 - box[0]
        y = (SIZE - (box[3] - box[1])) / 2 - box[1]
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    else:
        draw.ellipse((150, 100, 362, 400), fill=(255, 255, 255, 255))
        draw.ellipse((210, 210, 245, 245), fill=(23, 114, 246, 255))
        draw.ellipse((267, 210, 302, 245), fill=(23, 114, 246, 255))
    return icon


def save(icon, folder, sizes=SIZES):
    folder.mkdir(parents=True, exist_ok=True)
    for size in sizes:
        icon.resize((size, size), Image.LANCZOS).save(folder / f"{size}.png")
        print(f"wrote {folder / f'{size}.png'}")


def main():
    save(make_bilinote(), ICON_DIR)
    save(make_youtube(), ICON_DIR / "youtube")
    save(make_bilibili(), ICON_DIR / "bilibili")
    save(make_zhihu(), ICON_DIR / "zhihu")


if __name__ == "__main__":
    main()
