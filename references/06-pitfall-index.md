# 坑点速查总表

按"**症状 → 根因 → 解法**"组织。遇到报错先在这里搜关键词，
再跳到对应 reference 看细节。所有条目均为**实测踩到过**的，不是理论推演。

---

## A. 环境 / 安装

| # | 症状 | 根因 | 解法 |
|---|---|---|---|
| A1 | Adoptium / GitHub Releases 下载 JDK 返回 **502** | 代理拦了这两个源 | 换**华为云镜像** `mirrors.huaweicloud.com/openjdk/`（610KB/s） |
| A2 | `curl` 能下载，但 `sdkmanager` / Gradle **连不上源** | **Java 程序读不到 shell 的 `http_proxy`** | 显式传 `-Dhttp.proxyHost=...`（JDK 侧）/ `systemProp.http.proxyHost`（Gradle 侧） |
| A3 | Gradle **无法下载任何依赖**，报错不指向代理 | 残留的**一次性会话代理**已失效 | 构建前清空：`$env:HTTP_PROXY=""; $env:HTTPS_PROXY=""; $env:http_proxy=""; $env:https_proxy=""` |
| A4 | `Invoke-WebRequest` 对 `dl.google.com` 报 **SSL 信任错误** | 该站对 IWR 的 TLS 握手异常 | **一律用 `curl.exe`** 下载 |
| A5 | `sdkmanager --licenses` **卡住不动** | 无 TTY，读不到交互输入 | 直接**写许可哈希文件**到 `sdk/licenses/`（哈希值见 [01](01-environment-setup.md) §6.1） |
| A6 | PowerShell 管道给 `.bat` 的 stdin 无效 | `.bat` 包装层问题 | 绕过 `.bat`，直接 `java -classpath ...\sdkmanager-classpath.jar com.android.sdklib.tool.sdkmanager.SdkManagerCli` |
| A7 | `javac` 编译报首字符非法 / 许可哈希校验失败 | `-Encoding UTF8` **写了 BOM** | 一律用 `[System.IO.File]::WriteAllText($p,$c,(New-Object System.Text.UTF8Encoding($false)))` |
| A8 | 构建因空间不足失败 | Gradle 默认缓存在 C 盘 `.gradle`（数 GB） | 设 `GRADLE_USER_HOME` 到空间充足的盘 |
| A9 | `emulator-check accel` 找不到 HAXM | Intel 11 代后已废弃 HAXM | 用 **WHPX**；`accel: 0` 即表示就绪 |
| A10 | 找不到可用系统镜像 | 只装了 platforms 没装 system-image | `sdkmanager "system-images;android-33;google_apis;x86_64"` |
| A11 | `cmd /c` / `[Diagnostics.Process]::Start` 被拦截 | 受限执行策略 | 用原生 PowerShell 调 `.bat`，或直接调 `java` |

---

## B. 构建

| # | 症状 | 根因 | 解法 |
|---|---|---|---|
| B1 | `The specified project directory '<中文路径>' does not exist`（路径明明存在） | `gradle.bat` 经 `cmd.exe` 传参，**非 ASCII 路径被编码破坏** | 建 **ASCII 目录联接**：`New-Item -ItemType Junction -Path E:\proj -Target "<中文路径>"`，构建用 `-p E:\proj` |
| B2 | `Native memory allocation (mmap) failed to map ... for G1 virtual space`，守护进程崩溃 | **提交内存**（commit charge）耗尽，非物理内存不足 | 查 `FreeVirtualMemory`；**退出 OneDrive 等云盘客户端**；压内存参数；迁页面文件 |
| B3 | `Internal compiler error`（Kotlin 编译） | 内存吃紧（Gradle 堆 4GB + 另起 Kotlin 守护进程） | 堆降到 2GB + `kotlin.compiler.execution.strategy=in-process` |
| B4 | 项目级 `-Xmx` 设了但**没生效**，仍按更大值分配 | **用户级 `gradle.properties` 值不同**并最终生效 | 两处设成**相同值** |
| B5 | 构建缓存写入`.part` **拒绝访问**，连带任务失败 | 杀软锁临时文件 | `org.gradle.caching=false`（排障期先关） |
| B6 | `Failed to instrument class ... CustomPropertiesFileValueSource$Parameters` | **配置缓存与 KGP 冲突** | `org.gradle.configuration-cache=false` |
| B7 | 一轮构建 **24 分钟**，改一个错跑一轮 | 未批量暴露错误 | 用 `--continue` **一次拿全错误**；配置问题用 `:app:help` 快速验（约 2.5 分钟） |
| B8 | 改了依赖但 APK 体积**没变化** | Gradle 增量打包未截断旧文件 → **陈旧空洞** | 删 APK 后只重跑打包（约 2 分钟）→ 见 [05](05-apk-size-audit.md) §4 |
| B9 | 全量构建很慢（含大量纯逻辑模块） | **Compose 编译器插件被套在所有模块上** | 拆出独立的 compose 库插件，只给含界面的模块用（24 分钟 → 8.5 分钟） |
| B10 | 构建日志刷屏看不清 | 未落文件 | `2>&1 \| Out-File -Encoding UTF8`，再 `Select-String` 筛 `BUILD SUCCESSFUL\|BUILD FAILED\|^e: ` 等；**用完删掉** |

