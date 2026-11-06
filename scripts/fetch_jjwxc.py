#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""晋江文学城 抓取（参考实现）。

用法:
    python fetch_jjwxc.py search "书名"
    python fetch_jjwxc.py book <novelid> -o _work/raw/chapters.json [--start 1 --end N]

要点:
  - 全文检索走 AJAX：search/search_ajax.php?...&getfull=1（不需要签名）
  - 章节页 onebook.php?novelid=<id>&chapterid=<n>，正文在 <div id="paragraph_comment_content">
  - 编码 gb18030；节流 1.5–2s/章；断点续抓（已存在的章跳过）
  - 免费文 jurisdiction 为空；若出现"需要登录/购买"提示，说明是入 V 章节——停下来告诉用户，不要绕
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import os
import re
import sys
import time

try:
    import requests
except ImportError:  # 只有抓取需要 requests；构建/校验/审校不需要
    sys.exit("ERROR: 抓取需要 requests。安装：python -m pip install requests")

BASE = "https://www.jjwxc.net"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Referer": "https://www.jjwxc.net/"}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import textcheck  # noqa: E402  用同一套常用字判据做“这段真的是正文吗”体检


class _Tee:
    """把 stdout/stderr 同时写进日志文件，便于长任务留痕。"""

    def __init__(self, stream, path: str):
        self.stream = stream
        self.file = open(path, "a", encoding="utf-8")

    def write(self, s):
        self.stream.write(s)
        self.file.write(s)

    def flush(self):
        self.stream.flush()
        self.file.flush()


def get(url: str, tries: int = 5) -> str:
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            r.encoding = "gb18030"
            return r.text
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  retry {i + 1}: {e}", file=sys.stderr)
            time.sleep(3 * (i + 1))
    return ""


def search(keyword: str) -> None:
    url = (
        f"{BASE}/search/search_ajax.php?action=search&keywords={requests.utils.quote(keyword)}"
        "&type=1&version=1&getfull=1"
    )
    data = requests.get(url, headers=HEADERS, timeout=20).json()
    rows = data.get("data", {}).get("list", []) or data.get("list", [])
    for row in rows[:10]:
        print(
            f"novelid={row.get('novelid')}  作者={row.get('authorname') or row.get('author')}  "
            f"《{row.get('novelname')}》  进度={row.get('novelprogress')}"
        )


def chapter_ids(novelid: int) -> list[tuple[int, str]]:
    """从作品页目录取 (chapterid, 标题)。"""
    page = get(f"{BASE}/onebook.php?novelid={novelid}")
    pairs = re.findall(r"chapterid=(\d+)[^>]*>([^<]+)<", page)
    out, seen = [], set()
    for cid, title in pairs:
        cid = int(cid)
        if cid in seen:
            continue
        seen.add(cid)
        out.append((cid, html_mod.unescape(title).strip()))
    return out


def fetch_chapter(novelid: int, cid: int, title: str) -> dict:
    page = get(f"{BASE}/onebook.php?novelid={novelid}&chapterid={cid}")
    m = re.search(r'<div id="paragraph_comment_content">(.*?)</div>', page, re.S)
    if not m:
        raise RuntimeError(f"chapterid={cid} 没有正文（可能入V/需登录）")
    body = m.group(1)
    body = re.sub(r"<br\s*/?>", "\n", body, flags=re.I)
    body = re.sub(r"<[^>]+>", "", body)
    body = html_mod.unescape(body)
    paras = []
    for line in body.split("\n"):
        s = line.replace("\u3000", " ").strip()
        if s:
            paras.append(s)
    return {"title": title, "paragraphs": paras}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["search", "book"])
    ap.add_argument("arg")
    ap.add_argument("-o", "--out", default="_work/raw/chapters.json")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=10**6)
    ap.add_argument("--sleep", type=float, default=1.6)
    ap.add_argument("--log", default="", help="日志文件路径（追加）；建议带书名与时间戳")
    args = ap.parse_args()
    if args.log:
        os.makedirs(os.path.dirname(os.path.abspath(args.log)) or ".", exist_ok=True)
        sys.stdout = _Tee(sys.stdout, args.log)
        sys.stderr = _Tee(sys.stderr, args.log)

    if args.cmd == "search":
        search(args.arg)
        return 0

    novelid = int(args.arg)
    ids = chapter_ids(novelid)
    print(f"目录：{len(ids)} 章")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    done: dict[int, dict] = {}
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            for ch in json.load(f):
                done[ch["num"]] = ch
        print(f"已抓：{len(done)} 章（断点续抓）")

    want = [n for n in range(1, len(ids) + 1) if args.start <= n <= args.end]
    total = sum(c.get("chars", 0) for c in done.values())
    failed: list[int] = []
    for num, (cid, title) in enumerate(ids, 1):
        if num < args.start or num > args.end or num in done:
            continue
        try:
            info = fetch_chapter(novelid, cid, title)
        except Exception as e:  # noqa: BLE001
            # 不 break：后面还有机会（限流多是瞬时的）；记录失败章，最后用退出码说话
            print(f"!! 第 {num} 章失败：{e}", file=sys.stderr)
            failed.append(num)
            time.sleep(max(args.sleep, 5))
            continue
        ch = {
            "num": num,
            "title": re.sub(r"^第\d+章\s*", "", title),
            "display": f"第{num}章",
            "cid": cid,
            "paragraphs": info["paragraphs"],
            "chars": sum(len(p) for p in info["paragraphs"]),
        }
        done[num] = ch
        total += ch["chars"]
        body = "".join(info["paragraphs"])
        ratio = textcheck.common_ratio(body)
        flag = "" if ratio >= 0.80 else "  <== 可疑：常用字占比低，可能不是正文"
        print(f"[{num}/{len(ids)}] {title}  {ch['chars']} 字  累计 {total}  ratio={ratio:.2f}{flag}")
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump([done[k] for k in sorted(done)], f, ensure_ascii=False, indent=1)
        time.sleep(args.sleep)

    missing = [n for n in want if n not in done]
    print(f"完成：{len(done)} 章（本次目标 {len(want)} 章）")
    if missing:
        print(f"!! 仍缺 {len(missing)} 章：{missing[:20]}{' …' if len(missing) > 20 else ''}", file=sys.stderr)
        print("   重跑同一命令会断点续抓；或 --start/--end 缩小到缺口区间。", file=sys.stderr)
        if failed:
            print(f"   本次失败章：{failed[:20]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
