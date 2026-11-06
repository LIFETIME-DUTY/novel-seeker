#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把新封面写进已有 epub：只替换封面图片条目 + 刷新 dcterms:modified。

用法:
    python inject_cover.py "书名.epub" cover.jpg [--dry-run] [--keep-modified]

行为:
  - 解析 opf 找 properties="cover-image" 的条目（退化到 <meta name="cover"> 指向的 id）
  - 校验新图是 JPEG/PNG 且短边 ≥ 800、长宽比与原封面接近（只告警）
  - 刷新 opf 里的 dcterms:modified（否则 Apple 图书继续显示缓存里的旧封面；
    --keep-modified 可关掉）
  - 备份为 <epub>.bak.cover
  - 重建 zip：mimetype 恒为第一条 STORED，封面 STORED，其余沿用原压缩方式
  - 原子替换，并回读校验「只有封面（与 modified）条目变化」
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}


def image_info(data: bytes) -> tuple[str, int, int]:
    try:
        from PIL import Image
        import io

        im = Image.open(io.BytesIO(data))
        fmt = (im.format or "").lower()
        return fmt, im.width, im.height
    except Exception:
        return "", 0, 0


def find_cover_href(z: zipfile.ZipFile) -> tuple[str, str]:
    opf_name = next(n for n in z.namelist() if n.endswith("content.opf"))
    root = ET.fromstring(z.read(opf_name))
    base = opf_name.rsplit("/", 1)[0] + "/"
    manifest = {i.get("id"): i for i in root.findall("opf:manifest/opf:item", NS)}
    href = None
    for item in manifest.values():
        if "cover-image" in (item.get("properties") or ""):
            href = item.get("href")
            break
    if not href:
        meta = root.find("opf:metadata/opf:meta[@name='cover']", NS)
        if meta is not None and meta.get("content") in manifest:
            href = manifest[meta.get("content")].get("href")
    if not href:
        raise SystemExit("epub 里没有找到封面条目（properties=cover-image 或 meta name=cover）")
    return opf_name, base + href


MOD_RE = re.compile(
    rb'(<meta\s+property=["\']dcterms:modified["\'][^>]*>)(.*?)(</meta>)', re.S | re.I)


def refresh_modified(opf_bytes: bytes) -> tuple[bytes, bool]:
    """把 dcterms:modified 刷成当前时间；返回 (新字节, 是否改动)。"""
    import datetime as dt

    now = dt.datetime.now(dt.timezone.utc)
    m = MOD_RE.search(opf_bytes)
    if not m:
        return opf_bytes, False
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    if m.group(2) == stamp:
        # 同一秒内重复注入：往后挪 1 秒，保证时间戳一定变化（阅读器才会认新文件）
        stamp = (now + dt.timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    return opf_bytes[:m.start(2)] + stamp + opf_bytes[m.end(2):], True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("epub")
    ap.add_argument("cover")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-modified", action="store_true",
                    help="不刷新 dcterms:modified（默认刷新，否则阅读器会显示旧封面）")
    args = ap.parse_args()

    with open(args.cover, "rb") as f:
        new_cover = f.read()
    fmt, w, h = image_info(new_cover)
    if fmt not in ("jpeg", "png"):
        print("ERROR: 封面必须是 JPEG 或 PNG", file=sys.stderr)
        return 1
    if min(w, h) < 800:
        print(f"WARN: 封面偏小 {w}x{h}（建议 ≥1200×1600）")

    z = zipfile.ZipFile(args.epub)
    opf_name, cover_href = find_cover_href(z)
    entries = [(i, z.read(i.filename)) for i in z.infolist()]
    old_cover = next((d for i, d in entries if i.filename == cover_href), b"")
    old_fmt, ow, oh = image_info(old_cover)
    # 格式必须与 opf 里声明的 media-type / href 扩展名一致，否则严格阅读器会坏：
    # 新图格式不同就转成原格式（PNG 保留透明，JPEG 用高质量重编码）。
    if fmt and old_fmt and fmt != old_fmt:
        try:
            from PIL import Image
            import io

            im = Image.open(io.BytesIO(new_cover))
            buf = io.BytesIO()
            if old_fmt == "jpeg":
                im.convert("RGB").save(buf, "JPEG", quality=92, progressive=True)
            else:
                im.convert("RGBA").save(buf, "PNG", optimize=True)
            new_cover = buf.getvalue()
            fmt, w, h = image_info(new_cover)
            print(f"note: 新封面格式 {image_info(new_cover)[0]} → 已转成原封面格式 {old_fmt}（保持 media-type 一致）")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: 新封面格式 {fmt} 与原封面 {old_fmt} 不同，且转换失败：{e}", file=sys.stderr)
            return 1
    if ow and oh and w and h:
        old_ratio, new_ratio = ow / oh, w / h
        if abs(old_ratio - new_ratio) / old_ratio > 0.08:
            print(f"WARN: 新封面长宽比 {new_ratio:.3f} 与原封面 {old_ratio:.3f} 差 >8%，"
                  f"部分阅读器可能拉伸（原 {ow}x{oh}，新 {w}x{h}）")
    z.close()

    before = {i.filename: hashlib.sha1(d).hexdigest() for i, d in entries}
    new_entries = []
    changed = []
    for info, data in entries:
        if info.filename == cover_href:
            new_entries.append((info, new_cover))
            changed.append(info.filename)
        elif info.filename == opf_name and not args.keep_modified:
            opf2, touched = refresh_modified(data)
            new_entries.append((info, opf2))
            if touched:
                changed.append(info.filename)
        else:
            new_entries.append((info, data))

    if not changed:
        print(f"ERROR: 没找到封面文件 {cover_href}", file=sys.stderr)
        return 1

    tmp = args.epub + ".tmp"
    with zipfile.ZipFile(tmp, "w") as w_zip:
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        w_zip.writestr(zi, "application/epub+zip")
        for info, data in new_entries:
            if info.filename == "mimetype":
                continue
            ct = zipfile.ZIP_STORED if info.filename.startswith("OEBPS/images/") else info.compress_type
            w_zip.writestr(info.filename, data, compress_type=ct)

    z2 = zipfile.ZipFile(tmp)
    after = {i.filename: hashlib.sha1(z2.read(i.filename)).hexdigest() for i in z2.infolist()}
    z2.close()
    diff = [n for n in after if before.get(n) != after[n]]
    extra = set(after) - set(before)
    lost = set(before) - set(after)
    ok = set(diff) == set(changed) and not extra and not lost
    if not ok:
        os.remove(tmp)
        print("ERROR: 替换后条目集合/哈希异常，已放弃", file=sys.stderr)
        return 1

    if args.dry_run:
        os.remove(tmp)
        print(f"dry-run: 未写入（cover -> {cover_href}, {len(new_cover)} bytes, {w}x{h}, {fmt}）")
        return 0

    backup = args.epub + ".bak.cover"
    try:
        os.replace(args.epub, backup)
        os.replace(tmp, args.epub)
    except PermissionError:
        # epub 正被阅读器打开：把临时文件撤掉，别留下半成品
        if os.path.exists(tmp):
            os.remove(tmp)
        if not os.path.exists(args.epub) and os.path.exists(backup):
            os.replace(backup, args.epub)
        print("ERROR: 文件被占用（请先关闭阅读器/预览），未写入任何改动", file=sys.stderr)
        return 1

    print(f"OK 已写入：cover -> {cover_href}（{len(new_cover)} bytes, {w}x{h}, {fmt}）；"
          f"changed entries: {diff}；原文件备份为 {os.path.basename(backup)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
