#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 SKILL.md 的结构完整性。

不依赖 pyyaml —— 手工解析 frontmatter，
因为本机 Python 环境未必装 pyyaml，而校验脚本本身不该有额外依赖。

检查项：
  1. frontmatter 存在且闭合
  2. 必需字段 name / description 存在
  3. name 与所在目录名一致（技能发现依赖此约定）
  4. description 含 Use when / Not for / Triggers 三类语境
  5. 正文非空、以 # 标题开头
  6. 正文中引用的本地文件真实存在（防止断链）
  7. 脚本文件语法可编译
"""

import io
import os
import py_compile
import re
import sys

REQUIRED_KEYS = ["name", "description"]
DESC_MARKERS = ["Use when", "Not for", "Triggers"]


class Checker:
    def __init__(self):
        self.ok = 0
        self.bad = []

    def check(self, cond, desc, detail=""):
        if cond:
            self.ok += 1
            print(f"  PASS  {desc}")
        else:
            self.bad.append(desc)
            print(f"  FAIL  {desc}")
            if detail:
                print(f"        {detail}")


def parse_frontmatter(text):
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", text, re.S)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    skill_path = os.path.join(root, "SKILL.md")

    ck = Checker()
    print("=" * 62)
    print("  SKILL.md 结构校验")
    print("=" * 62)

    if not os.path.isfile(skill_path):
        print(f"  ✗ 找不到 {skill_path}")
        return 1

    text = io.open(skill_path, encoding="utf-8").read()
    fm, body = parse_frontmatter(text)

    print("\n[1] frontmatter")
    ck.check(fm is not None, "frontmatter 存在且用 --- 闭合")
    if fm is None:
        return 1

    keys = [l.split(":", 1)[0] for l in fm.splitlines()
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*:", l)]
    ck.check(True, f"顶层键：{', '.join(keys)}")
    for k in REQUIRED_KEYS:
        ck.check(k in keys, f"必需字段存在：{k}")

    # name 与目录名一致
    name_line = [l for l in fm.splitlines() if l.startswith("name:")]
    ck.check(len(name_line) == 1, "name 字段只有一行")
    if name_line:
        nm = name_line[0].split(":", 1)[1].strip().strip('"').strip("'")
        ck.check(nm == os.path.basename(root),
                 f"name 与目录名一致（{nm}）",
                 f"目录名是 {os.path.basename(root)}")

    # description 的触发语境
    print("\n[2] description 触发语境")
    dm = re.search(r'^description:\s*"(.*?)"\s*$', fm, re.M | re.S)
    if dm:
        desc = dm.group(1)
        ck.check(len(desc) > 200, f"description 足够详细（{len(desc)} 字符）")
        for mk in DESC_MARKERS:
            ck.check(mk in desc, f"含触发语境标记：{mk}")
        ck.check("Triggers" in desc and "," in desc.split("Triggers")[-1],
                 "Triggers 里有逗号分隔的关键词列表")
    else:
        ck.check(False, "description 用双引号包裹（多行/含冒号时必须如此）")

    # 正文
    print("\n[3] 正文")
    ck.check(body is not None and len(body.strip()) > 200,
             f"正文非空（{len(body or '')} 字符）")
    first = (body or "").strip().splitlines()[0] if (body or "").strip() else ""
    ck.check(first.startswith("#"), f"正文以一级标题开头", f"首行是 {first[:40]!r}")

    # 引用完整性
    print("\n[4] 引用完整性")
    refs = sorted(set(re.findall(r"\]\(([^)\s]+)\)", body or "")))
    local = [r for r in refs if not r.startswith(("http://", "https://", "#"))]
    missing = [r for r in local
               if not os.path.isfile(os.path.join(root, r.split("#")[0]))]
    ck.check(len(local) > 0, f"正文引用了 {len(local)} 个本地文件")
    ck.check(not missing, "所有本地引用都存在（无断链）",
             f"缺失：{missing}" if missing else "")

    # 脚本可编译
    print("\n[5] 脚本语法")
    for rel in ["scripts/apk_report.py", "self_test.py"]:
        p = os.path.join(root, rel)
        if os.path.isfile(p):
            try:
                py_compile.compile(p, doraise=True)
                ck.check(True, f"{rel} 语法可编译")
            except py_compile.PyCompileError as e:
                ck.check(False, f"{rel} 语法可编译", str(e)[:120])
        else:
            ck.check(False, f"{rel} 存在")

    # 红线：仓库内不得有 APK
    print("\n[6] 红线：不含 APK / 业务代码")
    bad = []
    for dirpath, _, files in os.walk(root):
        if ".git" in dirpath:
            continue
        for f in files:
            if f.endswith((".apk", ".aab", ".dex", ".so")):
                bad.append(os.path.relpath(os.path.join(dirpath, f), root))
    ck.check(not bad, "仓库内无 APK/AAB/dex/so",
             f"发现：{bad}" if bad else "")

    print("\n" + "=" * 62)
    if ck.bad:
        print(f"  结果：{ck.ok} 通过 / {len(ck.bad)} 失败")
        for d in ck.bad:
            print(f"    ✗ {d}")
        print("=" * 62)
        return 1
    print(f"  结果：全部 {ck.ok} 项通过 ✅")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
