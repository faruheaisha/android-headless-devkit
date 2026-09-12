# Changelog

本文件记录本 skill 的所有重要变更。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.2.0] - 2026-09-12

一次真实磁盘清理暴露出的三处知识缺口。
**共同点：都是"照着本 skill 做完之后必然踩到"的问题** ——
skill 让人建 junction、让人把缓存外移，却没写清随之而来的坑。

### Added

- `references/01-environment-setup.md` §5.2 —— **`gradle-home` 满了什么能删、什么不能删**：
  - 逐目录可删性表（`caches/<版本>/`、`build-cache-1`、`daemon`、`native` 可删；
    **`caches/modules-2` 属禁区** —— 它是依赖仓库不是缓存，删了触发全量重新下载，实测 653MB）
  - **判据：区分「可再生」（本地算一遍就有）与「需重新获取」（要联网下载）**
  - 删 `**/build/` 的**代价**：实测增量 2 分钟 → 全量约 8 分钟
    （必须一并告知用户，不能只报"省了多少"）
  - 实测释放量与 `gradle-home` 体积变化（917MB → 654MB）
  - ⚠️ **内容量 ≠ 实际腾出的空间**：实测删 645MB 内容，盘符可用只涨约 290MB
    （期间有其他进程在写盘）—— 分别报两个数
- `references/02-build-workflow.md` §1 新增小节 —— **`find` 穿不过 junction 的必然坑**：
  - 对照表：`ls -la <联接路径>/` ✅ 能穿过；`find <联接路径> -type f` ❌ 返回空
  - 两个由此产生的假象：①误判"目录是空的" ②全盘扫描时同一批文件被算两次（体积翻倍）
  - 判定方法（`Get-Item | Select LinkType, Target`）与实践建议（联接只当构建入口）
- `references/06-pitfall-index.md` 新增 B11–B14 四条，并补全关键词索引
  （新增"磁盘空间 / 缓存清理"、"`find` 联接返回空"、"HTML 原型"三个检索入口）

### Fixed

- **`CHANGELOG.md` 版本段落结构错误**：v1.1.0 的变更内容被并入 `[1.0.0]` 段落下，
  缺 `## [1.1.0]` 标题。已补回独立段落。

### 为什么这三处值得单独一个版本

它们都属"**照做之后的第二步**"：正文教了正确做法，但正确做法的副作用没被覆盖
（建了联接 → 扫描出错；外移了缓存 → 缓存满了不知道怎么清）。
**一份流程规范只教怎么开始、不教怎么维护，用一段时间后就会失效。**

---

## [1.1.0] - 2026-09-12

### Changed

- **重写 `SKILL.md` 的 `description`**：把本项目最独特的能力 ——
  **Agent 能通过 adb 截图后读图，从而自己"看见"界面、独立发现并修掉只有肉眼
  才能发现的 UI 缺陷** —— 提到核心位置；补入第 ⑥ 类触发语境（无头浏览器自验证 HTML）；
  新增触发词 `无头浏览器截图` / `headless chrome screenshot` / `HTML 原型验证` /
  `逐屏截图` / `交互设计验收`。

### Added

- `references/07-html-prototype-harness.md`（**附加环节：用无头浏览器验证自己的 HTML 产出**）：
  - 为什么需要：本项目**第一次**的教训是 Android 界面 5 个缺陷全靠装机截图发现；
    **第二次**的教训更值得警惕 —— 我写的第一版交互原型 HTML，
    犯了我自己在同期 PRD 里刚批评过的同一个错误（内容堆在上半屏、下方大片空白）
  - 完整的 Chrome headless 命令与参数说明
  - **三个实跑踩到的坑**：
    ① 循环截图必须每轮给独立 `--user-data-dir`（否则只有第一张成功、其余静默失败），
       且必须是 Windows 风格路径；
    ② 在 bash 里 `--screenshot` 路径要用正斜杠（`"E:\\out\\$name.png"` 会让
       `$name` 不展开，全部写进同一个字面文件名）；
    ③ 中文路径先复制到 ASCII 路径再截
  - **给产出加深链（`?p=`）** 使逐屏自检与评审分享成为可能
  - 交互原型里两类易犯错误：覆盖层被父级 `display:none` 连带隐藏导致白屏；
    内部动作跨链路切换导致步骤指示器错位
  - 自检清单 + 一条纪律：改了必须**再渲染一次确认**（"我改了"与"改对了"之间隔着一次截图）

---

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

- `validate_skill.py` —— `SKILL.md` 结构校验，18 项断言：
  frontmatter 存在与闭合、必需字段、**`name` 与目录名一致**（技能发现依赖此约定）、
  `description` 含 Use when / Not for / Triggers 三类语境、正文以一级标题开头、
  **正文引用的本地文件真实存在（防断链）**、脚本语法可编译、仓库内无 APK/AAB/dex/so。
  不依赖 pyyaml，手工解析 frontmatter —— 校验脚本自身不该有额外依赖。

- `evals/evals.json` —— 触发与行为断言（11 条 eval / 51 条断言）。

### 已知边界

- `input tap` 是**盲点**（按坐标估算），点击后必须再截图确认；本 skill 不含
  元素定位能力（如需按控件点击建议另接 UI Automator / Espresso）。
- 未覆盖多设备并行、真机（非模拟器）的厂商 ROM 差异、CI 集成（GitHub Actions）。
- Windows 为主要验证环境；Linux/macOS 的差异（路径与编码坑不同）未验证。
