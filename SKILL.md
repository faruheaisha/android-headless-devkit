---
name: android-headless-devkit
description: "无 Android Studio 的 Android 全流程开发与真机验收工具包：只用命令行（JDK + Android SDK CLI + Gradle）从零搭出可编译、可安装、可看见的完整链路，并完成「环境与依赖基线 → 构建 → 安装 → 截图读图验收 → 走通功能链路 → 物理真机终验」闭环。关键能力有六：①Agent 能通过 adb 截图后读图，自己『看见』界面、独立发现并修掉只有肉眼才能发现的 UI 缺陷（布局留白、玻璃质感、RTL 渲染、返回键过小等）；②能靠 uiautomator UI 树取真实控件坐标、用 base64 参数注入绕开『adb 打不了中文』，把功能链路也自动跑通并留下可核对证据；③能分清『页面渲染正常』与『功能真的通了』，并识别一次成功到底走的哪条路径（网络/缓存/本地），避免把缓存命中误报成链路已通；④能把环境与依赖沉淀成『换机换人可照做』的基线——环境变量参数化、依赖唯一出处、许可扫描（含随包模型资产的独立许可）、密钥不进包与轮换验证；⑤能做物理真机验证——装机报错三分类（签名冲突/ABI/版本降级）、统一日志前缀与长链路三连证据、调试路由的 release 门控、回归清单、debug/release/benchmark 三类包差异，并坚持『模拟器与真机的结论不可互相外推』；⑥能用无头浏览器对自己的 HTML 产出（交互原型、报告）逐屏渲染截图自检。Use when 需要 ①在 Windows 上从零装 Android 工具链（无 IDE、装到指定盘、绕开中文路径与代理）；②解决 Gradle 构建失败（内存/提交量崩溃、编译错误批量暴露、构建耗时预算）；③做 Android 真机或模拟器验证而不是只交代码——要截图看见界面、要查崩溃日志、要验 RTL/暗色/无障碍、要走通真实业务链路、要做交付前真机终验；④排查依赖与版本冲突（Compose BOM 与 Compose Multiplatform 库互相拉扯、activity 要求更高 compileSdk、R8 Missing class）；⑤做依赖清单/环境基线/许可核查/密钥排查（API key 是否打进 APK、密钥泄露后怎么处置、随包模型许可）；⑥做 APK 体积审计与死依赖剔除；⑦用无头浏览器对自己的 HTML 产出逐屏渲染截图自检；⑧接入云端 API 时排查『界面正常但请求没发出』『模型返回空内容』『状态指示与实际能力不一致』这类只在运行期才暴露的问题。即使只做其中一环（只装 SDK、只截图、只查版本冲突、只量包体、只做依赖许可核查、只渲染 HTML）也应使用本 skill。Not for: iOS/IPA、Flutter/React Native、Gradle 之外的构建系统（Bazel/Buck）、Play 上架流程与账号资质、Kotlin 语言语法教学、H5/小程序。Triggers: 无 Android Studio, 命令行装 Android SDK, sdkmanager, avdmanager, 模拟器无头, adb 截图, exec-out screencap, uiautomator dump, 控件坐标, 真机验证, 真机终验, USB 调试, adb devices unauthorized, 装机验证, INSTALL_FAILED_UPDATE_INCOMPATIBLE, INSTALL_FAILED_NO_MATCHING_ABIS, 签名冲突, 界面验收, 功能链路验收, 端到端验证, 环境变量, 依赖清单, 许可核查, 第三方声明, API key 泄露, 密钥轮换, 随包模型许可, Android 构建失败, gradle OOM, mmap failed, 提交内存, 依赖冲突, Compose BOM, Haze 版本, R8, Missing class, APK 体积, 瘦身, 死依赖, 中文路径 gradle, ANDROID_HOME, WHPX, adb pull 失败, multiinstance.lock, SystemUI ANR, 关动画, android headless, adb screencap, apk size audit, gradle build failed, reasoning_effort, NET_CAPABILITY_VALIDATED, 无头浏览器截图, headless chrome screenshot, HTML 原型验证, 逐屏截图, 交互设计验收, ONNX Runtime, 端侧模型, 模型打包, 随包模型, noCompress, STORED, 分词对拍, 逐 id 对拍, special token, org.json not mocked, not mocked, AVD 挪盘, userdata partition, 模型加载慢, 推理首次慢."
metadata:
  version: "1.4.0"
  last_updated: "2026-09-18"
  status: active
  license: MIT
  task_type: workflow
  requires: "python>=3.10（仅标准库）; PowerShell 5.1+ 或 bash; JDK 17; Android SDK command-line tools; Gradle。Windows 为主要验证环境。"
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
| 启动无头模拟器 | ✅ | `emulator -avd X -no-window`（**必须与整条流程同一任务内**，否则被回收） |
| **看见界面** | ✅ | `adb exec-out screencap -p > x.png` → **我读图** |
| 查崩溃 | ✅ | `adb logcat -d -b crash`，**检索 `FATAL EXCEPTION` 而非应用名**（会误报） |
| **点准界面** | ✅ | `uiautomator dump` 取真实控件坐标（**排除 `EditText`**）→ `input tap` → 再截图确认 |
| 走通功能链路 | ✅ | 给 App 加**仅 debug 生效的直启 + 参数入口**，绕开被系统对话框吞掉的连续点击 |
| 操作 IDE 窗口 | ❌ | GUI 无接口 |

