#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""novel-seeker 全链路冒烟测试。

用自造的小样（6 章、含部/卷、插图、作者有话要说、超长章、脏标点）跑一遍：
normalize → build_book（有封面 / 无封面）→ validate_epub → 审校链路
（check_part / merge_parts / pron_scan / apply_pron / make_diff / final_check）。

不联网、不依赖真实书；用法：
    python tests/run_smoke.py            # 安静模式，只打印每一步结果
    python tests/run_smoke.py -v         # 把子进程输出也打出来
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

# 可选依赖：只有「生成/换封面」需要 Pillow + numpy；其余全部只用标准库。
try:
    import numpy  # noqa: F401
    from PIL import Image  # noqa: F401
    HAVE_ART = True
except Exception:
    HAVE_ART = False

# 1×1 PNG，够用作冒烟里的插图（不依赖 Pillow 也能造图）
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
PY = sys.executable

DIRTY = [
    "他说：“你来啦...”",
    "她    点点头，--  然后走了。",
    "这不是个傻.逼吗？",
    "第一句没有句号",
    "…… 嗯，也行～",
    "他说\"走吧\"，她就跟着走了。",
]

PLAIN = [
    "夜里下了一场雨。",
    "她坐在窗边，听雨水敲着铁皮棚顶。",
    "“你还没睡？”他在门外问。",
    "“睡了。”她答。",
    "门外的脚步声停了停，又远了。",
    "她把灯关了，屋里一下子黑下来。",
]


def run(cmd, verbose=False, expect=0):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if verbose or r.returncode != expect:
        print("$", " ".join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd)))
        if r.stdout.strip():
            print(r.stdout.strip())
        if r.stderr.strip():
            print(r.stderr.strip())
    return r


