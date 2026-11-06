# -*- coding: utf-8 -*-
"""模拟「没装任何第三方库」的干净环境：屏蔽 requests/PIL/numpy/Crypto，再跑两套测试。

用法：python tests/run_bare.py
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

STUB = """# 放在 PYTHONPATH 最前面：让这些三方库 import 失败
import sys

BLOCKED = ("PIL", "numpy", "requests", "Crypto", "urllib3", "socks")


class _Block:
    def find_module(self, name, path=None):
        return self if name.split(".")[0] in BLOCKED else None

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ImportError("blocked by run_bare.py: " + name)
        return None

    def load_module(self, name):
        raise ImportError("blocked by run_bare.py: " + name)


sys.meta_path.insert(0, _Block())
"""


def main():
    tmp = tempfile.mkdtemp(prefix="ns_bare_")
    with open(os.path.join(tmp, "sitecustomize.py"), "w", encoding="utf-8") as f:
        f.write(STUB)
    env = dict(os.environ)
    env["PYTHONPATH"] = tmp + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"

    rc = 0
    for script in ("tests/run_smoke.py", "tests/verify_review_fixes.py"):
        print(f"\n=== {script}（无 Pillow/numpy/requests）")
        r = subprocess.run([sys.executable, os.path.join(ROOT, script)],
                           cwd=ROOT, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        tail = [ln for ln in r.stdout.strip().splitlines()[-8:]]
        print("\n".join(tail))
        if r.returncode != 0:
            rc = 1
            if r.stderr.strip():
                print("STDERR:", r.stderr.strip()[-800:])
    print("\n" + ("BARE OK" if rc == 0 else "BARE FAILED"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