## 六阶段工作流

```
阶段1 环境搭建   → 阶段2 构建打通   → 阶段3 装机验收
                        ↑                    │
                        └──── 阶段4 修错回环 ─┘
                                              │
              阶段6 发布核对 ← 阶段5 依赖收口 ←┘
```

阶段 3 有**两层**，别只做第一层：

```
3a 渲染验收：每页能不能正确画出来（截图读图）
3b 链路验收：功能真的能跑通吗（走完整流程 + 留下可核对的证据）
```

本项目实测：9 屏渲染全部正常时，链路其实**没通**（密钥未配 → 后来配好后又
**被缓存命中**绕过云端）。只做 3a 会得出"功能都好了"的错误结论。

| 阶段 | 做什么 | 产出 | 对应 reference |
|---|---|---|---|
| 1 环境搭建 | 装 JDK + SDK CLI + 建 AVD，绕过代理/编码/磁盘三类坑 | 可用工具链 + `env.ps1` | [01-environment-setup.md](references/01-environment-setup.md) |
| 2 构建打通 | 让 `assembleDebug` 成功，含中文路径与内存两类硬故障 | `BUILD SUCCESSFUL` + APK | [02-build-workflow.md](references/02-build-workflow.md) |
| 3 装机验收 | 无头模拟器上装、启、截图、读图、查崩溃 | 截图 + 崩溃检查结论 | [03-device-verification.md](references/03-device-verification.md) |
| 3b **链路验收** | 不止"页面能渲染"，而是"功能真能跑通"：走完整链路并留下证据 | 链路截图 + 日志证据 | [03](references/03-device-verification.md) §链路验收 |
| 4 修错回环 | 按"看得见的问题"改 UI/逻辑，改完**重新装机再验** | 修复后的截图 | [03](references/03-device-verification.md) |
| 5 环境与依赖收口 | 环境变量参数化、依赖唯一出处、许可扫描、密钥不进包、设备要求 | 基线文档 + 盘点表 | [08-dependency-and-environment-baseline.md](references/08-dependency-and-environment-baseline.md) |
| 5b 依赖版本对齐 | 版本冲突诊断、剔除无用依赖、确认 R8 规则 | 稳定的版本目录 | [04-dependency-versions.md](references/04-dependency-versions.md) |
| 5c **端侧模型集成** | 大模型资产打包（noCompress/首用拷贝/路径加载）、会话参数 A/B、分词逐 id 对拍、release 静态核对 | 实测时延 + 核对清单全绿 | [10-onnx-model-bundling.md](references/10-onnx-model-bundling.md) |
| 6 发布核对 | 量包体、找死重量、验 release 构建 | 实测体积表 | [05-apk-size-audit.md](references/05-apk-size-audit.md) |
| 7 **真机终验** | 物理设备装机、日志驱动验收、回归清单、三类包差异 | 真机结论（**标注不可外推**） | [09-real-device-verification.md](references/09-real-device-verification.md) |

