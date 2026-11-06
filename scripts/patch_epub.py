#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给**任意**已有 epub 改前置页 / 修目录（不需要源 chapters.json）。

用法:
    # 只看会改什么
    python patch_epub.py "书.epub" --fix-nav --titlepage --intro-file 简介.md --dry-run

    # 真正写入（默认备份为 书.epub.bak）
    python patch_epub.py "书.epub" --fix-nav --titlepage --intro-file 简介.md \
        --colophon --words 20.7 --chapters 58

支持的动作（至少给一个）:
  --titlepage            重建扉页：书名 / 全 本 / 作者　著
  --intro-file PATH      用 markdown/纯文本重建「内容简介」页（空行分段，`# ` 作小标题）
  --intro-keep           保留原简介页，只确保它进了目录/在正文之前
  --colophon             重建版权页（--words 字数、--chapters 章数，可加 --note）
  --no-colophon          删掉版权页
  --fix-nav              按 spine 顺序重建 nav.xhtml + toc.ncx（修“目录缺页/顺序乱/文案对不上”）
  --strip-platform       删掉正文页里出现的平台字样（谨慎：会改正文）
  --refresh-modified     刷新 dcterms:modified（改完后必须刷，否则阅读器显示旧版）
  --dry-run              只打印计划，不写入

注意：这个脚本只改“前页 + 目录 + opf 元数据”，不碰章节正文段落的文字（--strip-platform 除外）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/",
      "x": "http://www.w3.org/1999/xhtml", "ncx": "http://www.daisy.org/z3986/2005/ncx/"}
XHTML = "{http://www.w3.org/1999/xhtml}"

FRONT_CSS = """
/* front-matter-unified */
body.front { text-align: center; margin: 0; padding: 22% 1em 0 1em; }
body.front .tp-title { font-size: 2.2em; letter-spacing: 0.35em; margin: 0 0 0.9em 0; }
body.front .tp-sub { font-size: 0.95em; letter-spacing: 0.6em; color: #666; margin: 0 0 3em 0; }
body.front .tp-author { font-size: 1.05em; letter-spacing: 0.3em; }
body.intro { padding: 1em 1.2em; }
body.intro h1 { font-size: 1.3em; letter-spacing: 0.5em; text-align: center; margin: 0.4em 0 0.8em 0; }
body.intro .rule { border: 0; border-top: 1px solid #bbb; width: 3.2em; margin: 0 auto 1.6em auto; }
body.intro p { text-indent: 2em; line-height: 1.85; margin: 0 0 0.55em 0; }
body.intro .intro-meta { text-indent: 0; border-top: 1px solid #ddd; margin-top: 1.4em; padding-top: 0.9em;
  color: #555; font-size: 0.85em; line-height: 1.9; }
body.colo { padding: 3em 1.2em 1em 1.2em; }
body.colo .colo-h { font-size: 1.15em; letter-spacing: 0.55em; text-align: center; margin-bottom: 2.4em; }
body.colo .colo-row { text-indent: 0; margin: 0 0 0.45em 0; letter-spacing: 0.06em; }
body.colo .colo-note { text-indent: 0; margin: 2.6em 0 0 0; color: #555; font-size: 0.86em; line-height: 1.9; }
"""

PLATFORM_WORDS = ["晋江文学城", "晋江文学", "jjwxc", "长佩文学", "gongzicp", "海棠文化"]


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def page(title: str, cls: str, inner: str, css_href: str = "../css/style.css") -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
        'lang="zh-CN" xml:lang="zh-CN">\n'
        f'<head><meta charset="utf-8"/><title>{esc(title)}</title>\n'
        f'<link rel="stylesheet" type="text/css" href="{css_href}"/></head>\n'
        f'<body class="{cls}">\n{inner}\n</body>\n</html>\n'
    )


def posix_rel(path: str, start: str) -> str:
    return os.path.relpath(path, start).replace(os.sep, "/")


