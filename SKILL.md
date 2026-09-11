---
name: android-headless-devkit
description: "无 Android Studio 的 Android 全流程开发与真机验收工具包：只用命令行（JDK + Android SDK CLI + Gradle）从零搭出可编译、可安装、可看见的完整链路，并在无头模拟器上完成「构建 → 安装 → 截图 → 读图验收 → 查崩溃」闭环。关键能力是 Agent 能通过 adb 截图后读图，从而自己『看见』界面、独立发现并修掉只有肉眼才能发现的 UI 缺陷（布局留白、玻璃质感、RTL 渲染、返回键过小等），不必等用户截图反馈。Use when 需要 ①在 Windows 上从零装 Android 工具链（无 IDE、装到指定盘、绕开中文路径与代理）；②解决 Gradle 构建失败（内存/提交量崩溃、编译错误批量暴露、构建耗时预算）；③做 Android 真机或模拟器验证而不是只交代码——要截图看见界面、要查崩溃日志、要验 RTL/暗色/无障碍；④排查依赖与版本冲突（Compose BOM 与 Compose Multiplatform 库互相拉扯、activity 要求更高 compileSdk、R8 Missing class）；⑤做 APK 体积审计与死依赖剔除；⑥用无头浏览器对自己的 HTML 产出（交互原型、报告）逐屏渲染截图自检。即使只做其中一环（只装 SDK、只截图、只查版本冲突、只量包体、只渲染 HTML）也应使用本 skill。Not for: iOS/IPA、Flutter/React Native、Gradle 之外的构建系统（Bazel/Buck）、Play 上架流程与账号资质、Kotlin 语言语法教学、H5/小程序。Triggers: 无 Android Studio, 命令行装 Android SDK, sdkmanager, avdmanager, 模拟器无头, adb 截图, 真机验证, 装机验证, 界面验收, Android 构建失败, gradle OOM, mmap failed, 提交内存, 依赖冲突, Compose BOM, Haze 版本, R8, Missing class, APK 体积, 瘦身, 死依赖, 中文路径 gradle, ANDROID_HOME, WHPX, adb pull 失败, android headless, adb screencap, apk size audit, gradle build failed, 无头浏览器截图, headless chrome screenshot, HTML 原型验证, 逐屏截图, 交互设计验收."
metadata:
  version: "1.0.0"
  last_updated: "2026-09-12"
  status: active
  license: MIT
  task_type: workflow
  requires: "python>=3.10（仅标准库）; PowerShell 5.1+; JDK 17; Android SDK command-line tools; Gradle。Windows 为主要验证环境。"
---

# Android 无 IDE 开发与真机验收工具包

只用命令行把 Android 项目做出来**并且看见它真的跑起来** —— 不需要 Android Studio。

本 skill 在一台 **C 盘只剩 3GB、内存 16GB 但可用常低于 2GB、路径含中文、无任何
Android 开发环境**的机器上，从零搭出完整工具链，并跑通了
「构建 → 装进模拟器 → 截图 → 用眼睛验收 → 发现并修掉 5 个只有看得见才能发现的
UI 问题 → 审计包体并剔掉 17.63MB 死重量」的全过程。
文中所有版本号、报错原文、数值、耗时均为**实测值**，不是估计。

## 核心判断：决定能否开工的不是 IDE

很多人以为"让 AI 干 Android 活得先装 Android Studio"。实际：

- Android Studio 本身**免费**（Apache-2.0，无订阅无阉割，个人与商业项目均可）
- 但真正决定"能不能编译、能不能装、能不能看"的，是机器上**有没有 JDK + Android SDK 命令行工具**
- 我**无法操作 GUI**（点不了 IDE 窗口里的按钮），但**完全能通过命令行干活**，并且
  **能通过 `adb` 截图后读 PNG 从而"看见"界面**

> 结论：**没有 IDE 不是障碍。** 有 JDK + SDK CLI + `adb` 就够了。
> 这条决定了协作方式 —— 视觉问题我自己能发现并修，不必等用户截图。

## 能力边界（先讲清，避免承诺过头）

| 能力 | 能否 | 方式 |
|---|---|---|
| 编译工程 / 跑单测 | ✅ | `gradle :app:assembleDebug` / `:core:domain:test` |
| 读编译错误并修复 | ✅ | 读构建输出（用 `--continue` 一次拿全） |
| 启动无头模拟器 | ✅ | `emulator -avd X -no-window` |
| **看见界面** | ✅ | `adb screencap` → 拉回 PNG → **我读图** |
| 查崩溃 | ✅ | `adb logcat -d -b crash` |
| 点击界面 | ⚠️ 有限 | `adb shell input tap x y` **按坐标盲点**，不如人眼准 |
| 操作 IDE 窗口 | ❌ | GUI 无接口 |

## 六阶段工作流

```
阶段1 环境搭建   → 阶段2 构建打通   → 阶段3 装机验收
                        ↑                    │
                        └──── 阶段4 修错回环 ─┘
                                              │
              阶段6 发布核对 ← 阶段5 依赖收口 ←┘
```