坑点速查（症状 → 根因 → 解法，一张表）：[06-pitfall-index.md](references/06-pitfall-index.md)

端侧推理模型（TTS/OCR/ASR 权重）打进 APK 的完整做法（资产/加载/会话参数/分词对拍/release 静态核对）：[10-onnx-model-bundling.md](references/10-onnx-model-bundling.md)

**附**：产出的 HTML（交互原型、报告）同样要渲染验证 ——
[07-html-prototype-harness.md](references/07-html-prototype-harness.md)
本项目的教训是：**我写的第一版交互原型，犯了我自己在同期 PRD 里刚批评过的同一个错误**
（内容堆在上半屏、下方大片空白）。写的时候看不出来，渲染出来一眼就看出来。

**两类设备各有一篇**，别只看一篇：

| | 用哪篇 | 适合 |
|---|---|---|
| 无头模拟器 | [03](references/03-device-verification.md) | 每轮改动的自动化回归（可重复、可脚本化） |
| 物理真机 | [09](references/09-real-device-verification.md) | 交付前终验（真实硬件、真实网络、手感） |

> ★ **两类的结论不能互相外推**。模拟器是纯软件执行，时延天然慢；
> 而厂商 ROM 的权限与后台策略只在真机出现。报告必须写清结论来自哪类设备。

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

## 五条硬性经验（最重要，先看这些）

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

5. **"页面能渲染" ≠ "功能能跑通"，而且"功能成功"有多种路径。**
   两件事必须分开验：前者验 UI，后者验链路。
   本项目实测：9 屏全部渲染正常的同时，第一次"翻译成功"其实是**命中了缓存层** ——
   原文折叠条写着"从历史保存的"，请求**从未到达云端**。若不分辨路径，
   就会把"降级链命中缓存"当成"云端链路已通"，把一个未验证的结论写进交付报告。

   判据要按路径分开：
   ```
   走了网络 → 客户端有网络层日志（如 token 用量）       ← 真正的链路验证
   命中缓存 → 界面有"从历史保存的"标记，无网络日志      ← 只验证了降级链
   真失败   → 有错误日志 + 界面给出可理解的提示          ← 验证错误处理
   ```
   同理，**持久化数据会让第二次跑与第一次不同** —— 验收脚本应 `pm clear` 回到零状态；
   而"要跨过缓存"的测试必须**换用全新输入**，不能复用同一份数据。

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
│   ├── 03-device-verification.md   ★  UI 渲染验收 + ★功能链路验收 + 状态指示一致性
│   ├── 04-dependency-versions.md      版本对齐、冲突诊断、R8 规则
│   ├── 05-apk-size-audit.md           体积构成、陈旧空洞、死依赖剔除
│   ├── 06-pitfall-index.md            坑点速查总表（症状→根因→解法）
│   ├── 07-html-prototype-harness.md   用无头浏览器逐屏验证自己的 HTML 产出
│   ├── 08-dependency-and-environment-baseline.md  ★ 环境/依赖/许可/密钥基线（换机可照做）
│   └── 09-real-device-verification.md ★ 物理真机：装机·日志驱动验收·回归清单·三类包差异
├── scripts/
│   ├── env.ps1                       环境变量一键设置（含清空失效代理）
│   ├── verify_loop.ps1               装→启→截图→查崩溃 一键闭环
│   ├── apk_report.py                 APK 体积构成 + 陈旧空洞诊断
│   └── privacy_audit.py              发布前隐私审计（可挂 CI / pre-commit）
├── self_test.py                      apk_report.py 的自测（23 项断言）
├── validate_skill.py                 SKILL.md 结构校验（18 项断言）
└── evals/evals.json                  触发与行为断言（改 description 后必过）
```

## 不适用（越界前先向用户说明）

iOS/IPA、Flutter 与 React Native、Gradle 之外的构建系统、Play 上架资质与账号流程、
Kotlin 语法教学、H5 与小程序。本 skill 聚焦 **原生 Android + Gradle + Compose** 这一条线。