def parse_intro(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw.replace("\r\n", "\n")) if b.strip()]
    out = []
    for b in blocks:
        if b.startswith("#"):
            out.append(f'<h2>{esc(b.lstrip("# ").strip())}</h2>')
        else:
            out.append(f"<p>{esc(b.replace(chr(10), ' '))}</p>")
    return "\n".join(out)


def heading_text(root: ET.Element) -> str:
    for tag in ("h1", "h2", "h3"):
        for el in root.iter(XHTML + tag):
            t = " ".join("".join(el.itertext()).split())
            if t:
                return t
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("epub")
    ap.add_argument("--titlepage", action="store_true")
    ap.add_argument("--title", default="")
    ap.add_argument("--author", default="")
    ap.add_argument("--full-label", default="全　本")
    ap.add_argument("--intro-file", default="")
    ap.add_argument("--intro-keep", action="store_true")
    ap.add_argument("--colophon", action="store_true")
    ap.add_argument("--no-colophon", action="store_true")
    ap.add_argument("--words", default="", help="版权页字数（万），如 20.7")
    ap.add_argument("--chapters", default="", help="版权页章数，如 58")
    ap.add_argument("--note", default="", help="版权页附注（可选）")
    ap.add_argument("--fix-nav", action="store_true")
    ap.add_argument("--strip-platform", action="store_true")
    ap.add_argument("--refresh-modified", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    acts = any([args.titlepage, args.intro_file, args.colophon, args.no_colophon,
                args.fix_nav, args.strip_platform])
    if not acts:
        print("ERROR: 至少给一个动作（--titlepage/--intro-file/--colophon/--fix-nav/…）",
              file=sys.stderr)
        return 2
    if args.colophon and not (args.words or args.chapters):
        print("ERROR: --colophon 需要 --words 与/或 --chapters", file=sys.stderr)
        return 2

    z = zipfile.ZipFile(args.epub)
    entries = [(i, z.read(i.filename)) for i in z.infolist()]
    z.close()
    by_name = {i.filename: (i, d) for i, d in entries}
    names = [i.filename for i, _ in entries]

    opf_name = next(n for n in names if n.endswith("content.opf"))
    opf_text = by_name[opf_name][1].decode("utf-8")
    opf_root = ET.fromstring(by_name[opf_name][1])
    manifest = {i.get("id"): i for i in opf_root.findall("opf:manifest/opf:item", NS)}
    id_of = {i.get("href"): i.get("id") for i in manifest.values()}
    spine_ids = [x.get("idref") for x in opf_root.findall("opf:spine/opf:itemref", NS)]
    spine_hrefs = [manifest[s].get("href") for s in spine_ids if s in manifest]

    # ---------- 准备：CSS ----------
    css_name = next((n for n in names if n.endswith("css/style.css")), "")
    if not css_name:
        css_name = "OEBPS/css/style.css"
    css = by_name[css_name][1].decode("utf-8") if css_name in by_name else ""
    if "front-matter-unified" not in css:
        css = css.rstrip() + "\n" + FRONT_CSS

    # ---------- 扉页 ----------
    new_pages: dict[str, bytes] = {}
    tp_href = "text/titlepage.xhtml"
    if args.titlepage:
        if not args.title and not args.author:
            print("ERROR: --titlepage 需要 --title 和/或 --author", file=sys.stderr)
            return 2
        inner = (f'<div class="tp-title">{esc(args.title)}</div>\n'
                 f'<div class="tp-sub">{esc(args.full_label)}</div>\n'
                 f'<div class="tp-author">{esc(args.author)}　著</div>')
        new_pages[tp_href] = page(args.title or "扉页", "front", inner).encode()

    # ---------- 简介 ----------
    in_href = "text/intro.xhtml"
    if args.intro_file:
        if not os.path.isfile(args.intro_file):
            print(f"ERROR: 简介文件不存在: {args.intro_file}", file=sys.stderr)
            return 2
        body = parse_intro(args.intro_file)
        inner = ('<h1>内容简介</h1>\n<div class="rule"></div>\n' + body)
        new_pages[in_href] = page("内容简介", "intro", inner).encode()

    # ---------- 版权页 ----------
    co_href = "text/colophon.xhtml"
    if args.colophon:
        rows = []
        if args.title:
            rows.append(f'<p class="colo-row">书　　名　{esc(args.title)}</p>')
        if args.author:
            rows.append(f'<p class="colo-row">作　　者　{esc(args.author)}</p>')
        if args.words or args.chapters:
            n = args.chapters or "?"
            seg = f"全　文　约 {args.words} 万字，共 {n} 章" if args.words else f"全　文　共 {n} 章"
            rows.append(f'<p class="colo-row">{seg}</p>')
        note = args.note or ("本书据网络连载整理校订。校订仅针对标点、分段、明显讹字与病句，"
                             "力求文从字顺，未增删情节、未改动人物与事实。")
        inner = ('<h1 class="colo-h">版 权 页</h1>\n' + "\n".join(rows) +
                 f'\n<p class="colo-note">{esc(note)}</p>\n'
                 '<p class="colo-note">本电子书仅供个人阅读，不作商业用途。</p>')
        new_pages[co_href] = page("版权页", "colo", inner).encode()

    # ---------- 目录重建 ----------
    nav_name = next((n for n in names if n.endswith("nav.xhtml")), "OEBPS/nav.xhtml")
    nav_dir = nav_name.rsplit("/", 1)[0] + "/"
    chapters = []  # (href 相对 nav, 标题)
    skip_prefix = tuple(x for x in (tp_href, in_href, co_href, "text/cover.xhtml") if x)
    for href in spine_hrefs:
        if not href or not href.endswith(".xhtml"):
            continue
        if href.startswith(skip_prefix):
            continue
        full = "OEBPS/" + href
        if full not in by_name:
            continue
        root = ET.fromstring(by_name[full][1])
        chapters.append((href, heading_text(root) or os.path.basename(href)))

    avail = {h for h in (tp_href, in_href, co_href) if "OEBPS/" + h in by_name or h in new_pages}
    nav_items = []
    if "cover.xhtml" in " ".join(spine_hrefs[:1]):
        nav_items.append(("text/cover.xhtml", "封面"))
    if tp_href in avail or args.titlepage:
        nav_items.append((tp_href, "扉页"))
    if in_href in avail or args.intro_file:
        nav_items.append((in_href, "内容简介"))
    nav_items += chapters
    if (co_href in avail) or args.colophon:
        nav_items.append((co_href, "版权页"))

    plan = []
    if args.titlepage:
        plan.append(f"重建扉页 → {tp_href}")
    if args.intro_file:
        plan.append(f"重建简介页 → {in_href}")
    if args.colophon:
        plan.append(f"重建版权页 → {co_href}")
    if args.no_colophon and co_href in by_name:
        plan.append(f"删除版权页 → {co_href}")
    if args.fix_nav:
        plan.append(f"重建目录：{len(nav_items)} 条（nav + ncx）")
    if args.strip_platform:
        plan.append("清除正文里的平台字样")
    if args.refresh_modified:
        plan.append("刷新 dcterms:modified")
    print("计划：")
    for p in plan:
        print("  - " + p)
    if args.dry_run:
        print("dry-run：未写入")
        return 0

    # ---------- 写回 ----------
    drop = {f"OEBPS/{co_href}"} if (args.no_colophon and co_href in by_name) else set()
    out_entries: list[tuple[zipfile.ZipInfo, bytes]] = []
    changed = []
    for info, data in entries:
        n = info.filename
        if n in drop:
            changed.append(n)
            continue
        if n == css_name:
            data = css.encode("utf-8")
            changed.append(n)
        elif n.startswith(nav_dir) and n.endswith("nav.xhtml") and args.fix_nav:
            data = b""  # 占位，稍后统一写
        elif n.endswith(".xhtml") and "text/" in n and args.strip_platform:
            t = data.decode("utf-8", "ignore")
            for w in PLATFORM_WORDS:
                t = t.replace(w, "")
            data = t.encode("utf-8")
            changed.append(n)
        out_entries.append((info, data))

    # 新页 / 覆盖页
    def upsert(rel: str, payload: bytes) -> None:
        full = "OEBPS/" + rel
        for idx, (info, data) in enumerate(out_entries):
            if info.filename == full:
                out_entries[idx] = (info, payload)
                changed.append(full)
                return
        full_dir = full.rsplit("/", 1)[0]
        zi = zipfile.ZipInfo(full)
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.date_time = dt.datetime.now().timetuple()[:6]
        out_entries.append((zi, payload))
        changed.append(full)

    for rel, payload in new_pages.items():
        upsert(rel, payload)

    # nav 内容
    if args.fix_nav:
        lis = "\n".join(f'<li><a href="{esc(posix_rel(os.path.join("OEBPS", h), nav_dir))}">'
                        f'{esc(lbl)}</a></li>' for h, lbl in nav_items)
        nav = page("目录", "front",
                   f'<nav epub:type="toc" id="toc">\n<h1 class="ct">目　录</h1>\n'
                   f'<div class="rule"></div>\n<ol>\n{lis}\n</ol>\n</nav>',
                   css_href="css/style.css")
        upsert(nav_name[len("OEBPS/"):], nav.encode())

        ncx_name = next((n for n in names if n.endswith("toc.ncx")), "OEBPS/toc.ncx")
        uid = ""
        dc_id = opf_root.find("opf:metadata/dc:identifier", NS)
        if dc_id is not None and dc_id.text:
            uid = dc_id.text.strip()
        book_title = args.title or ""
        if not book_title:
            t = opf_root.find("opf:metadata/dc:title", NS)
            book_title = (t.text or "").strip() if t is not None else ""
        pts = []
        for i, (h, lbl) in enumerate(nav_items, 1):
            src = posix_rel(os.path.join("OEBPS", h), ncx_name.rsplit("/", 1)[0] + "/")
            pts.append(f'<navPoint id="np{i}" playOrder="{i}"><navLabel><text>{esc(lbl)}</text>'
                       f"</navLabel><content src=\"{esc(src)}\"/></navPoint>")
        ncx = ('<?xml version="1.0" encoding="utf-8"?>\n'
               f'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="zh-CN">\n'
               f"<head><meta name=\"dtb:uid\" content=\"{esc(uid)}\"/><meta name=\"dtb:depth\" content=\"1\"/>"
               f'<meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/>'
               f"</head>\n<docTitle><text>{esc(book_title)}</text></docTitle>\n"
               f"<navMap>\n" + "\n".join(pts) + "\n</navMap>\n</ncx>\n")
        upsert(ncx_name[len("OEBPS/"):], ncx.encode())

    # opf：manifest/spine 补齐新页
    if args.fix_nav and ('href="nav.xhtml"' not in opf_text):
        opf_text = opf_text.replace(
            "</manifest>",
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
            'properties="nav"/>' + chr(10) + "</manifest>")
    def ensure_ids() -> None:
        """把新页补进 manifest + spine，直到两边一致。"""
        nonlocal opf_text
        NL = chr(10)
        for _ in range(6):
            root = ET.fromstring(opf_text.encode("utf-8"))
            man = {i.get("id"): i.get("href") for i in root.findall("opf:manifest/opf:item", NS)}
            href2id = {h: i for i, h in man.items()}
            spine_hrefs2 = [man.get(x.get("idref"), "")
                            for x in root.findall("opf:spine/opf:itemref", NS)]
            changed_any = False
            for rel in new_pages:
                if rel not in href2id:
                    pid = "auto_" + re.sub(r"\W", "_", rel.replace("/", "_").replace(".xhtml", ""))
                    item = ('<item id="%s" href="%s" media-type="application/xhtml+xml"/>'
                            % (pid, rel))
                    opf_text = opf_text.replace("</manifest>", item + NL + "</manifest>")
                    href2id[rel] = pid
                    changed_any = True
            root2 = ET.fromstring(opf_text.encode("utf-8"))
            spine_now = [x.get("idref") for x in root2.findall("opf:spine/opf:itemref", NS)]
            for rel in (tp_href, in_href, co_href):
                if rel not in new_pages or rel not in href2id:
                    continue
                pid = href2id[rel]
                if pid in spine_now:
                    continue
                if rel == co_href:
                    opf_text = opf_text.replace("</spine>",
                                                '<itemref idref="%s"/>' % pid + NL + "</spine>")
                else:
                    pos = 1 if (spine_hrefs2 and spine_hrefs2[0] == "text/cover.xhtml") else 0
                    anchor = spine_hrefs2[pos] if len(spine_hrefs2) > pos else ""
                    aid = href2id.get(anchor, "")
                    if aid and ('idref="%s"' % aid) in opf_text:
                        opf_text = opf_text.replace(
                            '<itemref idref="%s"/>' % aid,
                            '<itemref idref="%s"/>' % aid + NL + '<itemref idref="%s"/>' % pid, 1)
                    else:
                        opf_text = opf_text.replace(
                            "</spine>", '<itemref idref="%s"/>' % pid + NL + "</spine>")
                changed_any = True
            if not changed_any:
                break

    ensure_ids()
    if args.no_colophon and co_href in by_name:
        cid = id_of.get(co_href)
        if cid:
            opf_text = opf_text.replace('<itemref idref="%s"/>' % cid, "")

    # dcterms:modified
    if args.refresh_modified or changed:
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        opf_text = re.sub(r'(<meta\s+property="dcterms:modified"[^>]*>)(.*?)(</meta>)',
                          lambda m: m.group(1) + stamp + m.group(3), opf_text, flags=re.S)

    for idx, (info, data) in enumerate(out_entries):
        if info.filename == opf_name:
            out_entries[idx] = (info, opf_text.encode("utf-8"))
            changed.append(opf_name)
    if css_name not in [i.filename for i, _ in out_entries]:
        zi = zipfile.ZipInfo(css_name)
        zi.compress_type = zipfile.ZIP_DEFLATED
        out_entries.append((zi, css.encode("utf-8")))
        changed.append(css_name)

    tmp = args.epub + ".tmp"
    with zipfile.ZipFile(tmp, "w") as w:
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        w.writestr(zi, "application/epub+zip")
        for info, data in out_entries:
            if info.filename == "mimetype":
                continue
            w.writestr(info, data)

    # 回读校验
    z2 = zipfile.ZipFile(tmp)
    names2 = z2.namelist()
    ok = True
    for required in ("OEBPS/content.opf", nav_name, "OEBPS/toc.ncx"):
        if required not in names2:
            ok = False
    for n in names2:
        if n.endswith((".xhtml", ".opf", ".ncx")):
            try:
                ET.fromstring(z2.read(n))
            except ET.ParseError as e:
                print(f"ERROR: 生成的 {n} 解析失败: {e}", file=sys.stderr)
                ok = False
    z2.close()
    if not ok:
        os.remove(tmp)
        print("ERROR: 结果校验失败，已放弃写入", file=sys.stderr)
        return 1

    backup = args.epub + ".bak"
    os.replace(args.epub, backup)
    os.replace(tmp, args.epub)
    print(f"OK 已写入 {len(set(changed))} 个条目；原文件备份为 {os.path.basename(backup)}")
    print("提示：改完请跑 validate_epub.py 做结构体检。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