def make_fixture(tmp):
    raw_dir = os.path.join(tmp, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    chs = []
    # 第 1 章：脏数据（测规范化）
    chs.append({"num": 1, "title": "雨夜", "display": "第一章", "paragraphs": list(DIRTY),
                "part": "上卷", "note": ["今晚更得晚，抱歉……"]})
    # 第 2–3 章：正常；第 2 章带插图（after=3 段之后）
    chs.append({"num": 2, "title": "门", "display": "第二章", "paragraphs": list(PLAIN),
                "part": "上卷"})
    chs.append({"num": 3, "title": "灯", "display": "第三章",
                "paragraphs": ["灯是黄的。", "她数到第七下，睡着了。"], "part": "上卷"})
    # 第 4 章：超长章（测 --split-chars）
    long_paras = []
    for i in range(60):
        long_paras.append(f"这是第 {i + 1} 段，用来把这一章撑到很长，以便测试自动分节。" * 4)
    chs.append({"num": 4, "title": "长夜", "display": "第四章", "paragraphs": long_paras,
                "part": "下卷"})
    chs.append({"num": 5, "title": "天亮", "display": "第五章", "paragraphs": list(PLAIN),
                "part": "下卷"})
    chs.append({"num": 6, "title": "番外·后来", "display": "番外一", "paragraphs": list(PLAIN),
                "part": "下卷"})
    # 第 2 章插图
    imgdir = os.path.join(tmp, "raw", "img")
    os.makedirs(imgdir, exist_ok=True)
    fig = os.path.join(imgdir, "fig1.png")
    with open(fig, "wb") as f:
        f.write(TINY_PNG)
    chs[1]["figures"] = [{"after": 3, "file": "img/fig1.png", "alt": "雨夜的门", "caption": "图一"}]

    raw = os.path.join(raw_dir, "chapters.json")
    with open(raw, "w", encoding="utf-8") as f:
        json.dump(chs, f, ensure_ascii=False, indent=1)
    meta = {
        "title": "测试书", "author": "某作者", "platform": "", "status": "完结",
        "tags": ["测试"], "intro": ["这是一个测试简介。", "第二段。"],
        "words_hint": "", "cover": "",
        "parts": [{"label": "上卷", "from": 1, "to": 3}, {"label": "下卷", "from": 4, "to": 6}],
    }
    meta_path = os.path.join(raw_dir, "book.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    return raw, meta_path


def make_cover(tmp, out, gradient="night"):
    r = run([PY, os.path.join(SCRIPTS, "make_cover.py"), "测试书", "某作者",
             "--gradient", gradient, "--out", out])
    return r.returncode == 0 and os.path.exists(out)


def make_part_files(tmp, chapters):
    """模拟审校交稿：每章一个 JSON（覆盖全部章节），其中 1、2 章改两处。"""
    d = os.path.join(tmp, "out", "p1")
    os.makedirs(d, exist_ok=True)
    for ch in chapters:
        paras = list(ch["paragraphs"])
        if ch["num"] == 1:
            paras[0] = "他说：“你来啦……”"          # 只改标点
            paras[3] = "第一句没有句号。"            # 补句号
        with open(os.path.join(d, f"ch{ch['num']:03d}.json"), "w", encoding="utf-8") as f:
            json.dump({"num": ch["num"], "title": ch["title"], "paragraphs": paras},
                      f, ensure_ascii=False, indent=1)
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--keep", action="store_true", help="保留临时目录")
    args = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="ns_smoke_")
    fails = []

    def step(name, ok, detail=""):
        print(("[OK]   " if ok else "[FAIL] ") + name + (f"  {detail}" if detail else ""))
        if not ok:
            fails.append(name)

    try:
        raw, meta = make_fixture(tmp)
        cover = os.path.join(tmp, "cover.jpg")
        if HAVE_ART:
            step("make_cover 生成封面", make_cover(tmp, cover))
        else:
            print("[SKIP] make_cover 生成封面（未安装 Pillow/numpy；其余步骤照常跑）")

        # 1 规范化
        norm = os.path.join(tmp, "norm.json")
        r = run([PY, os.path.join(SCRIPTS, "normalize.py"), raw, "-o", norm,
                 "--report", os.path.join(tmp, "norm.txt")], args.verbose)
        step("normalize.py", r.returncode == 0 and os.path.exists(norm),
             r.stdout.splitlines()[1] if r.returncode == 0 and len(r.stdout.splitlines()) > 1 else "")
        with open(norm, encoding="utf-8") as f:
            norm_chs = json.load(f)
        body1 = "".join(norm_chs[0]["paragraphs"])
        step("规范化生效（省略号/规避符/全角）",
             "……" in body1 and "傻逼" in body1 and "." not in body1.replace("……", ""),
             body1[:38])
        step("note 被保留并规范化", norm_chs[0].get("note") == ["今晚更得晚，抱歉……"])

        # 2 构建（有封面 + 部卷 + 插图 + 长章分节 + new-id）
        r = run([PY, os.path.join(SCRIPTS, "build_book.py"), norm, "--meta", meta,
                 "-n", "测试书（抓取版）", "--outdir", tmp, "--split-chars", "3000",
                 "--new-id"], args.verbose)
        epub = os.path.join(tmp, "测试书（抓取版）.epub")
        txt = os.path.join(tmp, "测试书（抓取版）.txt")
        step("build_book.py", r.returncode == 0 and os.path.exists(epub) and os.path.exists(txt),
             r.stdout.splitlines()[-1] if r.returncode == 0 else "")
        step("识别部/卷与长章分节", "分组" in r.stdout and "分节" in r.stdout)
        step("生成新 identifier", "identifier" in r.stdout.lower())

        # 3 校验
        r = run([PY, os.path.join(SCRIPTS, "validate_epub.py"), epub, "--chapters", norm,
                 "--strict-platform"], args.verbose)
        step("validate_epub.py", "RESULT: PASS" in r.stdout, r.stdout.strip().splitlines()[-1] if r.stdout else "")

        # 4 无封面
        r = run([PY, os.path.join(SCRIPTS, "build_book.py"), norm, "--meta", meta,
                 "-n", "测试书（无封面）", "--outdir", tmp, "--no-cover"], args.verbose)
        epub2 = os.path.join(tmp, "测试书（无封面）.epub")
        r2 = run([PY, os.path.join(SCRIPTS, "validate_epub.py"), epub2, "--chapters", norm])
        step("--no-cover 构建 + 校验", r.returncode == 0 and "RESULT: PASS" in r2.stdout)

        # 4b txt 前页与「作者有话要说」标记、页脚自动生成
        with open(txt, encoding="utf-8") as f:
            txt_body = f.read()
        step("txt 含【作者有话要说】标记", "【作者有话要说】" in txt_body)
        step("页脚篇幅自动生成且含番外",
             "篇　幅：全 6 章（含 1 篇番外）" in txt_body, 
             [ln for ln in txt_body.splitlines() if ln.startswith("篇　幅")][:1])

        # 4c 重号 + --renumber
        dup = os.path.join(tmp, "dup.json")
        dup_chs = json.loads(json.dumps(norm_chs))
        dup_chs[1]["display"] = dup_chs[0]["display"]  # 人为造重号
        with open(dup, "w", encoding="utf-8") as f:
            json.dump(dup_chs, f, ensure_ascii=False)
        r = run([PY, os.path.join(SCRIPTS, "complete_check.py"), dup], args.verbose)
        step("complete_check 报重号", "display 重复" in r.stdout, "")
        r = run([PY, os.path.join(SCRIPTS, "build_book.py"), dup, "--meta", meta,
                 "-n", "重号书", "--outdir", tmp, "--no-cover", "--renumber"], args.verbose)
        with open(os.path.join(tmp, "重号书.txt"), encoding="utf-8") as f:
            dup_txt = f.read()
        heads = [ln.split("　")[0] for ln in dup_txt.splitlines()
                 if ln.startswith("第") and "章" in ln.split("　")[0]]
        step("--renumber 治重号", r.returncode == 0 and len(heads) == len(set(heads)) == 5, heads[:3])

        if HAVE_ART:
            # 4d inject_cover 必须刷新 dcterms:modified
            import re as _re
            import zipfile as _zip
            cover2 = os.path.join(tmp, "cover2.jpg")
            make_cover(tmp, cover2, gradient="dusk")
            meta2_path = os.path.join(tmp, "book_cover.json")
            with open(meta, encoding="utf-8") as f:
                meta2 = json.load(f)
            meta2["cover"] = cover
            with open(meta2_path, "w", encoding="utf-8") as f:
                json.dump(meta2, f, ensure_ascii=False)
            epub3 = os.path.join(tmp, "带封书.epub")
            r = run([PY, os.path.join(SCRIPTS, "build_book.py"), norm, "--meta", meta2_path,
                     "-n", "带封书", "--outdir", tmp], args.verbose)
            with _zip.ZipFile(epub3) as z:
                old_mod = _re.search(r"dcterms:modified\">([^<]+)",
                                     z.read("OEBPS/content.opf").decode("utf-8")).group(1)
            r = run([PY, os.path.join(SCRIPTS, "inject_cover.py"), epub3, cover2], args.verbose)
            with _zip.ZipFile(epub3) as z:
                new_mod = _re.search(r"dcterms:modified\">([^<]+)",
                                     z.read("OEBPS/content.opf").decode("utf-8")).group(1)
            step("inject_cover 刷新 dcterms:modified", r.returncode == 0 and new_mod != old_mod,
                 f"{old_mod} → {new_mod}")
        else:
            print("[SKIP] 换封面与 dcterms:modified 检查（未安装 Pillow/numpy）")

        # 4e 审校前置：读懂材料必须齐全
        reading = os.path.join(tmp, "reading")
        r = run([PY, os.path.join(SCRIPTS, "read_prep.py"), norm, "-o", reading], args.verbose)
        want = ["outline.md", "roster.md", "style.md", "reading_brief.md"]
        ok = r.returncode == 0 and all(os.path.exists(os.path.join(reading, f)) for f in want)
        step("read_prep 生成理解材料", ok, "、".join(want))
        with open(os.path.join(reading, "outline.md"), encoding="utf-8") as f:
            outline = f.read()
        with open(os.path.join(reading, "reading_brief.md"), encoding="utf-8") as f:
            brief = f.read()
        step("理解材料含章节表与九节模板",
             "| 章 | 标题 |" in outline and "留白清单" in brief and "一句话" in brief)

        # 4f 留白闸门：别的节空着要 FAIL，留白空着只 WARN
        brief_path = os.path.join(reading, "reading_brief.md")
        filled = """# 理解备忘
## 1. 一句话
某甲与某乙重逢又分开，写的是得不到。
## 2. 主线（三到五段）
某甲和某乙重逢，最后分开。
## 3. 人物表
| 名字 | 性别 | 身份/关系 | 说话与行为特征 | 结局 |
|---|---|---|---|---|
| 某甲 | 女 | 姐姐 | 少话 | 离开 |
## 4. 叙述方式
第一人称，跟着某甲走。
## 5. 语言与语气
短句多，省略号多。
## 6. 反复出现的意象 / 母题
雨、灯、门。
## 7. 留白清单（最容易被我"补"坏的地方）
第3章末只写"她走了"，不写去哪，是留白。
## 8. 本作审校红线
不改方言，不补引号。
## 9. 读完之后的三句话自检
能说清在写什么；能说清指代；知道哪些是刻意。
"""
        with open(brief_path, "w", encoding="utf-8") as f:
            f.write(filled)
        r = run([PY, os.path.join(SCRIPTS, "check_reading.py"), brief_path], args.verbose)
        step("check_reading 全填 → PASS", r.returncode == 0 and "PASS" in r.stdout)

        blank = filled.replace('第3章末只写"她走了"，不写去哪，是留白。\n', "")
        with open(brief_path, "w", encoding="utf-8") as f:
            f.write(blank)
        r = run([PY, os.path.join(SCRIPTS, "check_reading.py"), brief_path], args.verbose)
        step("check_reading 留白空 → WARN 但放行", r.returncode == 0 and "WARN" in r.stdout)

        with open(brief_path, "w", encoding="utf-8") as f:
            f.write(filled.replace("某甲与某乙重逢又分开，写的是得不到。", "{一句话说清}"))
        r = run([PY, os.path.join(SCRIPTS, "check_reading.py"), brief_path], args.verbose, expect=1)
        step("check_reading 其他节空 → FAIL", r.returncode == 1 and "FAIL" in r.stdout)

        # txt ↔ epub 一致性（同一本书两份交付必须一致）
        txts = sorted(glob.glob(os.path.join(tmp, "*.txt")))
        epbs = sorted(glob.glob(os.path.join(tmp, "*.epub")))
        txtp = next((p for p in txts if "抓取版" in p), txts[0] if txts else "")
        epbp = next((p for p in epbs if "抓取版" in p), epbs[0] if epbs else "")
        if txtp and epbp:
            r = run([PY, os.path.join(SCRIPTS, "check_txt.py"), txtp, epbp], args.verbose)
            step("check_txt.py txt↔epub 一致", "RESULT: PASS" in r.stdout,
                 r.stdout.strip().splitlines()[0] if r.stdout else "")
            with open(txtp, "a", encoding="utf-8") as f:
                f.write(chr(10) + "多出来的一行" + chr(10))
            r = run([PY, os.path.join(SCRIPTS, "check_txt.py"), txtp, epbp], args.verbose, expect=1)
            step("check_txt 抓出多余行", r.returncode == 1 and "FAIL" in r.stdout, "应当 FAIL")
        else:
            step("check_txt.py txt↔epub 一致", False, "没找到构建产物")

        # patch_epub：给“已有 epub”改前页 + 修目录（不需要 chapters.json）
        n_all = len(norm_chs)
        pe = os.path.join(tmp, "patchme.epub")
        shutil.copyfile(epbp, pe)
        intro_md = os.path.join(tmp, "intro_patch.md")
        with open(intro_md, "w", encoding="utf-8") as f:
            f.write("第一段简介。" + chr(10) + chr(10) + "# 小标题" + chr(10) + chr(10) + "第二段。" + chr(10))
        r = run([PY, os.path.join(SCRIPTS, "patch_epub.py"), pe,
                 "--title", "测试书", "--author", "某作者", "--titlepage",
                 "--intro-file", intro_md, "--colophon", "--words", "0.1", "--chapters", str(n_all),
                 "--fix-nav", "--refresh-modified"], args.verbose)
        step("patch_epub.py 改前页+修目录", r.returncode == 0 and "OK 已写入" in r.stdout,
             r.stdout.strip().splitlines()[-1] if r.stdout else "")
        r = run([PY, os.path.join(SCRIPTS, "validate_epub.py"), pe], args.verbose)
        step("patch_epub 产物通过结构校验", "RESULT: PASS" in r.stdout,
             r.stdout.strip().splitlines()[-1] if r.stdout else "")

        # 5 审校链路：分卷稿 → check_part → merge_parts
        partdir = make_part_files(tmp, norm_chs)
        n_all = len(norm_chs)
        r = run([PY, os.path.join(SCRIPTS, "check_part.py"), partdir, f"1-{n_all}",
                 "--src", norm], args.verbose)
        step("check_part.py", "RESULT: PASS" in r.stdout, r.stdout.strip().splitlines()[0] if r.stdout else "")
        r = run([PY, os.path.join(SCRIPTS, "check_part.py"), partdir, "1-2",
                 "--src", norm], args.verbose, expect=1)
        step("check_part 越界章 → FAIL",
             r.returncode == 1 and "不在分卷范围" in r.stdout, "越界章应 FAIL")
        missing_dir = os.path.join(tmp, "p_missing")
        os.makedirs(missing_dir, exist_ok=True)
        src_files = sorted(glob.glob(os.path.join(partdir, "ch*.json")))
        for f in src_files:
            if os.path.basename(f) != "ch002.json":
                shutil.copyfile(f, os.path.join(missing_dir, os.path.basename(f)))
        r = run([PY, os.path.join(SCRIPTS, "check_part.py"), missing_dir, f"1-{n_all}",
                 "--src", norm], args.verbose, expect=1)
        step("check_part 缺章 → FAIL",
             r.returncode == 1 and "分卷缺章" in r.stdout, "缺章应 FAIL")
        merged = os.path.join(tmp, "merged.json")
        r = run([PY, os.path.join(SCRIPTS, "merge_parts.py"), os.path.dirname(partdir),
                 "-o", merged, "--src", norm], args.verbose)
        ok = r.returncode == 0 and os.path.exists(merged)
        step("merge_parts.py", ok, r.stdout.strip() if ok else "")
        with open(merged, encoding="utf-8") as f:
            mg = json.load(f)
        step("合并保留部/卷与作者有话要说",
             mg[0].get("part") == "上卷" and mg[0].get("note") == norm_chs[0]["note"])
        step("合并保留插图", mg[1].get("figures") == norm_chs[1]["figures"])

        # 6 指代扫描 / 应用 / diff / 终检
        r = run([PY, os.path.join(SCRIPTS, "pron_scan.py"), merged,
                 "--female", "她甲,她乙", "--male", "他甲", "-o", os.path.join(tmp, "pron.md")],
                args.verbose)
        step("pron_scan.py", r.returncode == 0)
        edits = os.path.join(tmp, "edits.json")
        with open(edits, "w", encoding="utf-8") as f:
            json.dump([{"num": 2, "para": 3,
                        "before": mg[1]["paragraphs"][2],
                        "after": mg[1]["paragraphs"][2].replace("他", "他甲", 1),
                        "reason": "冒烟测试：代词→人名"}], f, ensure_ascii=False, indent=1)
        fixed = os.path.join(tmp, "fixed.json")
        r = run([PY, os.path.join(SCRIPTS, "apply_pron.py"), merged, edits,
                 "--names", "她甲,她乙,他甲", "-o", fixed,
                 "--report", os.path.join(tmp, "applied.md")], args.verbose)
        step("apply_pron.py", r.returncode == 0 and os.path.exists(fixed))
        r = run([PY, os.path.join(SCRIPTS, "make_diff.py"), merged, fixed,
                 "-o", os.path.join(tmp, "diff.md")], args.verbose)
        step("make_diff.py", r.returncode == 0 and os.path.exists(os.path.join(tmp, "diff.md")))
        r = run([PY, os.path.join(SCRIPTS, "final_check.py"), merged,
                 "--names", "她甲,她乙,他甲", "--out", os.path.join(tmp, "final.md")], args.verbose)
        step("final_check.py", r.returncode == 0)

        # 7 textcheck 阈值自检
        sys.path.insert(0, SCRIPTS)
        import textcheck  # noqa: E402
        real, why_real = textcheck.looks_real("".join(PLAIN) * 6)
        fake, why_fake = textcheck.looks_real("".join(chr(0x4E00 + (i * 977) % 20902)
                                                      for i in range(600)))
        step("textcheck 判真", real, why_real)
        step("textcheck 判伪", not fake, why_fake)
    finally:
        if args.keep:
            print("临时目录:", tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    print()
    if fails:
        print(f"FAILED: {len(fails)} 项 → {', '.join(fails)}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
