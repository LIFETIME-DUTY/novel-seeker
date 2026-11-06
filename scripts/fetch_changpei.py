#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""长佩文学（gongzicp）抓取（参考实现，含真伪闸门）。

用法:
    python fetch_changpei.py search "书名"
    python fetch_changpei.py list <novel_id> -o _work/raw/chlist.json
    python fetch_changpei.py chapters _work/raw/chlist.json -o _work/raw/chapters.json [--sleep 3]

背景（踩过的坑，读一遍省几小时）:
  - 阅读站是 www.gongzicp.com（Vue SPA）；接口必须走同源代理 /webapi/…，
    直连 api1.gongzicp.com 一律返回「访问异常」。
  - 必需请求头：Authorization: Basic <见 SPA 主包>、Client: pc|h5、普通 UA/Referer。
  - 正文是 AES-CBC/PKCS7：key=b"u0LRrbu$Enm84koA"，iv=b"$h$b3!iGzsYnnshj"（base64 后解）。
  - 风控：data.check>=2 时 content 仍是合法密文，但明文是随机汉字（伪文本）；判真三闸门：
    常用字占比 >=0.85、字数/kt 比例 0.7–1.55、标点密度 >=1/60 字。
  - 同一出口 IP 连续请求会被降级：换代理/等待。免费文也可能触发，不是登录墙。
  - 遇到需要过验证码（阿里云滑块）时停下来告诉用户，不做绕过。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time

try:
    import requests
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
except ImportError:  # 只有抓取长佩需要这两个库
    sys.exit("ERROR: 抓取长佩需要 requests 与 pycryptodome。安装：python -m pip install requests pycryptodome")

BASE = "https://www.gongzicp.com"
AUTH = "Basic 6ZmI5aSn5a6dOmNwMTIzNDU2"  # 公开在 SPA 主包里的客户端标识
# 正文 AES 参数：来自 2023 版 ReadPc.js 里 new Le("iGzsYn","dTBMUnJidSRFbg==")。
# 站点升级前端后这两个常量可能失效（症状：解出来是乱码或空串）——
# 可用环境变量覆盖：CHANGPEI_KEY / CHANGPEI_IV，或按 references/sources.md 重新推导。
KEY = os.environ.get("CHANGPEI_KEY", "u0LRrbu$Enm84koA").encode()[:16]
IV = os.environ.get("CHANGPEI_IV", "$h$b3!iGzsYnnshj").encode()[:16]
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Referer": BASE + "/", "Authorization": AUTH, "Client": "pc"}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import textcheck  # noqa: E402  真伪闸门统一用 textcheck.looks_real

FREQ_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "freq_common.json")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_FREQ = None


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


def http_json(path: str, params: dict, proxies: dict | None = None) -> dict:
    r = requests.get(BASE + path, params=params, headers=HEADERS, timeout=15, verify=False, proxies=proxies)
    return r.json()


def decrypt(content: str) -> str:
    raw = base64.b64decode(content)
    if len(raw) % 16:
        return ""
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    try:
        return unpad(cipher.decrypt(raw), 16).decode("utf-8")
    except Exception:  # noqa: BLE001
        return ""


def _freq():
    global _FREQ
    if _FREQ is None:
        _FREQ = textcheck.load_freq(FREQ_PATH) if os.path.exists(FREQ_PATH) else None
    return _FREQ


def common_ratio(text: str) -> float:
    """常用字占比；有 freq_common.json 用统计基准，没有就用 textcheck 内置常用字表。"""
    return textcheck.common_ratio(text, _freq())


def looks_real(text: str, kt: int | None, ratio_floor=0.80) -> tuple[bool, str]:
    ok, why = textcheck.looks_real(text, kt=kt, freq=_freq(), ratio_min=ratio_floor)
    return ok, why


def split_paras(text: str) -> list[str]:
    out = []
    for line in text.replace("\r", "").split("\n"):
        s = re.sub(r"^[\s\u3000]+|[\s\u3000]+$", "", line)
        if s:
            out.append(s)
    return out


