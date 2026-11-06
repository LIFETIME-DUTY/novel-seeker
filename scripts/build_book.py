#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 chapters JSON 构建 txt + epub（EPUB3），带封面/扉页/简介/目录/版权页。

用法:
    python build_book.py _work/norm/chapters.json --meta _work/book.json \
        -n "书名（抓取版）" --outdir .            # 有封面：meta.cover 指向图片
    python build_book.py ... --no-cover          # 不做封面
    python build_book.py ... --new-id            # 换一个新的 dc:identifier（Apple 把它当新书）

章节数据支持的可选字段（都向后兼容）:
    {"num":1, "display":"第1章", "title":"回国", "paragraphs":["…"],
     "part": "第一部　风起",                       # 部/卷：相邻同名的章节归为一组，nav 两级
     "figures": [{"after": 3, "file": "img/ch1.jpg", "alt": "插图"}],   # 插图，插在第 3 段后
     "note": ["作者有话要说", "译文：……"]}          # 章末小字，渲染成 aside

长章处理：单章正文超过 --split-chars（默认 5000 字）时，会在段落边界切成多个
<section class="chapter-part">（仍是一个文件、不进目录），避免老阅读器渲染卡顿。
构建结束会打印被切的章号——交付时要告诉用户「无标题的分节是自动切分」。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys
import uuid
import zipfile

NS = 'xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"'
CN_NUM = "零一二三四五六七八九"
NOTE_MARK = "【作者有话要说】"


def esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def cn_index(n: int) -> str:
    if n < 10:
        return CN_NUM[n]
    if n < 20:
        return "十" + (CN_NUM[n % 10] if n % 10 else "")
    return CN_NUM[n // 10] + "十" + (CN_NUM[n % 10] if n % 10 else "")


def chars_of(chapters) -> int:
    return sum(len(re.sub(r"\s", "", p)) for c in chapters for p in c["paragraphs"])


EXTRA_RE = re.compile(r"番外|extra|后记|题外话|free\s*talk|作者的话", re.I)
NUMBERED_RE = re.compile(r"^第\s*[0-9〇零一二三四五六七八九十百]+\s*[章话回节]")


def _is_extra(c: dict) -> bool:
    return bool(EXTRA_RE.search(c.get("title") or "") or EXTRA_RE.search(c.get("display") or ""))


def auto_display(chapters: list[dict], renumber: bool = False,
                 extras_from: int = 0) -> None:
    """补 display；`renumber=True` 时按阅读顺序重排章号，尾部附赠篇编成「番外一…」。

    判定附赠篇（番外/后记/题外话/Free Talk）：标题或原 display 命中关键词；
    `extras_from`（1 起算的序号）用于关键词抓不到时**显式**指定附赠篇起点。
    绝不根据"没写成第N章"来推断——序章/楔子/引子都是正常正文。
    """
    n = len(chapters)
    is_extra = [_is_extra(c) for c in chapters]
    if extras_from and 1 <= extras_from <= n:
        for i in range(extras_from - 1, n):
            is_extra[i] = True
    body = [i for i in range(n) if not is_extra[i]]
    extra = [i for i in range(n) if is_extra[i]]
    for k, i in enumerate(body, 1):
        c = chapters[i]
        if renumber or not c.get("display"):
            c["display"] = f"第{k}章"
    for k, i in enumerate(extra, 1):
        c = chapters[i]
        d = (c.get("display") or "").strip()
        if not renumber and re.fullmatch(r"番外[一二三四五六七八九十0-9]+", d):
            continue
        c["display"] = f"番外{cn_index(k)}"


def display_problems(chapters: list[dict]) -> list[str]:
    """重号/重名检查：真实书里出现过"两个第37话"，不重排就会在目录里撞号。"""
    out: list[str] = []
    seen: dict[str, int] = {}
    for c in chapters:
        d = c.get("display") or ""
        if d in seen:
            out.append(f"{d} 重复（第 {seen[d]} 章与第 {c.get('num')} 章）")
        else:
            seen[d] = c.get("num", 0)
    nums: dict[int, int] = {}
    for c in chapters:
        num = c.get("num")
        if isinstance(num, int):
            nums[num] = nums.get(num, 0) + 1
    for num, cnt in sorted(nums.items()):
        if cnt > 1:
            out.append(f"num={num} 出现 {cnt} 次")
    return out


def group_parts(chapters: list[dict], meta: dict) -> list[tuple[str, list[dict]]]:
    """把章节按 part 分组；返回 [(组名, [章节…])]，组名空表示不分组。"""
    ranges = meta.get("parts") or []
    label_of: dict[int, str] = {}
    for idx, p in enumerate(ranges):
        lo, hi = int(p.get("from", 0)), int(p.get("to", 0))
        for c in chapters:
            if lo <= c["num"] <= hi:
                label_of[c["num"]] = p.get("label") or f"第{cn_index(idx + 1)}部"
    groups: list[tuple[str, list[dict]]] = []
    for c in chapters:
        label = c.get("part") or label_of.get(c["num"], "")
        if groups and groups[-1][0] == label:
            groups[-1][1].append(c)
        else:
            groups.append((label, [c]))
    return groups


# ---------------------------------------------------------------- 页脚
def auto_intro_meta(chapters, meta) -> list[str]:
    """没给 intro_meta 时自动生成「篇幅 / 基调」两行，保证页脚不会静默缺失。"""
    if meta.get("intro_meta"):
        return list(meta["intro_meta"])
    total = len(chapters)
    n_extra = sum(1 for c in chapters if (c.get("display") or "").startswith("番外"))
    words = chars_of(chapters) / 10000.0
    lead = f"篇　幅：全 {total} 章"
    if n_extra:
        lead += f"（含 {n_extra} 篇番外）"
    lead += f"，约 {words:.1f} 万字"
    out = [lead]
    tone = meta.get("tone") or " · ".join((meta.get("tags") or [])[:3])
    if tone:
        out.append(f"基　调：{tone}")
    return out


# ---------------------------------------------------------------- txt
def build_txt(chapters, meta) -> bytes:
    title = meta["title"]
    author = meta["author"]
    head = [title, "", f"{author}　著", "", meta.get("series_note", "全　本"), "", "=" * 24]
    intro = meta.get("intro") or []
    if intro:
        head += ["", "内容简介", ""]
        head += list(intro)
        foot_lines = auto_intro_meta(chapters, meta)
        if foot_lines:
            head += [""] + list(foot_lines)
        head += ["", "=" * 24]
    groups = group_parts(chapters, meta)
    part_of = {}
    for label, chs in groups:
        if label:
            for c in chs:
                part_of[id(c)] = label

    lines = head + [""]
    last_part = ""
    for ch in chapters:
        label = part_of.get(id(ch), "")
        if label and label != last_part:
            lines += ["", f"〔{label}〕", ""]
            last_part = label
        lines.append(f"{ch['display']}　{ch['title']}".rstrip())
        lines.append("")
        for p in ch["paragraphs"]:
            lines.append(p)
            lines.append("")
        note_lines = ch.get("note") or []
        if note_lines:
            lines.append(NOTE_MARK)
            lines.append("")
            for line in note_lines:
                lines.append(line)
                lines.append("")
    body = "\n".join(lines).rstrip("\n") + "\n"
    return ("\ufeff" + body).encode("utf-8")


# ---------------------------------------------------------------- epub 片段
def xhtml(title: str, body: str, cls: str = "", css_href: str = "../css/style.css") -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n'
        f'<html {NS} lang="zh-CN" xml:lang="zh-CN">\n<head>\n'
        '<meta charset="utf-8"/>\n'
        f'<title>{esc(title)}</title>\n'
        f'<link rel="stylesheet" type="text/css" href="{css_href}"/>\n'
        "</head>\n"
        f'<body class="{cls}">\n{body}\n</body>\n</html>\n'
    )