---

## C. 装机 / 设备

| # | 症状 | 根因 | 解法 |
|---|---|---|---|
| C1 | `INSTALL_FAILED_NO_MATCHING_ABIS` | APK 缺设备架构的原生库（**模拟器 x86_64 / 真机 arm64**） | debug 加 `x86_64`，release 只留 `arm64-v8a` |
| C2 | `adb pull` 失败 | **目标路径含中文** | 目标路径必须 **ASCII**；拉回后再复制到项目目录 |
| C3 | 截图拿到**黑屏 / 白屏** | 无头模式下硬件 GPU 不出图 | 用 `-gpu swiftshader_indirect`（**软件渲染**） |
| C4 | 模拟器"启动完了"但 adb 命令报设备未就绪 | 用固定 `sleep` 猜启动时间 | 轮询 `getprop sys.boot_completed` 直到 `1`（实测约 24 秒） |
| C5 | 截图看到的是**旧版本界面** | 没杀旧进程 | `am force-stop` 后再 `am start` |
| C6 | 截图"成功"但实际是上次的旧图 | `adb pull` 失败后旧文件仍在 | 截图前先 `Remove-Item -LiteralPath $dst -Force`，再判断 `Test-Path` |
| C7 | E 盘/磁盘莫名少了几 GB | **强杀模拟器留下 `ram.img`（约 2GB 快照残留）** | 优先 `adb emu kill` **优雅关闭**；残留确认进程已停后删除（下次启动自动重建） |
| C8 | 不知道点哪里 | `input tap` 是**盲点**，坐标靠估算 | 先截图**从图上量坐标** → 点 → **再截图确认** |
| C9 | 装机失败 | — | 三步分开确认：`install` 成功 → 进程存在（`pidof`）→ 崩溃缓冲区为空 |

---

## D. 依赖 / 版本

| # | 症状 | 根因 | 解法 |
|---|---|---|---|
| D1 | `IncompatibleComposeRuntimeVersionException` | **Compose BOM 与 KMP 库（如 Haze）的 CMP 依赖版本线不一致** | 让 BOM 与 KMP 库**同属一条 compose 小版本线**（见 [04](04-dependency-versions.md) §2） |
| D2 | `AAR metadata` 报 `activity:1.11.0 requires compileSdk 36 + AGP 8.9.1+` | KMP 库把 compose → activity 逐级抬高 | **锁低版本**（不为迁就一个传递依赖升级整条工具链） |
| D3 | 报错位置是 `activity`，改 `activity` 却无效 | **报错位置 ≠ 根因位置**（根因在 BOM 与 KMP 库的配对） | 顺着依赖链**往上追到起点**；定位后**删掉基于误诊加的 `constraints` 临时修补** |
| D4 | 看 `.pom` 看不到 KMP 库的真实依赖 | **KMP 的版本信息在 `.module`（Gradle Module Metadata，JSON）** | 拉 `.module` 文件，不要看 `.pom` |
| D5 | 不确定某版本是否存在 | 靠记忆猜 | 查 Maven 元数据：Central `repo1.maven.org/maven2/...`；**androidx 全在 Google Maven** `dl.google.com/dl/android/maven2/...` |
| D6 | 约定插件里 `apply("...")` 编译报"没有匹配的函数" | Kotlin 解析到**成员函数 `Project.apply`**（不接受 String） | 写 **`pluginManager.apply("...")`** |
| D7 | 约定插件源码 `Unresolved reference: accessors` | Gradle **只为 `build.gradle.kts` 生成版本目录访问器**，不为约定插件 Kotlin 源码生成 | 改用 `VersionCatalog.findLibrary("别名")` + 带友好报错的 `dep()` 辅助函数 |
| D8 | 纯逻辑模块编译要求 Compose 运行时 | **Compose 编译器插件要求类路径有 Compose 运行时** | 拆插件：通用库插件（不含 Compose）vs compose 库插件 |
| D9 | R8 报 `Missing class` 构建失败 | `proguard-rules.pro` 缺 `-dontwarn`（AGP 8.x 默认致命） | 按库补 `-dontwarn`（okhttp/okio/conscrypt/bouncycastle/openjsse 等） |
| D10 | R8 后运行时崩溃（反射/序列化失效） | 缺 `-keep` 规则 | 补序列化 `$$serializer` / Room / Hilt / JNI 引擎包名的 `-keep` |
| D11 | 发布包异常大 | **声明的依赖零代码引用** | 逐个大依赖核对源码引用；无引用则注释掉（→ [05](05-apk-size-audit.md) §3） |
| D12 | 引入某库后**构建直接失败** | 该库依赖**已废弃的 RenderScript** 等被移除的机制 | 换库（选"三年后还在"的、有稳定版本线的） |
| D13 | 老牌高星库在 Compose 项目里用不了 | 属**传统 View 体系**，与 Compose 不兼容 | 挑库看**技术代际**，不只看 star 数 |