| 阶段 | 做什么 | 产出 | 对应 reference |
|---|---|---|---|
| 1 环境搭建 | 装 JDK + SDK CLI + 建 AVD，绕过代理/编码/磁盘三类坑 | 可用工具链 + `env.ps1` | [01-environment-setup.md](references/01-environment-setup.md) |
| 2 构建打通 | 让 `assembleDebug` 成功，含中文路径与内存两类硬故障 | `BUILD SUCCESSFUL` + APK | [02-build-workflow.md](references/02-build-workflow.md) |
| 3 装机验收 | 无头模拟器上装、启、截图、读图、查崩溃 | 截图 + 崩溃检查结论 | [03-device-verification.md](references/03-device-verification.md) |
| 4 修错回环 | 按"看得见的问题"改 UI/逻辑，改完**重新装机再验** | 修复后的截图 | [03](references/03-device-verification.md) |
| 5 依赖收口 | 版本对齐、剔除无用依赖、确认 R8 规则 | 稳定的版本目录 | [04-dependency-versions.md](references/04-dependency-versions.md) |
| 6 发布核对 | 量包体、找死重量、验 release 构建 | 实测体积表 | [05-apk-size-audit.md](references/05-apk-size-audit.md) |

坑点速查（症状 → 根因 → 解法，一张表）：[06-pitfall-index.md](references/06-pitfall-index.md)

**附**：产出的 HTML（交互原型、报告）同样要渲染验证 ——
[07-html-prototype-harness.md](references/07-html-prototype-harness.md)
本项目的教训是：**我写的第一版交互原型，犯了我自己在同期 PRD 里刚批评过的同一个错误**
（内容堆在上半屏、下方大片空白）。写的时候看不出来，渲染出来一眼就看出来。

## 快速开始

```powershell
# 1) 环境变量（每次新开 shell 都要设；含清空失效代理）
. scripts\env.ps1 -Jdk "<JDK17路径>" -Sdk "<ANDROID_HOME>" -GradleHome "<缓存目录>"

# 2) 构建
& "$env:GRADLE_BIN" -p "<项目路径或ASCII联接>" ":app:assembleDebug" --no-daemon
#    排障时用 --continue 一次暴露全部错误：
& "$env:GRADLE_BIN" -p "<项目>" ":app:assembleDebug" --continue

# 3) 装机验收（装→启→截图→查崩溃，一键）
.\scripts\verify_loop.ps1 -Apk "<apk>" -Package "com.example.app" -Activity ".MainActivity"

# 4) 包体审计（含"陈旧空洞"诊断）
python scripts\apk_report.py "<apk>"
```

## 四条硬性经验（最重要，先看这些）

1. **不实跑就发现不了的 bug 占多数。**
   本项目里约定插件解析、可空类型、缺依赖、Haze API 版本不兼容、Manifest 引用不存在的
   图标资源 —— 全部是"写完看起来没问题、实跑一次集中暴露"的。**凡涉及构建配置，
   必须实跑验证再声称完成。**

2. **包体读数可能是假的。**
   debug 包显示 103.55MB，拆开只有 65MB —— 有一段 37.97MB 的**陈旧空洞**。
   量体积前先核对"文件大小 vs 条目合计"，差值大于 ~1MB 就要查。

3. **"声明了依赖" ≠ "用到了依赖"。**
   依赖树看不出这件事。本次最大一笔收益就是发现一个 **17.63MB 的原生库占了发布包 82%，
   而全工程零处代码引用它**。剔掉后发布包 20.54MB → 2.80MB。

4. **版本冲突的根源常是 KMP 库把整条版本线一起拉高。**
   Haze 是 Compose Multiplatform 库，它的 CMP 版本会连带抬高 androidx compose → activity
   → 继而要求更高的 compileSdk/AGP。选版本要**顺着这条链一起看**，不能只看单个库的版本号。

## 保守优先的两条取舍原则

这套流程在"该保守的地方保守、该激进的地方激进"上有一条明确界线：

- **可能返工的选型 → 保守**（玻璃库只用稳定版单库起步、缓存只做精确匹配、
  图像修复先做采样填充而不是上模型）
- **决定体验的核心 → 激进**（翻译质量、原位渲染效果、界面观感）

借这条原则判断"锁版本还是升工具链"：**不为迁就一个传递依赖去升级 AGP + Gradle +
compileSdk 整条链**，而是把它们锁在能用的低版本上（详见
[04-dependency-versions.md](references/04-dependency-versions.md)）。

## 目录

```
android-headless-devkit/
├── SKILL.md                          入口：工作流、能力边界、硬性经验
├── README.md                         仓库门面与快速上手
├── references/
│   ├── 01-environment-setup.md        装 JDK/SDK/AVD，代理·编码·磁盘三类坑
│   ├── 02-build-workflow.md           构建打通、中文路径、内存崩溃、耗时预算
│   ├── 03-device-verification.md   ★  无头模拟器装机验收闭环与 UI 验收清单
│   ├── 04-dependency-versions.md      版本对齐、冲突诊断、R8 规则、排除清单
│   ├── 05-apk-size-audit.md           体积构成、陈旧空洞、死依赖剔除
│   ├── 06-pitfall-index.md            坑点速查总表（症状→根因→解法）
│   └── 07-html-prototype-harness.md   用无头浏览器逐屏验证自己的 HTML 产出
├── scripts/
│   ├── env.ps1                       环境变量一键设置（含清空失效代理）
│   ├── verify_loop.ps1               装→启→截图→查崩溃 一键闭环
│   └── apk_report.py                 APK 体积构成 + 陈旧空洞诊断
├── self_test.py                      apk_report.py 的自测（23 项断言）
├── validate_skill.py                 SKILL.md 结构校验（18 项断言）
└── evals/evals.json                  触发与行为断言（改 description 后必过）
```

## 不适用（越界前先向用户说明）

iOS/IPA、Flutter 与 React Native、Gradle 之外的构建系统、Play 上架资质与账号流程、
Kotlin 语法教学、H5 与小程序。本 skill 聚焦 **原生 Android + Gradle + Compose** 这一条线。