CSS = """/* novel-seeker default */
html, body { margin: 0; padding: 0; }
body {
  font-family: "Source Han Serif SC", "Songti SC", "SimSun", serif;
  line-height: 1.9;
  color: #1a1a1a;
  padding: 0 4%;
  text-align: justify;
  -webkit-hyphens: none;
}
body.cover { padding: 0; margin: 0; background: #0b0b0d; height: 100%; }
body.cover section { margin: 0; padding: 0; text-align: center; }
body.cover img { display: block; width: 100%; height: auto; margin: 0 auto; }
h1.ct {
  font-size: 1.45em; font-weight: 600; text-align: center;
  margin: 1.6em 0 0.35em; letter-spacing: 0.06em; line-height: 1.5;
}
h1.ct span.sub {
  display: block; font-size: 0.62em; font-weight: 400;
  color: #555; letter-spacing: 0.12em; margin-top: 0.35em;
}
div.rule {
  width: 3.2em; height: 1px; background: #bbb;
  margin: 0.9em auto 1.6em;
}
p { margin: 0.5em 0; text-indent: 2em; orphans: 2; widows: 2; }
p.sep { text-indent: 0; text-align: center; letter-spacing: 0; color: #8a8a8a; margin: 1.15em 0; }
section.chapter { page-break-before: always; }
section.chapter-part { page-break-before: auto; }
figure { margin: 1.2em 0; text-align: center; page-break-inside: avoid; }
figure img { max-width: 100%; max-height: 68vh; height: auto; }
figure figcaption { font-size: 0.85em; color: #666; margin-top: 0.4em; text-indent: 0; }
aside.author-note {
  margin: 2.0em 0 0; padding-top: 0.9em; border-top: 1px solid #e2e2e2;
  font-size: 0.86em; color: #666; line-height: 1.8;
}
aside.author-note p { text-indent: 0; margin: 0.35em 0; }
aside.author-note p.an-h { color: #888; letter-spacing: 0.1em; font-size: 0.95em; }
/* 前页 */
body.front { padding-top: 26%; text-align: center; }
body.front .tp-title { font-size: 2.5em; letter-spacing: 0.3em; font-weight: 600; }
body.front .tp-sub { font-size: 0.95em; letter-spacing: 0.5em; color: #666; margin-top: 0.7em; }
body.front .tp-author { font-size: 1.15em; letter-spacing: 0.14em; margin-top: 2.8em; }
body.intro h1.ct { margin-top: 0.9em; }
body.intro p { text-indent: 2em; }
body.intro p.meta-line { text-indent: 0; letter-spacing: 0.04em; color: #555; font-size: 0.94em; }
div.intro-meta { border-top: 1px solid #ddd; margin-top: 2.2em; padding-top: 1.0em; }
body.colo { padding-top: 2.6em; }
body.colo h1.ct { font-size: 1.15em; letter-spacing: 0.4em; margin-top: 0; }
body.colo p.colo-row { text-indent: 0; letter-spacing: 0.05em; margin: 0.55em 0; }
body.colo p.colo-label { color: #777; }
body.colo p.colo-note { text-indent: 0; font-size: 0.88em; color: #666; line-height: 1.8; margin: 0.6em 0; }
div.colo-sep { border-top: 1px solid #ddd; margin: 1.6em 0 1.2em; }
/* 目录（支持两级） */
nav#toc { margin: 0; }
nav#toc ol { list-style: none; padding-left: 0; margin: 0; }
nav#toc li { margin: 0.42em 0; }
nav#toc li > span { color: #333; letter-spacing: 0.05em; }
nav#toc ol ol { padding-left: 1.1em; margin-top: 0.3em; }
nav#toc a { color: #333; text-decoration: none; }
"""


