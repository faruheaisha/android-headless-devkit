# android-headless-devkit

**无 Android Studio 的 Android 全流程开发与真机验收 Agent Skill** ——
只用命令行搭出完整工具链，并在无头模拟器上完成「构建 → 安装 → 截图 → 读图验收 → 查崩溃」闭环。

*An Agent Skill for building, running, and **visually verifying** Android apps entirely from
the command line — no Android Studio. Includes SDK setup on Windows, Gradle failure
diagnosis, headless emulator verification with screenshots, dependency version-conflict
resolution, and APK size auditing.*

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
[![PowerShell 5.1+](https://img.shields.io/badge/PowerShell-5.1%2B-black.svg)](https://learn.microsoft.com/powershell/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-black.svg)](https://www.python.org/)
[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-compatible-black.svg)](https://agentskills.io)

遵循 [Agent Skills 开放标准](https://agentskills.io)（`SKILL.md` + 渐进式披露）。

> **关于内容边界**：本仓库只包含**方法论、可执行脚本与实测数值**。
> **不含任何 APK、应用业务代码、密钥或用户数据。**

## 它解决什么

| 痛点 | 本 skill 的做法 |
|---|---|
| 以为没装 Android Studio 就没法干活 | 讲清"决定能否开工的是 JDK + SDK CLI 而非 IDE"；工具链可全装在指定盘、不依赖 IDE |
| 中文路径下 Gradle 说目录不存在 | ASCII **目录联接（junction）** 透明桥接，这是通用解法 |
| 构建偶发 JVM 原生内存崩溃 | 定位到真正瓶颈是**提交内存**而非物理内存；给出实测配置与排查顺序 |
| 改一个错跑一轮，单轮 24 分钟 | `--continue` **一次拿全错误** + `:app:help` 快速配置校验；附实测耗时预算表 |
| 依赖版本冲突看不懂、改不对 | 讲清 **KMP 库会把整条版本线一起拉高**的传导链；给实测版本对应表；**KMP 库要看 `.module` 而非 `.pom`** |
| 代码看着没问题但界面是坏的 | **装机截图 + 读图**验收闭环，含 RTL / 玻璃质感 / 最小触控尺寸等 20+ 项检查清单 |
| 报"内存不足"却找不出原因 | 教你查**提交可用**而不是物理可用；OneDrive 单进程实测提交 14.5GB |
| 包体异常大、找不到原因 | 分类拆解 + **死依赖识别**（"声明 ≠ 使用"）+ **陈旧空洞诊断** |

## 实测成果（本 skill 的来源项目）

在一台 **C 盘只剩 3GB、内存 16GB 但可用常低于 2GB、项目路径含中文、无任何 Android
开发环境** 的机器上，从零搭出工具链并完成下列闭环：

| 结果 | 数据 |
|---|---|
| 工具链 | 全装在单盘、自包含、不依赖 Android Studio |
| 构建 | `BUILD SUCCESSFUL`，0 错误 0 警告 |
| 单元测试 | 16 个用例全通过，耗时 **0.05 秒**（纯 JVM，无需模拟器） |
| 装机验收 | Android 13 模拟器上安装、启动、截图、无崩溃 |
| 裸眼发现并修掉的 UI 问题 | **5 个**（状态栏重叠、玻璃质感消失、卡片暗环、布局留白、返回键过小） |
| 包体 | debug **65.26MB** / release **2.80MB**（剔除死依赖后缩小 7.3 倍） |
| release 构建 | 首次实跑 R8 通过，零 `Missing class` |

## 六阶段工作流

| 阶段 | 做什么 | 对应 reference |
|---|---|---|
| 1 环境搭建 | 装 JDK + SDK CLI + 建 AVD，绕过代理/编码/磁盘三类坑 | [01](references/01-environment-setup.md) |
| 2 构建打通 | 中文路径、内存崩溃、排障方法论、耗时预算 | [02](references/02-build-workflow.md) |
| 3 **装机验收** | 无头模拟器：装→启→截图→**读图**→查崩溃 | [03](references/03-device-verification.md) |
| 4 修错回环 | 按"看得见的问题"改，改完**重新装机再验** | [03](references/03-device-verification.md) |
| 5 依赖收口 | 版本对齐、剔除无用依赖、R8 规则 | [04](references/04-dependency-versions.md) |
| 6 发布核对 | 量包体、找死重量、验 release 构建 | [05](references/05-apk-size-audit.md) |

坑点速查（症状 → 根因 → 解法，40+ 条）：[06-pitfall-index.md](references/06-pitfall-index.md)

## 快速开始

```powershell
# 1) 环境变量（含清空失效代理与体检）
. .\scripts\env.ps1 -DevRoot "E:\AndroidDev"

# 2) 构建（排障时用 --continue 一次拿全错误）
& $env:GRADLE_BIN -p "<项目>" ":app:assembleDebug" --no-daemon

# 3) 装机验收（装→启→截图→查崩溃，一键）
.\scripts\verify_loop.ps1 -Apk "<apk>" -Package "com.example.app" `
    -Activity ".MainActivity" -OutDir "E:\out" -Tap "250,830"

# 4) APK 体积审计（含陈旧空洞诊断）
python .\scripts\apk_report.py "<apk>"

# 5) 脚本自测
python .\self_test.py
```

## 核心判断：决定能否开工的不是 IDE

- Android Studio **免费**（Apache-2.0），但**命令行工具齐备才是关键**
- 本 skill 的作者（Agent）**无法操作 GUI**，但**能通过命令行完成全部工作**
- 并且**能通过 `adb` 截图后读图从而"看见"界面** → 视觉问题可**自行发现并修正**

> 这条能力边界直接改变协作分工：**RTL 渲染、玻璃质感、布局留白这类"必须用眼睛验收"
> 的东西，也可以自己验，不必等用户截图反馈。**

## 两条硬性纪律

1. **不实跑就发现不了的 bug 占多数。** 凡涉及构建配置，必须实跑验证再声称完成。
   本仓库的 `verify_loop.ps1` 自身就是这条纪律的产物 —— 它的两个真 bug
   （函数定义顺序、adb 输出未校验导致的假阳性）全部是实跑才暴露的。
2. **汇报要区分"已验证"与"未验证"。**
   编译通过 ≠ 单测通过 ≠ 装机运行 ≠ 界面验收 ≠ 功能可用，
   五档分别需要不同证据，不能把前三档说成第五档。

## 目录

```
android-headless-devkit/
├── SKILL.md                          入口：工作流、能力边界、硬性经验
├── README.md                         本文件
├── LICENSE                           MIT
├── CHANGELOG.md
├── CONTRIBUTING.md
├── references/
│   ├── 01-environment-setup.md        装 JDK/SDK/AVD，代理·编码·磁盘三类坑
│   ├── 02-build-workflow.md           构建打通、中文路径、内存崩溃、耗时预算
│   ├── 03-device-verification.md   ★  无头模拟器装机验收闭环与 UI 验收清单
│   ├── 04-dependency-versions.md      版本对齐、冲突诊断、R8 规则、许可准入
│   ├── 05-apk-size-audit.md           体积构成、陈旧空洞、死依赖剔除
│   └── 06-pitfall-index.md            坑点速查总表（40+ 条）
├── scripts/
│   ├── env.ps1                       环境变量一键设置 + 体检
│   ├── verify_loop.ps1               装→启→截图→查崩溃 一键闭环（带 adb 超时）
│   └── apk_report.py                 APK 体积构成 + 陈旧空洞诊断
├── self_test.py                      apk_report.py 的自测（23 项断言）
└── evals/evals.json                  触发与行为断言
```

## 不适用

**iOS / IPA**、**Flutter / React Native**、Gradle 之外的构建系统（Bazel / Buck）、
**Play 上架流程与账号资质**、Kotlin 语言语法教学、H5 / 小程序。

本 skill 聚焦 **原生 Android + Gradle + Compose** 这一条线。

## 许可

MIT，见 [LICENSE](LICENSE)。

案例来自真实项目，已做匿名化处理：应用名、包名、业务逻辑与用户数据均不在本仓库内，
仅保留**与框架/工具链相关**的可复用知识。
