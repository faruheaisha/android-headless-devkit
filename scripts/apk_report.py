#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""APK 体积构成审计与"陈旧空洞"诊断。

只依赖 Python 标准库（zipfile / os / collections），不引入任何第三方包，
也不依赖 Android SDK —— 因为体积审计不该需要装一整套工具链。

用法：
    python apk_report.py app-debug.apk
    python apk_report.py app-release.apk --top 20
    python apk_report.py app.apk --json report.json

它会回答四个问题：
    1. 包体由什么构成？（按 lib/dex/res/assets 分类的占比）
    2. 哪几个文件最大？
    3. 有几个 ABI？dex 有几个？（判断 abiFilters 与 R8 是否生效）
    4. 文件大小与内容合计对不对得上？（对不对得上就是在暗示"陈旧空洞"）
"""

import argparse
import collections
import json
import os
import sys
import zipfile

# 只有压缩后 ≥ 此阈值的原生库才进入"体积敏感"提示。
# 实测：不设阈值时会把 0.01MB 的辅助库也报成体积大户，制造噪音。
NATIVE_HEAVY_THRESHOLD = 512 * 1024

# 常见"体积大户"原生库的特征关键字 —— 用于提示排查方向
HEAVY_NATIVE_HINTS = {
    "onnxruntime": "ONNX Runtime（推理引擎）",
    "libmlkit": "ML Kit",
    "libtensorflow": "TensorFlow Lite",
    "libopencv": "OpenCV",
    "libopencv_mobile": "opencv-mobile",
    "libavcodec": "FFmpeg",
    "libavformat": "FFmpeg",
    "libwebrtc": "WebRTC",
    "libflutter": "Flutter 引擎",
    "libreactnative": "React Native",
    "libhermes": "Hermes JS 引擎",
    "libimage_processing": "AndroidX 图像处理",
    "libdatastore": "DataStore",
}


def human(n):
    return f"{n / 1048576:.2f}MB"


def infer_build_type(path):
    """从文件名猜构建类型，用于让提示措辞贴合语境。

    产物名通常是 app-debug.apk / app-release-unsigned.apk。
    猜不出就返回 None，此时提示走中性措辞。
    """
    name = os.path.basename(path).lower()
    if "debug" in name:
        return "debug"
    if "release" in name:
        return "release"
    return None


def classify(name):
    if name.startswith("lib/"):
        parts = name.split("/")
        abi = parts[1] if len(parts) > 2 else "?"
        return f"lib/{abi}"
    if name.startswith("classes") and name.endswith(".dex"):
        return "dex"
    if name.startswith("res/"):
        return "res/"
    if name.startswith("assets/"):
        return "assets/"
    return "其他"


def analyze(path, top=12, do_gaps=True):
    size = os.path.getsize(path)
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        items = [(i.filename, i.file_size, i.compress_size, i.header_offset, i.extra)
                 for i in infos]

    groups = collections.defaultdict(lambda: [0, 0])
    for name, usize, csize, _, _ in items:
        k = classify(name)
        groups[k][0] += usize
        groups[k][1] += csize

    content = sum(c for _, _, c, _, _ in items)

    abis = sorted({n.split("/")[1] for n, _, _, _, _ in items
                   if n.startswith("lib/") and len(n.split("/")) > 2})
    native = [(n, c) for n, u, c, _, _ in items
              if n.startswith("lib/") and n.endswith(".so")]
    uncompr = [n for n, _ in native]
    dex = sorted(n for n, _, _, _, _ in items
                 if n.startswith("classes") and n.endswith(".dex"))

    out = {
        "file": os.path.abspath(path),
        "build_type": infer_build_type(path),
        "size_bytes": size,
        "size_human": human(size),
        "entries": len(items),
        "content_bytes": content,
        "content_human": human(content),
        "hole_bytes": size - content,
        "hole_human": human(max(0, size - content)),
        "groups": {k: {"uncompressed": v[0], "compressed": v[1]}
                   for k, v in sorted(groups.items(), key=lambda x: -x[1][1])},
        "abis": abis,
        "native_libs": uncompr,
        "dex_files": dex,
        # 只把"体积敏感且真的占地方"的原生库列入 native_heavy：
        # 阈值 0.5MB —— 实测若不加阈值，会把 0.01MB 的辅助库
        # （如 libdatastore_shared_counter.so）也误报成体积大户。
        "native_heavy": [{"name": n, "compressed": c}
                         for n, c in native if c >= NATIVE_HEAVY_THRESHOLD],
        "top_files": [],
        "gaps": [],
    }

    for name, usize, csize, _, _ in sorted(items, key=lambda x: -x[2])[:top]:
        out["top_files"].append({"name": name, "compressed": csize, "uncompressed": usize})

    # ---- 陈旧空洞诊断：定位条目间的空隙 ----
    if do_gaps:
        ordered = sorted(items, key=lambda x: x[3])
        prev_end = 0
        gaps = []
        for name, usize, csize, off, extra in ordered:
            if off > prev_end:
                gaps.append((off - prev_end, prev_end, name))
            # local file header = 30 字节固定 + 文件名 + extra
            end = off + 30 + len(name.encode("utf-8", "replace")) + len(extra) + csize
            prev_end = max(prev_end, end)
        gaps.sort(reverse=True)
        out["gaps"] = [{"bytes": g, "offset": o, "next_entry": n}
                       for g, o, n in gaps[:8]]
        out["gap_total_bytes"] = sum(g for g, _, _ in gaps)

    return out


def print_report(r):
    p = print
    p("=" * 64)
    p("  APK 体积审计")
    p("=" * 64)
    p(f"  文件        {r['file']}")
    p(f"  大小        {r['size_human']}   ({r['size_bytes']:,} 字节)")
    p(f"  条目数      {r['entries']}")
    p("")

    p("-- 构成（按压缩后大小排序）" + "-" * 36)
    p(f"  {'分类':<22}{'压缩后':>12}{'原始':>12}{'占比':>8}")
    for k, v in r["groups"].items():
        pct = v["compressed"] / r["size_bytes"] * 100 if r["size_bytes"] else 0
        p(f"  {k:<22}{human(v['compressed']):>12}"
          f"{human(v['uncompressed']):>12}{pct:>7.1f}%")
    p("")

    p("-- 最大的文件" + "-" * 51)
    for f in r["top_files"]:
        p(f"  {human(f['compressed']):>10}  {f['name'][:78]}")
    p("")

    p("-- 架构与 dex" + "-" * 51)
    p(f"  ABI         {', '.join(r['abis']) if r['abis'] else '(无原生库)'}")
    p(f"  原生库      {len(r['native_libs'])} 个")
    if r["native_heavy"]:
        total = sum(i["compressed"] for i in r["native_heavy"])
        pct = total / r["size_bytes"] * 100 if r["size_bytes"] else 0
        p(f"  其中占地方  {len(r['native_heavy'])} 个 ≥0.5MB，合计 {human(total)}"
          f"（{pct:.0f}% 的包体）")
    p(f"  dex 文件    {len(r['dex_files'])} 个")
    p("")

    # ---- 空洞诊断 ----
    hole = r["hole_bytes"]
    p("-- 陈旧空洞诊断" + "-" * 49)
    p(f"  内容合计    {r['content_human']}")
    p(f"  文件大小    {r['size_human']}")
    p(f"  差值        {r['hole_human']}")
    if hole > 1048576:
        p("  ⚠ 差值大于 1MB。常见原因是 Gradle 增量打包未截断旧文件，")
        p("    留下了一段陈旧空洞（旧 dex 残留）。它不影响运行，但会让")
        p("    体积读数虚高、污染优化决策。")
        p("    解法：删掉该 APK 后只重跑打包任务（通常 2 分钟），不必 clean。")
        if r.get("gaps"):
            p("  最大的几处空隙：")
            for g in r["gaps"][:5]:
                p(f"    {human(g['bytes']):>10} @ {human(g['offset']):>10}"
                  f"  之后是 {g['next_entry'][:44]}")
    else:
        p("  OK 差值正常（无显著空洞）")
    p("")

    # ---- 启发式提示 ----
    bt = r.get("build_type")
    is_release = (bt == "release")
    is_debug = (bt == "debug")

    tips = []
    if len(r["abis"]) > 1:
        if is_debug:
            tips.append(f"含多个 ABI（{', '.join(r['abis'])}）—— 对 debug 包这是**正确**的："
                        "x86_64 用于跑模拟器，缺了会 INSTALL_FAILED_NO_MATCHING_ABIS。")
        else:
            tips.append(f"含多个 ABI（{', '.join(r['abis'])}）。release 通常只需 arm64-v8a，"
                        "多余架构属可剔除的浪费。")

    for item in r["native_heavy"]:
        n = item["name"]
        low = n.lower()
        label = "原生库"
        for key, lbl in HEAVY_NATIVE_HINTS.items():
            if key in low:
                label = lbl
                break
        tips.append(f"体积敏感原生库：{n}（{human(item['compressed'])}，{label}）"
                    "—— 请确认代码里真的用到了它。")

    if len(r["dex_files"]) > 1:
        if is_debug:
            tips.append(f"有 {len(r['dex_files'])} 个 dex —— 对 debug 包正常"
                        "（不混淆，方法数超限会自动分包）。")
        elif is_release:
            tips.append(f"有 {len(r['dex_files'])} 个 dex，但这是 release 包"
                        "—— R8 可能没生效，检查 isMinifyEnabled。")
        else:
            tips.append(f"有 {len(r['dex_files'])} 个 dex。release 包出现多 dex "
                        "通常意味着 R8 未生效。")
    else:
        tips.append("单 dex —— release 包的健康形态（R8 生效）。")

    if len(r["native_libs"]) and not r["native_heavy"]:
        tips.append(f"有 {len(r['native_libs'])} 个原生库但都很小（各 <0.5MB）"
                    "—— 属正常辅助库，不必处理。")

    if tips:
        p("-- 提示" + "-" * 57)
        for t in tips:
            p(f"  - {t}")
        p("")

    p("-- 下一步" + "-" * 55)
    p("  1. 对占比最大的依赖，去源码里搜是否真的有引用：")
    p("       声明 ≠ 使用 —— 依赖树看不出这件事。")
    p("  2. 无引用即为死重量：注释掉依赖行 + 写明恢复条件即可。")
    p("  3. 剔除后必须重建并真机复验无回归，不能只看编译通过。")
    p("=" * 64)


def main():
    ap = argparse.ArgumentParser(
        description="APK 体积构成审计与陈旧空洞诊断（纯标准库）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n  python apk_report.py app-debug.apk\n"
               "  python apk_report.py app-release.apk --json out.json")
    ap.add_argument("apk", help="APK 文件路径")
    ap.add_argument("--top", type=int, default=12, help="列出最大的 N 个文件（默认 12）")
    ap.add_argument("--json", metavar="PATH", help="同时把结果写成 JSON")
    ap.add_argument("--no-gaps", action="store_true", help="跳过空洞诊断（大包可加速）")
    args = ap.parse_args()

    if not os.path.isfile(args.apk):
        print(f"错误：找不到文件 {args.apk}", file=sys.stderr)
        return 1
    if not zipfile.is_zipfile(args.apk):
        print(f"错误：{args.apk} 不是有效的 zip/APK（AAB 也可以，但 IPA 不行）",
              file=sys.stderr)
        return 1

    try:
        r = analyze(args.apk, top=args.top, do_gaps=not args.no_gaps)
    except zipfile.BadZipFile as e:
        print(f"错误：APK 结构损坏 —— {e}", file=sys.stderr)
        return 1

    print_report(r)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        print(f"JSON 已写入: {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
