# -*- coding: utf-8 -*-
"""复跑独立审查报告里已确认的 P0 用例，确认修好了。"""
import io
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "scripts")
PY = sys.executable
ok_all = True


def run(args, expect=0):
    r = subprocess.run([PY] + args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r


def check(name, cond, extra=""):
    global ok_all
    print(("[OK]   " if cond else "[FAIL] ") + name + ("" if cond else "  " + extra))
    ok_all = ok_all and bool(cond)


tmp = tempfile.mkdtemp(prefix="ns_verify_")

# 1 normalize：不能误删斜杠/间隔号
sys.path.insert(0, S)
import normalize as N  # noqa: E402

cases = [
    ("他/她说", "他/她说"),
    ("和/或", "和/或"),
    ("玛丽·雪莱", "玛丽·雪莱"),
    ("第一.章 回国", "第一章 回国"),  # 汉字旁空格会被合并规则去掉，见下条断言
    ("他说「走」。", "他说「走」。"),
]
for src, want in cases:
    got = N.normalize_paragraph(src)
    check(f"normalize {src!r} -> {got!r}", got.replace(" ", "") == want.replace(" ", ""), f"want {want!r}")

check("normalize 还原 傻.逼", N.normalize_paragraph("你个傻.逼") == "你个傻逼")
check("normalize 还原 做/爱", N.normalize_paragraph("他们在做/爱") == "他们在做爱")
check("normalize 不误删 38.7", N.normalize_paragraph("气温 38.7 度") == "气温 38.7 度")

# 2 build_book：序章不再被误判成番外
chs = [{"num": i, "title": t, "display": d, "paragraphs": ["正文" * 40]}
       for i, (t, d) in enumerate([("序章", "序章"), ("回国", "第1章"), ("重逢", "第2章"),
                                   ("番外·时间", "番外·时间")], 1)]
import build_book as B  # noqa: E402

seq = [dict(c) for c in chs]
B.auto_display(seq)   # 原地改列表，无返回值
disp = [c["display"] for c in seq]
check("auto_display 序章不被当成番外", disp[0] != "番外一", str(disp))
check("auto_display 番外被识别", any(d.startswith("番外") for d in disp[1:]), str(disp))

# 3 空书 / 缺 title → 非零退出
empty = os.path.join(tmp, "empty.json")
io.open(empty, "w", encoding="utf-8").write(json.dumps({"chapters": []}))
meta = os.path.join(tmp, "book.json")
io.open(meta, "w", encoding="utf-8").write(json.dumps({"title": "", "author": ""}))
r = run([os.path.join(S, "build_book.py"), empty, "--meta", meta, "-n", "x", "--outdir", tmp])
check("空书构建返回非零", r.returncode != 0, r.stdout[-100:] + r.stderr[-100:])

# 4 textcheck txt 模式：假文必须非零
bad_txt = os.path.join(tmp, "bad.txt")
io.open(bad_txt, "w", encoding="utf-8").write("测试" * 600)
r = run([os.path.join(S, "textcheck.py"), bad_txt])
check("textcheck txt 模式判伪返回 1", r.returncode == 1, r.stdout[-80:])

# 5 complete_check：num 重号必须 FAIL，--allow-dup 才放过
dup = os.path.join(tmp, "dup.json")
io.open(dup, "w", encoding="utf-8").write(json.dumps({"chapters": [
    {"num": 1, "title": "a", "display": "第1章", "paragraphs": ["正文" * 60]},
    {"num": 2, "title": "b", "display": "第2章", "paragraphs": ["正文" * 60]},
    {"num": 2, "title": "c", "display": "第3章", "paragraphs": ["正文" * 60]},
]}))
r = run([os.path.join(S, "complete_check.py"), dup])
check("complete_check 重号 FAIL", r.returncode == 1 and "重复" in r.stdout, r.stdout[-120:])
r = run([os.path.join(S, "complete_check.py"), dup, "--allow-dup"])
check("complete_check --allow-dup 放行", r.returncode == 0, r.stdout[-120:])

# 6 read_prep：不覆盖已填的 reading_brief
chs_p = os.path.join(tmp, "chs.json")
io.open(chs_p, "w", encoding="utf-8").write(json.dumps({"chapters": [
    {"num": i, "title": f"t{i}", "display": f"第{i}章",
     "paragraphs": ["夜里下了一场雨。" * 8, "她坐在窗边。" * 8]} for i in range(1, 7)]}, ensure_ascii=False))
rd = os.path.join(tmp, "reading")
run([os.path.join(S, "read_prep.py"), chs_p, "-o", rd])
brief = os.path.join(rd, "reading_brief.md")
io.open(brief, "a", encoding="utf-8").write("\nMARKER_KEEP_ME\n")
run([os.path.join(S, "read_prep.py"), chs_p, "-o", rd])
check("read_prep 不覆盖手填 brief", "MARKER_KEEP_ME" in io.open(brief, encoding="utf-8").read())

# 7 apply_pron：有拒绝项时不写正式输出
ch = os.path.join(tmp, "ch.json")
io.open(ch, "w", encoding="utf-8").write(json.dumps({"chapters": [
    {"num": 1, "title": "a", "display": "第1章", "paragraphs": ["她笑了。"]}]}, ensure_ascii=False))
ed = os.path.join(tmp, "edits.json")
io.open(ed, "w", encoding="utf-8").write(json.dumps({"edits": [
    {"chapter": 1, "para": 1, "before": "她笑了。", "after": "她甲笑了。"},
    {"chapter": 99, "para": 1, "before": "不存在", "after": "也不存在"},
]}, ensure_ascii=False))
outp = os.path.join(tmp, "applied.json")
r = run([os.path.join(S, "apply_pron.py"), ch, ed, "--names", "甲,乙", "-o", outp])
check("apply_pron 有拒绝项返回 1", r.returncode == 1, r.stdout[-100:])
check("apply_pron 不在失败时写正式输出", not os.path.exists(outp))
check("apply_pron 写出 .partial", os.path.exists(outp + ".partial"))

print("\n" + ("ALL PASS" if ok_all else "SOME FAILED"))
sys.exit(0 if ok_all else 1)
