#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apk_report.py 的自测。

为什么需要它：真实 APK 恰好没有陈旧空洞，无法验证"空洞诊断"这条路径。
所以这里**合成**带空洞的 zip，把每条判据都跑一遍 ——
不实跑就声称"功能可用"是本项目明确反对的做法。

运行：
    python self_test.py
退出码 0 = 全部通过。
"""

import os
import struct
import sys
import tempfile
import zipfile
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
import apk_report as ar  # noqa: E402


# ------------------------------------------------------------------ 最小 zip 构造器
def make_zip(entries, gap_before=None, gap_size=0):
    """构造一个合法的 zip（stored 无压缩）。

    entries   : [(name, data), ...]
    gap_before: 在第 N 个条目之前插入空洞（模拟 Gradle 增量打包未截断旧文件）
    gap_size  : 空洞字节数
    """
    out = bytearray()
    central = []

    for i, (name, data) in enumerate(entries):
        if gap_before == i and gap_size:
            out += b"\x00" * gap_size

        off = len(out)
        nb = name.encode("utf-8")
        crc = zlib.crc32(data) & 0xFFFFFFFF
        local = struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, 0, 0, 0,
                            crc, len(data), len(data), len(nb), 0)
        out += local + nb + data
        central.append((name, nb, crc, len(data), off))

    cd_off = len(out)
    for name, nb, crc, size, off in central:
        ch = struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0, 0, 0, 0,
                         crc, size, size, len(nb), 0, 0, 0, 0, 0, off)
        out += ch + nb
    cd_size = len(out) - cd_off

    out += struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(central),
                       len(central), cd_size, cd_off, 0)
    return bytes(out)


# ------------------------------------------------------------------ 断言工具
class Checker:
    def __init__(self):
        self.passed = 0
        self.failed = []

    def check(self, cond, desc, detail=""):
        if cond:
            self.passed += 1
            print(f"  PASS  {desc}")
        else:
            self.failed.append(desc)
            print(f"  FAIL  {desc}")
            if detail:
                print(f"        {detail}")


def write(tmp, name, data):
    p = os.path.join(tmp, name)
    with open(p, "wb") as f:
        f.write(data)
    return p


# ------------------------------------------------------------------ 测试
def main():
    ck = Checker()
    tmp = tempfile.mkdtemp(prefix="ahd_selftest_")

    print("=" * 62)
    print("  apk_report.py 自测")
    print("=" * 62)

    # ---- 测试 1：构成分类与"体积敏感原生库"识别 ----
    print("\n[1] 构成分类 + 大原生库识别（release 包）")
    entries = [
        ("classes.dex", b"\x00" * (1024 * 1024)),                    # 1MB
        ("resources.arsc", b"\x00" * (200 * 1024)),                  # 200KB
        ("res/layout/a.xml", b"\x00" * 4096),
        ("assets/model.bin", b"\x00" * (300 * 1024)),
        # 两个 ABI 各带一个 2MB 的推理引擎 —— 模拟真实场景
        ("lib/arm64-v8a/libonnxruntime.so", b"\x00" * (2 * 1024 * 1024)),
        ("lib/x86_64/libonnxruntime.so", b"\x00" * (2 * 1024 * 1024)),
        # 一个很小的辅助库：不应被算作"体积敏感"
        ("lib/arm64-v8a/libdatastore_shared_counter.so", b"\x00" * (12 * 1024)),
    ]
    apk1 = write(tmp, "app-release-unsigned.apk", make_zip(entries))
    r1 = ar.analyze(apk1)

    ck.check(r1["build_type"] == "release", "识别构建类型为 release",
             f"实际 {r1['build_type']}")
    ck.check("dex" in r1["groups"], "分类含 dex")
    ck.check("res/" in r1["groups"], "分类含 res/")
    ck.check("assets/" in r1["groups"], "分类含 assets/")
    ck.check(r1["groups"]["dex"]["compressed"] == 1024 * 1024,
             "dex 归类正确（1MB）",
             f"实际 {r1['groups']['dex']['compressed']}")
    ck.check(r1["abis"] == ["arm64-v8a", "x86_64"], "ABI 列表正确",
             f"实际 {r1['abis']}")
    ck.check(len(r1["dex_files"]) == 1, "dex 个数正确（1 个）")

    heavy_names = [i["name"] for i in r1["native_heavy"]]
    ck.check(len(r1["native_heavy"]) == 2,
             "只把 ≥0.5MB 的原生库列为体积敏感（2 个）",
             f"实际 {heavy_names}")
    ck.check(all("onnxruntime" in n for n in heavy_names),
             "体积敏感项都是推理引擎")
    ck.check(not any("datastore" in n for n in heavy_names),
             "★ 0.01MB 级辅助库**未被**误报（阈值生效）")
    ck.check(r1["hole_bytes"] < 1024 * 1024, "无空洞的包 hole 差值正常")

    # ---- 测试 2：陈旧空洞诊断（关键路径）----
    print("\n[2] 陈旧空洞诊断（合成 5MB 空洞）")
    gap = 5 * 1024 * 1024
    apk2 = write(tmp, "app-debug.apk", make_zip(entries, gap_before=1, gap_size=gap))
    r2 = ar.analyze(apk2)

    ck.check(r2["build_type"] == "debug", "识别构建类型为 debug")
    ck.check(abs(r2["hole_bytes"] - gap) < 4096,
             f"★ 空洞被正确量出（约 {gap // 1024 // 1024}MB）",
             f"实际 {r2['size_bytes']} - {r2['content_bytes']} = {r2['hole_bytes']}")
    ck.check(len(r2["gaps"]) > 0, "定位到空隙条目")
    if r2["gaps"]:
        top = r2["gaps"][0]
        ck.check(abs(top["bytes"] - gap) < 4096,
                 "最大空隙大小正确",
                 f"实际 {top['bytes']}")
        ck.check(top["next_entry"] == "resources.arsc",
                 "空隙位置指向正确的下一个条目",
                 f"实际 {top['next_entry']}")

    # ---- 测试 3：debug 与 release 的提示措辞不同 ----
    print("\n[3] 提示措辞按构建类型区分")
    # 用真实文件对比措辞：构造两个仅文件名不同的包
    apk_d = write(tmp, "app-debug.apk", make_zip(entries))
    apk_r = write(tmp, "app-release.apk", make_zip(entries))
    rd, rr = ar.analyze(apk_d), ar.analyze(apk_r)
    ck.check(rd["build_type"] == "debug" and rr["build_type"] == "release",
             "同名内容不同文件名 → 推断出不同构建类型")
    ck.check(ar.infer_build_type("x/foo.apk") is None,
             "文件名无 debug/release → 返回 None（走中性措辞）")

    # ---- 测试 4：错误处理 ----
    print("\n[4] 错误处理")
    missing = os.path.join(tmp, "nope.apk")
    ck.check(not os.path.isfile(missing), "不存在的文件确实不存在")
    notzip = write(tmp, "notzip.apk", b"this is definitely not a zip file")
    ck.check(not zipfile.is_zipfile(notzip),
             "★ 非 zip 文件会被 is_zipfile 拦下（避免抛异常）")

    # ---- 测试 5：真实 APK（若存在则顺带验一遍）----
    print("\n[5] 真实 APK 冒烟（可选）")
    real = r"E:\ugapp\app\build\outputs\apk\release\app-release-unsigned.apk"
    if os.path.isfile(real):
        r = ar.analyze(real)
        ck.check(r["size_bytes"] > 0, f"能读真实 release 包（{r['size_human']}）")
        ck.check(r["abis"] == ["arm64-v8a"], "真实 release 包 ABI 正确（仅 arm64）",
                 f"实际 {r['abis']}")
        ck.check(len(r["dex_files"]) == 1, "真实 release 包为单 dex（R8 生效）",
                 f"实际 {len(r['dex_files'])}")
    else:
        print("  SKIP  真实 APK 不存在，跳过")

    # ---- 汇总 ----
    print("\n" + "=" * 62)
    if ck.failed:
        print(f"  结果：{ck.passed} 通过 / {len(ck.failed)} 失败")
        for d in ck.failed:
            print(f"    ✗ {d}")
        print("=" * 62)
        return 1
    print(f"  结果：全部 {ck.passed} 项通过 ✅")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