def split_sections(paras: list[str], limit: int) -> list[list[str]]:
    """按段落边界把长章切成若干块，每块尽量不超过 limit 字。"""
    if limit <= 0:
        return [paras]
    total = sum(len(p) for p in paras)
    if total <= limit:
        return [paras]
    blocks, cur, n = [], [], 0
    for p in paras:
        L = len(p)
        if cur and n + L > limit:
            blocks.append(cur)
            cur, n = [], 0
        cur.append(p)
        n += L
    if cur:
        blocks.append(cur)
    return blocks


def para_html(p: str) -> str:
    s = p.strip()
    if len(s) <= 5 and s and re.fullmatch(r"[-—*·•\s]+", s):
        return f'<p class="sep">{esc("＊　＊　＊")}</p>'
    return f"<p>{esc(s)}</p>"


def build_epub(chapters, meta, cover_bytes: bytes | None, cover_ext: str, opts, base_dir: str) -> tuple[bytes, dict]:
    import hashlib as _h

    title = meta["title"]
    author = meta["author"]
    lang = meta.get("language", "zh-CN")
    old_uuid = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"novel-seeker:{author}:{title}"))
    book_uuid = ("urn:uuid:" + str(uuid.uuid4())) if opts.new_id else old_uuid
    modified = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total_chars = chars_of(chapters)
    words_wan = total_chars / 10000.0
    n_extra = sum(1 for c in chapters if c["display"].startswith("番外"))
    intro = meta.get("intro") or []
    intro_meta = auto_intro_meta(chapters, meta) if intro else []

    files: dict[str, bytes] = {}
    spine: list[str] = []
    front: list[tuple[str, str]] = []
    groups = group_parts(chapters, meta)
    has_parts = any(g[0] for g in groups)

    # cover
    if cover_bytes:
        files[f"OEBPS/images/cover.{cover_ext}"] = cover_bytes
        mt = "image/jpeg" if cover_ext in ("jpg", "jpeg") else f"image/{cover_ext}"
        body = (f'<section epub:type="cover">\n'
                f'<img src="../images/cover.{cover_ext}" alt="{esc(title)}"/>\n</section>')
        files["OEBPS/text/cover.xhtml"] = xhtml(title, body, "cover").encode("utf-8")
        spine.append("cover")
        front.append(("text/cover.xhtml", "封面"))
        cover_mt = mt
    else:
        cover_mt = ""

    # titlepage
    body = (
        f'<div class="tp-title">{esc(title)}</div>\n'
        f'<div class="tp-sub">{esc(meta.get("series_note", "全　本"))}</div>\n'
        f'<div class="tp-author">{esc(author)}　著</div>'
    )
    files["OEBPS/text/titlepage.xhtml"] = xhtml(title, body, "front").encode("utf-8")
    spine.append("titlepage")
    front.append(("text/titlepage.xhtml", "扉页"))

    # intro（缺失时也生成占位页，保证前页顺序固定：封面→扉页→简介→正文）
    if not intro:
        intro = ["（原书没有提供简介；如需补充，请在 book.json 的 intro 字段写入。）"]
        intro_meta = []
    if intro:
        parts = ['<h1 class="ct">内 容 简 介</h1>', '<div class="rule"></div>']
        parts += [f"<p>{esc(p)}</p>" for p in intro]
        if intro_meta:
            parts.append('<div class="intro-meta">')
            parts += [f'<p class="meta-line">{esc(x)}</p>' for x in intro_meta]
            parts.append("</div>")
        files["OEBPS/text/intro.xhtml"] = xhtml("内容简介", "\n".join(parts), "intro").encode("utf-8")
        spine.append("intro")
        front.append(("text/intro.xhtml", "内容简介"))

    # chapters
    split_chapters: list[int] = []
    ch_entries: list[tuple[str, str, str]] = []  # (href,label,part_label)
    for i, ch in enumerate(chapters, 1):
        pid = f"ch{i:03d}"
        h1 = f'<h1 class="ct">{esc(ch["display"])}'
        if ch.get("title"):
            h1 += f'<span class="sub">{esc(ch["title"])}</span>'
        h1 += "</h1>"
        blocks = split_sections(ch["paragraphs"], opts.split_chars)
        if len(blocks) > 1:
            split_chapters.append(ch["num"])
        figs: dict[int, list[tuple[int, dict]]] = {}
        n_para = len(ch["paragraphs"])
        for k, f in enumerate(ch.get("figures") or [], 1):
            after = int(f.get("after") or 0)
            if after < 0 or after > n_para:
                raise SystemExit(
                    f"!! 插图 after={after} 越界：第{i}章只有 {n_para} 段（图会静默丢失）")
            figs.setdefault(after, []).append((k, f))
        body_parts = [f'<section class="chapter" epub:type="chapter">', h1, '<div class="rule"></div>']
        inner: list[str] = []
        pos = 0
        for block in blocks:
            chunk: list[str] = []
            for p in block:
                pos += 1
                chunk.append(para_html(p))
                for k, f in figs.get(pos, []):
                    fig_path = (f.get("file") or "").replace("\\", "/")
                    if not fig_path:
                        continue
                    ext = os.path.splitext(fig_path)[1].lstrip(".").lower() or "jpg"
                    ext = "jpeg" if ext == "jpg" else ext
                    alt = esc(f.get("alt") or "")
                    cap = esc(f.get("caption") or f.get("alt") or "")
                    cap_html = f"<figcaption>{cap}</figcaption>" if cap else ""
                    chunk.append(
                        f'<figure><img src="../images/figures/img{i:03d}_{k}.{ext}" '
                        f'alt="{alt}"/>{cap_html}</figure>')
            if len(blocks) > 1:
                inner.append('<section class="chapter-part">\n' + "\n".join(chunk) + "\n</section>")
            else:
                inner.extend(chunk)
        body_parts += inner
        body_parts.append("</section>")
        if ch.get("note"):
            body_parts.append('<aside class="author-note">')
            body_parts.append('<p class="an-h">作者有话要说</p>')
            body_parts += [f"<p>{esc(x)}</p>" for x in ch["note"]]
            body_parts.append("</aside>")
        body = "\n".join(body_parts)
        files[f"OEBPS/text/{pid}.xhtml"] = xhtml(
            f'{ch["display"]} {ch.get("title","")}'.strip(), body, "chapter").encode("utf-8")
        spine.append(pid)
        label = f'{ch["display"]}　{ch.get("title","")}'.strip()
        ch_entries.append((f"text/{pid}.xhtml", label, ch.get("part") or ""))

    # 把章节按 part 归组（保持顺序）
    grouped: list[tuple[str, list[tuple[str, str]]]] = []
    for href, label, part in ch_entries:
        if grouped and grouped[-1][0] == part:
            grouped[-1][1].append((href, label))
        else:
            grouped.append((part, [(href, label)]))
    if not has_parts:
        grouped = [("", [x for g in grouped for x in g[1]])]

    # colophon
    rows = [
        ("书　　名", title),
        ("作　　者", author),
        ("全　　文", f"约 {words_wan:.1f} 万字，共 {len(chapters)} 章" + (f"（含 {n_extra} 篇番外）" if n_extra else "")),
    ]
    body = ['<h1 class="ct">版 权 页</h1>', '<div class="rule"></div>']
    for k, v in rows:
        body.append(f'<p class="colo-row"><span class="colo-label">{esc(k)}</span> {esc(v)}</p>')
    body.append('<div class="colo-sep"></div>')
    body.append(f'<p class="colo-note">{esc(meta.get("colophon_note", "本书据网络连载整理校订。校订仅针对标点、分段、明显讹字与病句，力求文从字顺，未增删情节、未改动人物与事实。"))}</p>')
    body.append('<p class="colo-note">本电子书仅供个人阅读，不作商业用途。</p>')
    files["OEBPS/text/colophon.xhtml"] = xhtml("版权页", "\n".join(body), "colo").encode("utf-8")
    spine.append("colophon")

    # nav（两级）
    lis: list[str] = [f'<li><a href="{esc(h)}">{esc(l)}</a></li>' for h, l in front]
    for part, items in grouped:
        if part:
            first = items[0][0]
            inner = "\n".join(f'<li><a href="{esc(h)}">{esc(l)}</a></li>' for h, l in items)
            lis.append(f'<li><span>{esc(part)}</span>\n<ol>\n{inner}\n</ol>\n</li>')
        else:
            lis += [f'<li><a href="{esc(h)}">{esc(l)}</a></li>' for h, l in items]
    lis.append('<li><a href="text/colophon.xhtml">版权页</a></li>')
    nav_body = ('<nav epub:type="toc" id="toc">\n<h1 class="ct">目　录</h1>\n<div class="rule"></div>\n<ol>\n'
                + "\n".join(lis) + "\n</ol>\n</nav>")
    files["OEBPS/nav.xhtml"] = xhtml("目录", nav_body, "toc", css_href="css/style.css").encode("utf-8")

    # ncx（与 nav 同构，含前置页；有 part 时为两级）
    play = [1]

    def np(href: str, label: str, children: list[str] = ()) -> str:
        pid = f"np{play[0]}"
        order = play[0]
        play[0] += 1
        child_xml = f"\n{chr(10).join(children)}\n" if children else ""
        return (f'<navPoint id="{pid}" playOrder="{order}"><navLabel><text>{esc(label)}</text></navLabel>'
                f'<content src="{esc(href)}"/>{child_xml}</navPoint>')

    pts: list[str] = [np(h, l) for h, l in front]
    for part, items in grouped:
        if part:
            kids = [np(h, l) for h, l in items]
            pts.append(np(items[0][0], part, kids))
        else:
            pts += [np(h, l) for h, l in items]
    pts.append(np("text/colophon.xhtml", "版权页"))
    depth = 2 if any(g[0] for g in grouped) else 1
    ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="zh-CN">\n'
        f'<head><meta name="dtb:uid" content="{book_uuid}"/>'
        f'<meta name="dtb:depth" content="{depth}"/><meta name="dtb:totalPageCount" content="0"/>'
        '<meta name="dtb:maxPageNumber" content="0"/></head>\n'
        f'<docTitle><text>{esc(title)}</text></docTitle>\n<docAuthor><text>{esc(author)}</text></docAuthor>\n'
        f"<navMap>\n{chr(10).join(pts)}\n</navMap>\n</ncx>\n"
    )
    files["OEBPS/toc.ncx"] = ncx.encode("utf-8")

    # opf
    manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
                '<item id="css" href="css/style.css" media-type="text/css"/>']
    for sid in spine:
        manifest.append(f'<item id="{sid}" href="text/{sid}.xhtml" media-type="application/xhtml+xml"/>')
    img_items: list[str] = []
    if cover_bytes:
        manifest.append(f'<item id="cover-image" href="images/cover.{cover_ext}" media-type="{cover_mt}" properties="cover-image"/>')
    # 章内插图：读入 zip（统一放 OEBPS/images/figures/），拒绝绝对路径与跳出工作目录
    for i, ch in enumerate(chapters, 1):
        for k, f in enumerate(ch.get("figures") or [], 1):
            p = (f.get("file") or "").replace("\\", "/").strip()
            if not p:
                continue
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", p):
                raise SystemExit(f"!! 插图不能是 URL: {p}（请先下载到本地）")
            if not os.path.isabs(p) and ".." in p.split("/"):
                raise SystemExit(f"!! 插图相对路径不能包含 ..: {p}")
            cand = p if os.path.isabs(p) else os.path.join(base_dir, p)
            if not os.path.isfile(cand):
                raise SystemExit(f"!! 插图不存在: {cand}")
            ext = os.path.splitext(p)[1].lstrip(".").lower() or "jpg"
            ext = "jpeg" if ext == "jpg" else ext
            mt = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
            iid = f"img{i:03d}_{k}"
            zip_path = f"images/figures/{iid}.{ext}"
            with open(cand, "rb") as fh:
                files[f"OEBPS/{zip_path}"] = fh.read()
            if iid not in img_items:
                manifest.append(f'<item id="{iid}" href="{zip_path}" media-type="{mt}"/>')
                img_items.append(iid)
    meta_xml = [
        f"<dc:title>{esc(title)}</dc:title>",
        f"<dc:creator>{esc(author)}</dc:creator>",
        f"<dc:language>{lang}</dc:language>",
        f'<dc:identifier id="bookid">{book_uuid}</dc:identifier>',
        f'<meta property="dcterms:modified">{modified}</meta>',
    ]
    if intro:
        meta_xml.append(f"<dc:description>{esc(intro[0])}</dc:description>")
    for tag in meta.get("tags") or []:
        meta_xml.append(f"<dc:subject>{esc(tag)}</dc:subject>")
    if cover_bytes:
        meta_xml.append('<meta name="cover" content="cover-image"/>')
    itemrefs = "\n".join(f'<itemref idref="{sid}"/>' for sid in spine)
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="{lang}">\n'
        f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n{chr(10).join(meta_xml)}\n</metadata>\n'
        f'<manifest>\n{chr(10).join(manifest)}\n</manifest>\n'
        f'<spine toc="ncx">\n{itemrefs}\n</spine>\n</package>\n'
    )
    files["OEBPS/content.opf"] = opf.encode("utf-8")
    files["OEBPS/css/style.css"] = CSS.encode("utf-8")
    files["META-INF/container.xml"] = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>\n'
        "</container>\n"
    ).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, "application/epub+zip")
        for name, data in files.items():
            ct = zipfile.ZIP_STORED if name.startswith("OEBPS/images/") else zipfile.ZIP_DEFLATED
            z.writestr(name, data, compress_type=ct)
    stats = {"uuid": book_uuid, "old_uuid": old_uuid, "split": split_chapters,
             "groups": sum(1 for g in grouped if g[0])}
    return buf.getvalue(), stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("chapters")
    ap.add_argument("--meta", required=True)
    ap.add_argument("-n", "--name", required=True, help="输出文件名主干（不含扩展名）")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--no-cover", action="store_true")
    ap.add_argument("--new-id", action="store_true", help="用新的 dc:identifier（uuid4），Apple 会当新书")
    ap.add_argument("--split-chars", type=int, default=5000, help="单章超过多少字切成多节；0 表示不切")
    ap.add_argument("--renumber", action="store_true",
                    help="按阅读顺序重排章号（治重号/乱号），尾部附赠篇自动编成「番外一…」")
    ap.add_argument("--extras-from", type=int, default=0,
                    help="附赠篇起始章序号（1 起算）；标题里没有「番外/后记/题外话」时才需要")
    args = ap.parse_args()

    with open(args.chapters, encoding="utf-8") as f:
        chapters = json.load(f)
    if isinstance(chapters, dict):
        chapters = chapters["chapters"]
    with open(args.meta, encoding="utf-8") as f:
        meta = json.load(f)
    if not chapters:
        print("!! 章节为空：没有任何可构建的内容（检查抓取是否真的成功）", file=sys.stderr)
        return 1
    for k in ("title", "author"):
        if not meta.get(k):
            print(f"!! meta 缺少必填字段 {k}（book.json 里补上）", file=sys.stderr)
            return 1

    before = [(c.get("num"), c.get("display"), c.get("title")) for c in chapters]
    auto_display(chapters, args.renumber, args.extras_from)
    if args.renumber:
        for idx, c in enumerate(chapters, 1):
            c["num"] = idx
        mapping = [
            {"old_num": b[0], "old_display": b[1], "new_num": c["num"],
             "new_display": c["display"], "title": b[2]}
            for b, c in zip(before, chapters)
        ]
        stem = os.path.splitext(os.path.abspath(args.chapters))[0]
        ren_path = stem + ".renumbered.json"
        map_path = stem + ".renumber_map.json"
        payload = {"chapters": chapters}
        with open(ren_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        with open(map_path, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=1)
        print(f"renumber: 已重排并写出 {ren_path}")
        print(f"renumber: 映射 {map_path}（源文件未改动；下次构建用 .renumbered.json）")
    for msg in display_problems(chapters):
        print(f"!! 章节号问题: {msg}（可用 --renumber 重排）", file=sys.stderr)
    os.makedirs(args.outdir, exist_ok=True)

    cover_bytes, cover_ext = None, "jpg"
    if not args.no_cover:
        cover_path = meta.get("cover")
        if not cover_path:
            print("!! meta.cover 未设置：本次按「不做封面」构建（要封面请设 meta.cover 或见 make_cover.py）", file=sys.stderr)
        else:
            cand = cover_path if os.path.isabs(cover_path) else os.path.join(
                os.path.dirname(os.path.abspath(args.meta)), cover_path)
            if os.path.exists(cand):
                with open(cand, "rb") as f:
                    cover_bytes = f.read()
                ext = os.path.splitext(cand)[1].lstrip(".").lower()
                cover_ext = "jpeg" if ext in ("jpg", "jpeg") else ext
                if cover_ext not in ("jpeg", "png", "gif"):
                    print(f"!! 封面格式不支持: {cover_ext}", file=sys.stderr)
                    return 1
            else:
                print(f"!! 封面文件不存在: {cand}", file=sys.stderr)
                return 1

    # 章内插图：相对 paths 以 chapters.json 所在目录为基准（先早失败，别等校验器）
    src_dir = os.path.dirname(os.path.abspath(args.chapters))
    for i, ch in enumerate(chapters, 1):
        n_para = len(ch.get("paragraphs") or [])
        for f in ch.get("figures") or []:
            p = (f.get("file") or "").replace("\\", "/").strip()
            if not p:
                continue
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", p):
                print(f"!! 插图不能是 URL: {p}", file=sys.stderr)
                return 1
            if not os.path.isabs(p) and ".." in p.split("/"):
                print(f"!! 插图相对路径不能包含 ..: {p}", file=sys.stderr)
                return 1
            cand = p if os.path.isabs(p) else os.path.join(src_dir, p)
            if not os.path.isfile(cand):
                print(f"!! 插图不存在: {cand}", file=sys.stderr)
                return 1
            after = int(f.get("after") or 0)
            if after < 0 or after > n_para:
                print(f"!! 插图 after={after} 越界：第{i}章只有 {n_para} 段", file=sys.stderr)
                return 1

    txt = build_txt(chapters, meta)
    txt_path = os.path.join(args.outdir, args.name + ".txt")
    with open(txt_path, "wb") as f:
        f.write(txt)

    epub, stats = build_epub(chapters, meta, cover_bytes, cover_ext, args, src_dir)
    epub_path = os.path.join(args.outdir, args.name + ".epub")
    with open(epub_path, "wb") as f:
        f.write(epub)

    print(f"TXT : {txt_path} {len(txt)} bytes")
    print(f"EPUB: {epub_path} {len(epub)} bytes")
    print(f"章节: {len(chapters)}  字数: {chars_of(chapters)}  epub_sha1: {hashlib.sha1(epub).hexdigest()[:12]}")
    print(f"identifier: {stats['uuid']}")
    if stats["groups"]:
        print(f"部/卷分组: {stats['groups']} 组（目录两级）")
    if stats["split"]:
        print(f"长章自动分节: 第 {stats['split']} 章 —— 交付时请说明「无标题的分节是自动切分，不进目录」")
    if args.new_id:
        old_id = meta.get("identifier") or stats["old_uuid"]
        meta["prev_ids"] = (meta.get("prev_ids") or []) + [old_id]
        meta["identifier"] = stats["uuid"]
        with open(args.meta, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        print(f"新 identifier 已写回 {args.meta}（旧 id 记入 prev_ids: {old_id}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
