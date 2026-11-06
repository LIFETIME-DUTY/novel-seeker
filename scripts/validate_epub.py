#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""epub 结构 + 正文一致性校验（0 容忍）。

用法:
    python validate_epub.py "书名（抓取版）.epub" [--chapters norm/chapters.json]
                            [--strict-platform] [--expect-modified 2026-11-03T15:01:04Z]

不给 --chapters 时做**纯结构体检**（适用于已经交付、源 JSON 已清理的成品）；
给了 --chapters 则额外逐字校验每章正文。

检查项:
  1. mimetype 是第一条且 STORED，内容 application/epub+zip
  2. container / opf / nav / ncx / 所有 xhtml 均可解析
  3. manifest ↔ zip 一致；spine 的 idref 都在 manifest 里
  4. 每个章节文件在 spine 里正好出现一次（防“文件在包里但阅读器不显示”）
  5. nav 每条都在 ncx 里、顺序一致；章节条目数量/顺序一致；ncx 多出的只允许是部/卷节点
  6. 前置页（扉页/简介）必须进 nav（Apple 图书按 NCX 导航）
  7. 封面：manifest cover-image + text/cover.xhtml + spine 首位 + 图片 magic 与 media-type 一致
  8. 正文里的 <img> 必须存在、不得是绝对路径或跳出包外
  9. 每章 <p> 文本与源 JSON 逐字一致（含顺序与段数；跳过图注与作者有话要说）
 10. dcterms:modified 存在（Apple 缓存判据），可 --expect-modified 精确比对
 11. --strict-platform 时扫描平台字样残留
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

PLATFORM_WORDS = ["晋江文学城", "晋江文学", "jjwxc", "长佩文学", "gongzicp", "海棠文化", "自制精校版"]

NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
    "x": "http://www.w3.org/1999/xhtml",
}
XHTML = "{http://www.w3.org/1999/xhtml}"
CHAPTER_RE = re.compile(r"^OEBPS/text/ch\d+\.xhtml$")


def chapter_no(name: str) -> int:
    m = re.search(r"ch(\d+)\.xhtml$", name)
    return int(m.group(1)) if m else 0


def text_of_paragraphs(html_bytes: bytes) -> list[str]:
    """只取正文段落：跳过 <figure>（图注）与 <aside class="author-note">。"""
    root = ET.fromstring(html_bytes)
    skip = set()
    for tag in ("figure", "aside"):
        for el in root.iter(XHTML + tag):
            for p in el.iter(XHTML + "p"):
                skip.add(id(p))
    out = []
    for p in root.iter(XHTML + "p"):
        if id(p) in skip:
            continue
        out.append("".join(p.itertext()).strip())
    return out


def resolve(base_dir: str, src: str) -> str | None:
    """把 xhtml 里的相对 src 解析成 zip 内路径；绝对/越界返回 None。"""
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", src) or src.startswith("/"):
        return None
    parts: list[str] = []
    for seg in (base_dir + "/" + src).split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(seg)
    return "/".join(parts)