---

## E. 体积 / 发布

| # | 症状 | 根因 | 解法 |
|---|---|---|---|
| E1 | 包体读数与内容对不上（差几十 MB） | 陈旧空洞 | 见 B8 / [05](05-apk-size-audit.md) §4 |
| E2 | release 里有很多 dex | R8 没生效 | 确认 `isMinifyEnabled = true`；核对 `-keep` 是否过宽 |
| E3 | release 里带 x86/armeabi | `abiFilters` 没配 | release 只留 `arm64-v8a` |
| E4 | `res/` 达 MB 级 | 资源未压缩 | `isShrinkResources = true` |
| E5 | 只在发布时才崩 | 从未跑过 release 构建（R8 规则不全） | **首次 release 构建要提前做**，别等发版；`lintVitalAnalyzeRelease` 能拦住会崩的问题 |
| E6 | 包体达标但"感觉不对" | 没区分 debug / release | 两个数字都要报，且**报告实测值** |

---

## F. 验证纪律（不是技术坑，但最常犯）

| # | 反模式 | 后果 | 正确做法 |
|---|---|---|---|
| F1 | "代码我检查过，应该没问题" | 5 个 UI 问题全部漏掉 | **装机截图，用眼睛看** |
| F2 | 只看"编译通过"就说完成 | 功能可能根本没通 | 区分**编译通过 / 单测通过 / 装机运行 / 界面验收 / 功能可用**五档 |
| F3 | 改了构建配置只看编译通过 | 引入回归 | 改完**重新装机验证**（无回归才收工） |
| F4 | 把"UI 都好了"说成"功能都好了" | 用户以为可用 | 主动说明**未验证**部分（如"翻译链路因缺密钥未端到端跑通"） |
| F5 | 交付一堆中间文件 | 用户无从下手 | 删临时文件，**只留最终交付物**，并说明用途与下一步 |
| F6 | 为迁就一个依赖升级整条工具链 | 连锁回归风险 | **保守优先**：锁低版本 |
| F7 | 交付里留"待办/TBD/风险"占位 | 用户仍需自己收尾 | 一次性给到可执行结论；确实未决的**明确列出并给出建议** |

---

## 关键词索引

| 搜这个 | 去哪 |
|---|---|
| `mmap failed` / 内存 / 提交内存 | [01](01-environment-setup.md) §5.2、[02](02-build-workflow.md) §3 |
| `sdkmanager` / 许可 / 代理 / BOM | [01](01-environment-setup.md) |
| 中文路径 / junction / 构建慢 / `--continue` | [02](02-build-workflow.md) |
| `adb` / 截图 / 模拟器 / ABI / RTL / UI 验收 | [03](03-device-verification.md) |
| Compose BOM / Haze / 版本冲突 / 约定插件 / R8 / 许可 | [04](04-dependency-versions.md) |
| 包体 / 瘦身 / 死依赖 / 空洞 / 体积 | [05](05-apk-size-audit.md) |