def cmd_search(kw: str) -> None:
    data = http_json("/webapi/search/novels", {"k": kw, "page": 1})
    for row in (data.get("data") or {}).get("list", [])[:10]:
        print(f"nid={row.get('novel_id')}  {row.get('novel_author')}《{row.get('novel_name')}》  {row.get('novel_wordnumber')} 字")


def cmd_list(nid: int, out: str) -> None:
    data = http_json("/webapi/novel/chapterGetList", {"nid": nid})
    items = [x for x in (data.get("data") or {}).get("list", []) if x.get("chapter_type") != "more"]
    print(f"章节 {len(items)}  字数合计 {sum(int(x.get('kt_number') or 0) for x in items)}")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    for i, x in enumerate(items, 1):
        print(f"{i:>3} cid={x.get('id')} kt={x.get('kt_number')} {x.get('name')}")


def cmd_chapters(chlist: str, out: str, sleep: float, proxies: dict | None = None) -> int:
    with open(chlist, encoding="utf-8") as f:
        items = json.load(f)
    done: dict[int, dict] = {}
    if os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            for ch in json.load(f):
                done[ch["num"]] = ch
        print(f"已抓 {len(done)} 章（断点续抓）")

    for num, item in enumerate(items, 1):
        if num in done:
            continue
        cid = item.get("id")
        for attempt in range(4):
            data = http_json("/webapi/novel/chapterGetInfo", {"cid": cid, "server": 0}, proxies=proxies)
            check = (data.get("data") or {}).get("check")
            content = ((data.get("data") or {}).get("chapterInfo") or {}).get("content") or ""
            text = decrypt(content) if content else ""
            ok, why = looks_real(text, int(item.get("kt_number") or 0))
            print(f"[{num}] cid={cid} check={check} key={why} chars={len(re.sub(r"\s", '', text))}")
            if ok:
                ch = {
                    "num": num,
                    "cid": cid,
                    "title": re.sub(r"^(第\d+[话章]|番外[.．]?[一二三四五六七八九十]*)\s*", "", item.get("name") or "").strip(),
                    "display": "",
                    "kt": int(item.get("kt_number") or 0),
                    "paragraphs": split_paras(text),
                }
                ch["chars"] = sum(len(p) for p in ch["paragraphs"])
                done[num] = ch
                with open(out, "w", encoding="utf-8") as f:
                    json.dump([done[k] for k in sorted(done)], f, ensure_ascii=False, indent=1)
                break
            time.sleep(min(60, 6 * (attempt + 1)))
        else:
            print(f"!! 第 {num} 章多次未取到真文，停下来（换出口 IP 或等风控解除后再跑）", file=sys.stderr)
            break
        time.sleep(sleep)
    print(f"完成 {len(done)}/{len(items)} 章")
    return 0 if len(done) >= len(items) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["search", "list", "chapters"])
    ap.add_argument("arg")
    ap.add_argument("-o", "--out", default="_work/raw/chapters.json")
    ap.add_argument("--sleep", type=float, default=3.0)
    ap.add_argument("--proxy", default="", help="HTTP 代理，如 http://127.0.0.1:1080；风控按出口 IP 计")
    ap.add_argument("--log", default="", help="日志文件路径（追加）；建议带书名与时间戳，避免并发覆盖")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    if args.log:
        os.makedirs(os.path.dirname(os.path.abspath(args.log)) or ".", exist_ok=True)
        sys.stdout = _Tee(sys.stdout, args.log)
        sys.stderr = _Tee(sys.stderr, args.log)
    proxies = {"http": args.proxy, "https": args.proxy} if args.proxy else None
    if args.cmd == "search":
        cmd_search(args.arg)
        return 0
    if args.cmd == "list":
        cmd_list(int(args.arg), args.out)
        return 0
    return cmd_chapters(args.arg, args.out, args.sleep, proxies=proxies)


if __name__ == "__main__":
    sys.exit(main())