def magic_mt(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("epub")
    ap.add_argument("--chapters", default="", help="源 chapters.json；不给则只做结构体检")
    ap.add_argument("--strict-platform", action="store_true")
    ap.add_argument("--expect-modified", default="", help="要求 dcterms:modified 等于该值")
    args = ap.parse_args()

    errs: list[str] = []
    warns: list[str] = []
    fail = lambda m: errs.append(m)

    chapters = []
    if args.chapters:
        with open(args.chapters, encoding="utf-8") as f:
            data = json.load(f)
        chapters = data["chapters"] if isinstance(data, dict) else data
        if not chapters:
            fail("源 chapters.json 是空的（0 章），这是抓取失败，不是成书")

    z = zipfile.ZipFile(args.epub)
    names = z.namelist()

    # 1 mimetype
    if not names or names[0] != "mimetype":
        fail("mimetype 不是第一条")
    else:
        if z.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            fail("mimetype 未使用 STORED")
        if z.read("mimetype").strip() != b"application/epub+zip":
            fail("mimetype 内容错误")

    # 2 XML 可解析
    bad = []
    for n in names:
        if n.endswith((".xhtml", ".opf", ".ncx", ".xml")):
            try:
                ET.fromstring(z.read(n))
            except ET.ParseError as e:
                bad.append(f"{n}: {e}")
    if bad:
        fail("XML 解析失败: " + "; ".join(bad[:5]))

    if "OEBPS/content.opf" not in names:
        print("FAIL: 找不到 OEBPS/content.opf")
        for e in errs:
            print("  - " + e)
        return 1

    opf = ET.fromstring(z.read("OEBPS/content.opf"))
    manifest: dict[str, ET.Element] = {}
    for item in opf.findall("opf:manifest/opf:item", NS):
        manifest[item.get("id")] = item
    spine = [x.get("idref") for x in opf.findall("opf:spine/opf:itemref", NS)]

    # 3 manifest ↔ zip
    hrefs: dict[str, str] = {}
    for i, item in manifest.items():
        href = item.get("href")
        full = "OEBPS/" + href
        if full not in names:
            fail(f"manifest 指向的文件不存在: {full}")
        hrefs[i] = href
    for sid in spine:
        if sid not in manifest:
            fail(f"spine 引用了不存在的 id: {sid}")

    # 4 spine 必须包含全部章节文件，且各一次
    chapter_files = sorted([n for n in names if CHAPTER_RE.match(n)], key=chapter_no)
    spine_hrefs = [hrefs.get(sid, "") for sid in spine]
    for cf in chapter_files:
        rel = cf[len("OEBPS/"):]
        cnt = spine_hrefs.count(rel)
        if cnt != 1:
            fail(f"章节文件在 spine 里出现 {cnt} 次（应为 1 次）: {rel}")

    # 5 nav ↔ ncx
    nav_links: list[str] = []
    nav_pairs: list[tuple[str, str]] = []
    nav_root = ET.fromstring(z.read("OEBPS/nav.xhtml"))
    for a in nav_root.iter(XHTML + "a"):
        nav_links.append(a.get("href"))
        nav_pairs.append((a.get("href"), "".join(a.itertext()).strip()))
    ncx_root = ET.fromstring(z.read("OEBPS/toc.ncx"))
    ncx_links = [c.get("src") for c in ncx_root.iter("{%s}content" % NS["ncx"])]

    missing_in_ncx = [x for x in nav_links if x not in ncx_links]
    if missing_in_ncx:
        fail(f"nav 有 {len(missing_in_ncx)} 条在 ncx 里找不到: {missing_in_ncx[:3]}")
    pos = {}
    for i, h in enumerate(ncx_links):
        pos.setdefault(h, i)
    order = [pos[h] for h in nav_links if h in pos]
    if order != sorted(order):
        fail("nav 与 ncx 的链接顺序不一致")

    ncx_unique = list(dict.fromkeys(ncx_links))
    extras = [h for h in ncx_unique if h not in nav_links]
    if extras:
        # 只允许“部/卷节点”：指向某章但不带章节前缀以外的额外层级
        bad_extra = [h for h in extras if h not in [c[len("OEBPS/"):] for c in chapter_files]]
        if bad_extra:
            fail(f"ncx 多出非部/卷节点: {bad_extra[:3]}")
        else:
            warns.append(f"ncx 比 nav 多 {len(extras)} 个部/卷节点（两级目录，正常）")

    for href in nav_links:
        if "OEBPS/" + href not in names:
            fail(f"nav 链接目标不存在: {href}")

    # 5b 章节条目：nav / ncx 里的章节 href 集合与顺序必须一致
    chapter_rel = [c[len("OEBPS/"):] for c in chapter_files]
    nav_ch = [h for h in nav_links if h in chapter_rel]
    ncx_ch = [h for h in dict.fromkeys(ncx_links) if h in chapter_rel]
    if nav_ch != ncx_ch:
        fail(f"nav/ncx 的章节条目不一致（nav {len(nav_ch)} 个，ncx {len(ncx_ch)} 个）")
    if nav_ch != chapter_rel:
        fail(f"目录里的章节条目与章节文件不一致（目录 {len(nav_ch)} 个，文件 {len(chapter_rel)} 个）")

    # 6 前置页必须进目录
    for page in ("text/titlepage.xhtml", "text/intro.xhtml"):
        if "OEBPS/" + page in names and page not in nav_links:
            fail(f"目录缺少前置页: {page}（Apple 图书会看不到该页）")

    # 7 封面
    cover_items = [i for i in manifest.values() if "cover-image" in (i.get("properties") or "")]
    if len(cover_items) > 1:
        fail(f"有 {len(cover_items)} 个 cover-image 条目")
    if cover_items:
        if "OEBPS/text/cover.xhtml" not in names:
            fail("有 cover-image 但没有 text/cover.xhtml 封面页")
        first = spine[0] if spine else None
        if not first or hrefs.get(first, "") != "text/cover.xhtml":
            fail(f"spine 第一项不是封面页（实际: {hrefs.get(first, first)}）")
        href = cover_items[0].get("href")
        mt = cover_items[0].get("media-type")
        if "OEBPS/" + href not in names:
            fail(f"封面文件不存在: {href}")
        else:
            real = magic_mt(z.read("OEBPS/" + href))
            if real and mt and real != mt:
                fail(f"封面 media-type={mt} 与真实格式 {real} 不符")
    else:
        warns.append("没有 properties=cover-image 的封面条目（无封面书可忽略）")

    # 8 正文图片
    for n in names:
        if not n.endswith(".xhtml"):
            continue
        t = z.read(n).decode("utf-8", "ignore")
        for m in re.finditer(r'<img[^>]+src="([^"]+)"', t):
            src = m.group(1)
            fp = resolve(n.rsplit("/", 1)[0], src)
            if fp is None:
                fail(f"{n} 引用了绝对路径/越界图片: {src}")
            elif fp not in names:
                fail(f"{n} 引用的图片不存在: {src} → {fp}")

    # 9 正文逐字比对
    mismatches = 0
    if chapters:
        if len(chapter_files) != len(chapters):
            fail(f"章节文件数({len(chapter_files)}) 与源章节数({len(chapters)}) 不一致")
        for path, ch in zip(chapter_files, chapters):
            got = text_of_paragraphs(z.read(path))
            want = [p for p in ch.get("paragraphs", [])]
            if got != want:
                mismatches += 1
                if mismatches <= 3:
                    first = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), None)
                    fail(f"正文与源不一致: {path}（段数 {len(got)} vs {len(want)}，"
                         f"首个差异段 #{first if first is not None else '-'}）")

    # 10 dcterms:modified
    mod = opf.find("opf:metadata/opf:meta[@property='dcterms:modified']", NS)
    if mod is None:
        fail("缺少 dcterms:modified（Apple 图书会缓存旧版）")
    elif args.expect_modified and mod.text.strip() != args.expect_modified:
        fail(f"dcterms:modified={mod.text.strip()} 不是期望的 {args.expect_modified}")

    # 11 平台字样
    if args.strict_platform:
        for n in names:
            if not n.endswith((".xhtml", ".opf", ".ncx")):
                continue
            t = z.read(n).decode("utf-8", "ignore")
            for w in PLATFORM_WORDS:
                if w in t:
                    fail(f"{n} 含平台字样「{w}」（--strict-platform）")
                    break

    # 长章分节（只报告）
    split_files = [n.rsplit("/", 1)[-1] for n in chapter_files
                   if 'class="chapter-part"' in z.read(n).decode("utf-8", "ignore")]

    ncx_count = len(ncx_links)
    print(f"chapters: {len(chapter_files)}  ncx: {ncx_count}  nav: {len(nav_links)}  "
          f"spine: {len(spine)}  entries: {len(names)}")
    if chapters:
        print(f"mismatch chapters: {mismatches}")
    if split_files:
        print(f"chapter-part 分节文件: {len(split_files)} 个")
    for w in warns:
        print("WARN: " + w)
    if errs:
        for e in errs:
            print("FAIL: " + e)
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
