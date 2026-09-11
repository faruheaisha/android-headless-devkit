# Changelog

本文件记录本 skill 的所有重要变更。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-09-12

首个版本。内容来自一个真实的 Android 项目全流程实战：
在 C 盘只剩 3GB、物理内存 16GB 但可用常低于 2GB、项目路径含中文、且**没有任何
Android 开发环境**的机器上，从零搭出工具链，跑通构建 → 装机 → 截图验收闭环，
并完成包体审计与 release 构建验证。

### Added

- `SKILL.md` —— 入口：核心判断（决定能否开工的是 JDK+SDK CLI 而非 IDE）、
  能力边界表（含"能通过 adb 截图读图从而看见界面"）、六阶段工作流、
  四条硬性经验、保守优先取舍原则。

- `references/01-environment-setup.md` —— 环境搭建：
  - 命令行工具清单与"两条等价安装路径"（装 IDE / 只装 CLI）
  - JDK 下载源的实测对比（Adoptium/GitHub 502 → **华为云镜像 610KB/s**）
  - **代理三坑**：命令行工具读代理而 Java 程序读不到；一次性会话代理失效后
    必须主动清空；`Invoke-WebRequest` 的 SSL 信任问题（一律用 `curl.exe`）
  - **提交内存**才是真正瓶颈（OneDrive 单进程实测提交 14.5GB，
    退出后提交可用 0.84GB → 7.26GB）
  - 无 TTY 下接受 SDK 许可的解法（**许可哈希文件，含实测哈希值**）
  - PowerShell `-Encoding UTF8` 的 BOM 陷阱与无 BOM 写法
  - WHPX 加速判断（`accel: 0` 表示就绪，Intel 11 代后不用 HAXM）
  - AVD 实测参数表

- `references/02-build-workflow.md` —— 构建打通：
  - ★ **中文路径的目录联接（junction）解法**（通用）
  - 实测内存参数配置与"用户级/项目级 `gradle.properties` 必须一致"的教训
  - ★ **排障方法论**：`--continue` 一次拿全错误、`:app:help` 快速配置校验、
    报错特征 → 归属分类表
  - **实测耗时预算表**（配置校验 2.5 分钟 / 增量打包 2 分钟 / 全量 7分42秒 /
    首次含排障 24 分钟 / release 10分35秒）
  - 拆分 Compose 约定插件使全量构建 24 分钟 → 8.5 分钟的优化
  - 增量打包的陈旧 APK 陷阱

- `references/03-device-verification.md` —— **真机验收（核心）**：
  - 为什么必须做：**5 个 UI 问题全部是装机截图后才发现的**，附逐个说明
  - 无头模拟器启动参数（`-gpu swiftshader_indirect` 是无头出图的前提）
  - 轮询 `sys.boot_completed` 而非固定 sleep
  - 装机 → 启动 → 截图 → 读图全流程；`adb pull` 目标路径必须 ASCII
  - 崩溃与进程存活检查；装机失败的 ABI 排查
  - ★ **UI 验收清单**：通用项 + **RTL 专项**（连写无方框、返回箭头方向、
    高光阴影不镜像等）+ 布局顺序敏感项
  - 模拟器优雅关闭 vs 强杀（强杀留 2GB `ram.img` 残留）
  - "验证到什么程度"五档区分表

- `references/04-dependency-versions.md` —— 依赖与版本：
  - ★ 核心认知：**KMP 库会把整条版本线一起拉高**（含完整传导链与实测对应表）
  - Compose BOM → compose-ui 映射表（Google Maven 实测）
  - 三步诊断方法论；**KMP 库要看 `.module` 而不是 `.pom`**
  - 保守优先：锁低版本而非升级整条工具链；定位根因后要删掉误诊期的临时修补
  - 约定插件的两个真 bug（`Project.apply` 解析、版本目录访问器不可用）
  - R8 / ProGuard 规则清单与验证方法
  - 依赖许可准入清单（含 ML Kit / LaMa / View 体系模糊库 / GPL 系的排除理由）
  - "声明 ≠ 使用"的检查方法

- `references/05-apk-size-audit.md` —— 体积审计：
  - 实测体积表（debug 65.26MB / release 2.80MB，R8 使 dex 64.32MB → 2.30MB）
  - 构成拆解判读要点
  - ★ **死依赖剔除实录**（17.63MB 原生库占发布包 82% 而零代码引用；
    处置方式为"注释 + 写明恢复条件"）
  - ★ **陈旧空洞诊断**（37.97MB 空洞导致体积读数虚高；诊断代码与解法）
  - ABI 精简、dex 与 R8 核对

- `references/06-pitfall-index.md` —— 坑点速查总表，
  按 A 环境 / B 构建 / C 装机 / D 依赖 / E 体积 / F 验证纪律分六组共 40+ 条，
  每条为「症状 → 根因 → 解法」+ 关键词索引。

- `scripts/env.ps1` —— 环境变量一键设置（含清空失效代理）+ 体检输出
  （JDK / adb / gradle / AVD / **提交内存**）。

- `scripts/verify_loop.ps1` —— 装→启→截图→查崩溃一键闭环。
  内置两项由实跑失败倒逼出的健壮性设计：
  - **所有 adb 调用带超时**（实测设备消失时 adb 会无限期挂起，脚本曾卡 12 分钟）
  - **adb 输出必须校验格式**（实测 adb 报错文本曾漏进 PID 变量，
    导致设备已消失却报"进程存活 OK"）
  截图先经 ASCII 暂存目录再复制到目标目录，绕开 `adb pull` 的中文路径限制。

- `scripts/apk_report.py` —— APK 体积构成 + 陈旧空洞诊断，**纯 Python 标准库**。
  含"体积敏感原生库"识别（带 0.5MB 阈值，避免误报小辅助库）与按构建类型的
  措辞区分（debug 多 ABI/多 dex 属正常，release 则异常）。

- `self_test.py` —— 23 项断言。**合成带空洞的 zip** 来验证空洞诊断路径
  （真实 APK 恰好没有空洞，无法覆盖该路径），并含真实 APK 冒烟测试。

- `evals/evals.json` —— 触发与行为断言。

### 已知边界

- `input tap` 是**盲点**（按坐标估算），点击后必须再截图确认；本 skill 不含
  元素定位能力（如需按控件点击建议另接 UI Automator / Espresso）。
- 未覆盖多设备并行、真机（非模拟器）的厂商 ROM 差异、CI 集成（GitHub Actions）。
- Windows 为主要验证环境；Linux/macOS 的差异（路径与编码坑不同）未验证。
