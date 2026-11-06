#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""封面合成器：底图 + 文字层（书名 / 作者），输出 1600×2400 主版 + 备选 + 缩略图自检。

这是一个「模板」，不是万能生成器：真正好看的封面靠设计（见 references/cover-brief.md）。
用它来快速套一个干净的版式，或者作为二次设计的底子。

用法:
    # 用一张图当底（可为站方插画，记得先去平台字样）
    python make_cover.py 书名 作者 --bg cover_raw.jpg --out cover.jpg --mode vertical --shade left
    # 没有底图：程序化生成夜色渐变底
    python make_cover.py 书名 作者 --out cover.jpg --mode vertical --gradient night
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:  # 只有生成封面需要这两个库，其余流程纯标准库
    sys.exit(
        "ERROR: 生成封面需要 Pillow 与 numpy（其余步骤不需要）。\n"
        "  安装：python -m pip install Pillow numpy\n"
        "  或者：不做封面，构建时加 --no-cover；以后要补封面可用官方图 + inject_cover.py。"
    )

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\Source Han Serif SC Heavy (TrueType).ttf",
    r"C:\Windows\Fonts\SourceHanSerifSC-Bold.otf",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"/System/Library/Fonts/Supplemental/Songti.ttc",
    r"/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJKsc-Bold.otf",
    "/usr/share/fonts/truetype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/opentype/source-han-serif/SourceHanSerifSC-Bold.otf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
LIGHT_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\STSONG.TTF",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"/System/Library/Fonts/Supplemental/Songti.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/source-han-serif/SourceHanSerifSC-Regular.otf",
]

FONT_OVERRIDE = ""


def pick_font(cands, size):
    for p in ([FONT_OVERRIDE] if FONT_OVERRIDE else []) + list(cands):
        if p and os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    raise SystemExit(
        "ERROR: 找不到中文字体（标题会变成方块，这张封面等于废图）。"
        "请用 --font 指定 .ttf/.otf/.ttc，例如 --font \"C:/Windows/Fonts/msyh.ttc\"")


def fit_cover(img: Image.Image, w=1600, h=2400) -> Image.Image:
    """等比裁切填满目标尺寸（不拉伸）。"""
    scale = max(w / img.width, h / img.height)
    nw, nh = int(img.width * scale + 0.5), int(img.height * scale + 0.5)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def gradient_bg(w, h, kind="night") -> Image.Image:
    yy = np.linspace(0, 1, h)[:, None]
    if kind == "night":
        top = np.array([9, 11, 16], np.float32)
        bot = np.array([30, 34, 44], np.float32)
    else:  # dusk
        top = np.array([16, 10, 12], np.float32)
        bot = np.array([58, 26, 20], np.float32)
    col = top[None, :] * (1 - yy) + bot[None, :] * yy
    arr = np.repeat(col[:, None, :], w, axis=1)
    arr += np.random.default_rng(3).normal(0, 2.2, (h, w, 1))
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def shade(img: Image.Image, side="left", strength=0.82, extent=0.52) -> Image.Image:
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    if side == "left":
        for x in range(int(w * extent)):
            a = int(255 * strength * (1 - x / (w * extent)) ** 1.4)
            d.line([(x, 0), (x, h)], fill=a)
    else:
        for y in range(int(h * 0.62), h):
            a = int(255 * strength * ((y - h * 0.62) / (h * 0.38)) ** 1.3)
            d.line([(0, y), (w, y)], fill=a)
    mask = mask.filter(ImageFilter.GaussianBlur(w // 26))
    dark = Image.new("RGB", (w, h), (6, 6, 8))
    return Image.composite(dark, img, mask)


def draw_vertical(d, text, font, x, y, gap, fill):
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        y += gap


def build(title, author, bg_path, mode, gradient, out_path, platform=""):
    W, H = 1600, 2400
    base = fit_cover(Image.open(bg_path).convert("RGB")) if bg_path else gradient_bg(W, H, gradient)
    if mode == "vertical":
        base = shade(base, "left", 0.84, 0.50)
    else:
        base = shade(base, "bottom", 0.80)

    im = base.copy()
    d = ImageDraw.Draw(im)
    title_font_size = int(min(300, (W * 0.86) / max(1, len(title))))
    f_title = pick_font(FONT_CANDIDATES, title_font_size)
    f_author = pick_font(LIGHT_FONT_CANDIDATES, 48)
    f_note = pick_font(LIGHT_FONT_CANDIDATES, 34)

    if mode == "vertical":
        gap = int(title_font_size * 1.06)
        x = int(W * 0.13)
        y = int(H * 0.16)
        draw_vertical(d, title, f_title, x, y, gap, (247, 244, 236))
        ay = y + gap * len(title) + int(title_font_size * 0.55)
        d.text((x + 6, ay), author, font=f_author, fill=(224, 220, 210))
        d.line([(x + 6, ay + 78), (x + 6 + title_font_size * 1.1, ay + 78)], fill=(150, 145, 132), width=2)
        if platform:
            d.text((x + 6, ay + 104), platform, font=f_note, fill=(160, 156, 146))
    else:
        ty = int(H * 0.34)
        d.text(((W - d.textlength(title, font=f_title)) / 2, ty), title, font=f_title, fill=(247, 244, 236))
        ay = ty + int(title_font_size * 1.35)
        tw = d.textlength(author, font=f_author)
        d.text(((W - tw) / 2, ay), author, font=f_author, fill=(224, 220, 210))
        if platform:
            pw = d.textlength(platform, font=f_note)
            d.text(((W - pw) / 2, H - 150), platform, font=f_note, fill=(160, 156, 146))

    im = im.filter(ImageFilter.UnsharpMask(radius=2.0, percent=70, threshold=3))
    im.save(out_path, quality=92, progressive=True, subsampling=0)
    stem = out_path.rsplit(".", 1)[0]
    im.save(stem + "_preview.png")
    im.resize((200, 300), Image.LANCZOS).save(stem + "_thumb.jpg", quality=90)
    print(f"cover: {out_path} {os.path.getsize(out_path)} bytes")
    print(f"preview: {stem}_preview.png   thumb: {stem}_thumb.jpg")
    print("!! 记得用 read_image 看缩略图：书名在 200×300 下还认得出吗？")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("title")
    ap.add_argument("author")
    ap.add_argument("--bg", default="", help="底图（jpg/png）")
    ap.add_argument("--mode", choices=["vertical", "horizontal"], default="vertical")
    ap.add_argument("--gradient", choices=["night", "dusk"], default="night")
    ap.add_argument("--platform", default="", help="底部小字（默认留空：不要写来源平台）")
    ap.add_argument("--font", default="", help="指定标题字体文件（找不到系统中文字体时用）")
    ap.add_argument("--out", default="cover.jpg")
    args = ap.parse_args()
    global FONT_OVERRIDE
    if args.font:
        if not os.path.exists(args.font):
            print(f"!! --font 文件不存在: {args.font}", file=sys.stderr)
            return 1
        FONT_OVERRIDE = args.font
    if args.bg and not os.path.isfile(args.bg):
        print(f"!! --bg 文件不存在: {args.bg}", file=sys.stderr)
        return 1
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    build(args.title, args.author, args.bg, args.mode, args.gradient, args.out, args.platform)
    return 0


if __name__ == "__main__":
    sys.exit(main())
