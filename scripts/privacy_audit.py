#!/usr/bin/env python3
"""隐私审计：确认仓库里没有来源项目的可识别信息。

本 skill 来自真实项目的实践。写文档时为了把问题讲清楚，
**必然会带进来源项目的可识别信息** —— 这是自然发生的，不是疏忽。
所以设一道可执行的关卡，不靠"我记得清理过"。

用法：
    python scripts/privacy_audit.py                 # 扫当前目录
    python scripts/privacy_audit.py --root <路径>    # 扫指定目录

退出码：0 = 干净；1 = 有命中（可用于 CI / pre-commit）。

---

## 为什么做成脚本，而不是文档里几条 grep

两个原因，都是踩出来的：

1. **判据必须只有一份**。曾经出现 CONTRIBUTING 里的判据已收紧、
   而抽查脚本还用旧判据，于是报出假阳性 —— 规则改了、用规则的地方没改。
2. **正则在中文范围上容易写错**。`[\\u4e00-\\u9fa5]` 写在 Python raw string 里
   不会解释成 unicode 转义，而会变成字符类 {反斜杠, u, 4, e, 0, a, 5}，
   于是 `E:\\AndroidDev4` 这类普通路径也会命中。
   用 `chr(0x4E00)` 拼出区间最不容易出错。

## 判据设计原则：要求"像真值"，而不是"出现过关键词"

宽松判据（匹配 `sk-`、`apiKey=`、`/c/Users`）在干净仓库上会稳定产生假阳性，
**而一条会误报的规则等于没有规则** —— 使用者会训练自己忽略它的输出。
所以这里每条判据都要求"看起来确实是那个东西"：
密钥要够长、路径里的用户名不能是占位符、中文必须出现在路径段内。
"""
import argparse
import io
import os
import re
import sys

# ---- 判据 ----

# ① 密钥：sk- 后 ≥16 位字母数字（占位符 sk-... 不会命中）
RE_SECRET = re.compile(r"sk-[A-Za-z0-9]{16,}")

# ② 项目标识：**刻意留空**。
#
#    这里有一个绕不开的矛盾：脚本需要知道"要查什么"，但脚本本身在公开仓库里 ——
#    把真实项目名写进来，等于用脚本自己完成了泄漏。
#
#    所以真实值通过环境变量注入（逗号分隔）：
#        PRIVACY_MARKS="myproject,myalias" python scripts/privacy_audit.py
#    本地/CI 用它；公开仓库里的这份保持干净。
#    没设该变量时，这一类跳过（其余三类仍然生效）。
PROJECT_MARKS = [
    m.strip() for m in os.environ.get("PRIVACY_MARKS", "").split(",") if m.strip()
]

# ③ 本机绝对路径：要求用户名是"真值"，不是 < > % $ 这类占位符
RE_USERS_WIN = re.compile(r"[A-Z]:\\+Users\\+([^\s`\"'\\]*)")
RE_USERS_NIX = re.compile(r"/c/Users/([^\s`\"'/]*)")
# 中文目录：要求中文出现在**路径段内**（两个反斜杠之间）—— 见 README 的说明
RE_CJK_DIR = re.compile(
    "[A-Z]:\\\\+[^\\\\\\s]*[" + chr(0x4E00) + "-" + chr(0x9FA5) + "][^\\\\\\s]*\\\\"
)

# ④ 不应进仓库的文件类型
FORBIDDEN_EXT = (
    ".kt", ".kts", ".java", ".gradle", ".xml", ".apk", ".aab", ".dex",
    ".so", ".jar", ".csv", ".wav", ".onnx", ".docx", ".pdf", ".xlsx",
)

# ---- 白名单 ----

# 规则文档自身：必然写着上面这些模式，属规则文本而非泄漏
RULE_DOCS = {"CONTRIBUTING.md", "scripts/privacy_audit.py"}

# 已知的**反面示例路径**：文档里刻意用中文目录举例说明
# "中文路径会导致构建失败"，属必要内容，保留。
KNOWN_EXAMPLE_DIRS = (
    chr(0x5DE5) + chr(0x4F5C),          # "工作"
    chr(0x6211) + chr(0x7684) + chr(0x9879) + chr(0x76EE),  # "我的项目"
)

SCAN_EXT = (".md", ".ps1", ".py", ".json", ".toml", ".txt", ".yml", ".yaml")


def scan_text(text: str, name: str) -> list:
    """返回该文件的命中列表。"""
    bad = []

    if name.endswith(FORBIDDEN_EXT):
        bad.append("文件类型 " + os.path.splitext(name)[1])

    if RE_SECRET.search(text):
        bad.append("含疑似密钥（sk- 后 ≥16 位字母数字）")

    for mark in PROJECT_MARKS:
        if mark in text:
            bad.append("含项目标识 " + mark)

    for m in RE_USERS_WIN.finditer(text):
        user = m.group(1)
        if user and user[0] not in "<>%$" and not user.startswith("$"):
            bad.append("含本机用户名 " + user[:12])
    for m in RE_USERS_NIX.finditer(text):
        user = m.group(1)
        if user and user[0] not in "<>%$" and not user.startswith("$"):
            bad.append("含本机用户名 " + user[:12])

    for m in RE_CJK_DIR.finditer(text):
        seg = m.group(0)
        if not any(d in seg for d in KNOWN_EXAMPLE_DIRS):
            bad.append("含中文目录路径 " + seg.strip()[:24])

    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description="隐私审计：确认仓库无可识别信息")
    ap.add_argument("--root", default=".", help="要扫描的根目录（默认当前目录）")
    args = ap.parse_args()
    root = os.path.abspath(args.root)

    print("=" * 70)
    print("隐私审计")
    print("  root:", root)
    print("=" * 70)

    hits = 0
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        for fn in filenames:
            if not fn.endswith(SCAN_EXT):
                # 但文件类型违规也要查（例如混进来的 .apk）
                if fn.endswith(FORBIDDEN_EXT):
                    rel = os.path.relpath(os.path.join(dirpath, fn), root)
                    print("  X %s -> 不应进仓库的文件类型" % rel)
                    hits += 1
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/")
            if rel in RULE_DOCS:
                continue
            scanned += 1
            p = os.path.join(dirpath, fn)
            try:
                text = io.open(p, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            bad = scan_text(text, rel)
            if bad:
                hits += 1
                print("  X %s" % rel)
                for b in bad:
                    print("      - %s" % b)

    print()
    print("  扫描 %d 个文本文件" % scanned)
    if hits == 0:
        print("  结果：0 命中 ✅")
        print("    - 无密钥、无项目标识、无本机用户名、无真实中文项目路径")
        print("    - 无代码/工程化/数据类文件")
        return 0
    print("  结果：%d 个文件命中 ⚠" % hits)
    print("  处置：逐个判断是**真泄漏**还是**规则文本/占位符示例**。")
    print("        真泄漏 → 泛化；规则文本 → 加入 RULE_DOCS；")
    print("        必要的中文反面示例 → 加入 KNOWN_EXAMPLE_DIRS（并在此说明理由）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
