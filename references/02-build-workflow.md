# 阶段 2 · 构建打通：让 Gradle 真的编出来

**目标**：`assembleDebug` 成功产出 APK，且排障路径可复用。

**验收标准**：看到 `BUILD SUCCESSFUL`，APK 文件存在于 `app/build/outputs/apk/`。

---

## 1. ★ 中文路径：Gradle 启动器的致命坑（通用解法）

### 现象

```
The specified project directory 'D:\工作\我的项目\app' does not exist
```

**路径明明存在**，但 Gradle 说找不到。

### 根因

`gradle.bat` 经 `cmd.exe` 传递参数，**非 ASCII 路径被编码搞坏**。
这与项目本身无关，是启动器层面的问题。

### 解法：建 ASCII 目录联接（junction）做透明桥接

```powershell
# 别名与目标都按自己的实际情况替换：<别名> 必须纯 ASCII
New-Item -ItemType Junction -Path "E:\proj" -Target "D:\工作\我的项目\app"
```

之后构建一律用 ASCII 别名：

```powershell
gradle -p E:\proj :app:assembleDebug
```

**要点**：

- 用 **Junction**（目录联接）而非符号链接 —— 不需要管理员权限
- **用户文件的实际位置完全不变**，联接只是透明别名
- 这是 **Android 构建在中文路径下的通用解法**，不止某台机器适用
- 同理，`adb pull` 的目标路径也必须 ASCII（见 [03](03-device-verification.md)）

> 附带好处：工具链（`E:\AndroidDev`，本 skill 默认值）与构建入口（`E:\proj`）
> 都在 ASCII 路径上，后续所有命令都不必再操心编码问题。
> 本文其余示例统一用 `E:\proj` 代指**你为项目建的 ASCII 联接**。

### ⚠️ 建了联接之后必然踩到的坑：`find` 穿不过 junction

**这是实跑才发现的**，而且一定会踩 —— 因为你建了联接，之后任何"扫一遍项目"
的操作（统计体积、清理临时文件、查文件数）都会经过它。

| 命令 | 能否穿过 junction |
|---|---|
| `ls -la <联接路径>/` | ✅ **能**，正常列出真实内容 |
| `find <联接路径> -type f` | ❌ **不能**，返回空 |

**两个由此产生的假象**（都会误导判断）：

1. **"这个目录是空的"** —— `find /e/proj -maxdepth 1 -type f` 返回空，
   而 `ls -la /e/proj/` 明明列出十几个文件。
   → 别据此认为目录为空，**体积统计用 `du`/PowerShell 递归，不要用 `find` 走联接**。
2. **"同一批文件被算了两次"** —— 如果扫描同时覆盖真实路径与联接路径
   （例如全盘扫描时，真实项目目录与指向它的联接目录同时被扫到），
   同一个 `build/` 目录会被计入两次，体积翻倍。
   → 清理时**只对真实路径操作**；否则第二次会报"不存在"，让你误以为删除失败。

**判定某个路径是不是联接**：

```bash
# Git Bash：`ls -d` 能显示，而 find 穿不过 —— 两者结果不一致即是联接
ls -d /e/proj

# PowerShell 更明确（会打印 LinkType）
Get-Item "E:\proj" | Select-Object Name, LinkType, Target
```

> **实践建议**：把联接只当作**构建入口**（`gradle -p E:\proj`），
> 不要把它当"第二份项目"来扫描或清理。所有文件操作都走真实路径。

---

## 2. 构建命令模板

```powershell
# ---- 环境变量（每次新 shell 都要设）----
$env:JAVA_HOME        = "E:\AndroidDev\jdk-17"
$env:ANDROID_HOME     = "E:\AndroidDev\sdk"
$env:ANDROID_SDK_ROOT = "E:\AndroidDev\sdk"
$env:ANDROID_AVD_HOME = "E:\AndroidDev\avd"
$env:GRADLE_USER_HOME = "E:\AndroidDev\gradle-home"
# 清掉可能残留的失效代理
$env:HTTP_PROXY=""; $env:HTTPS_PROXY=""; $env:http_proxy=""; $env:https_proxy=""

# ---- 构建 ----
& "E:\AndroidDev\gradle-8.9\bin\gradle.bat" -p "E:\proj" ":app:assembleDebug" --no-daemon
& "E:\AndroidDev\gradle-8.9\bin\gradle.bat" -p "E:\proj" ":app:assembleRelease" --no-daemon
& "E:\AndroidDev\gradle-8.9\bin\gradle.bat" -p "E:\proj" ":core:domain:test" --no-daemon
```

### 输出捕获（日志很长，必须落文件再筛）

```powershell
& "<gradle>" -p "<项目>" ":app:assembleDebug" 2>&1 |
  Out-File -LiteralPath "$proj\_build.log" -Encoding UTF8

Get-Content -LiteralPath "$proj\_build.log" |
  Select-String -Pattern "BUILD SUCCESSFUL|BUILD FAILED|^e: |error:" |
  Select-Object -First 10 | ForEach-Object { $_.Line }
```

> 日志文件用完**记得删**，别留在项目里。

---

## 3. 内存参数：按"小内存机器"配置（含实测配置）

内存不足会让 JVM **原生内存崩溃**（`mmap failed for G1 virtual space`）。
工程侧的应对是**刻意用保守参数，牺牲一点编译速度换构建稳定**。

`gradle.properties`（实测可用配置）：

```properties
# 堆压到 2GB、Metaspace 512MB、代码缓存 256MB
# 用 SerialGC：G1 会预留大块虚拟空间，小内存下 SerialGC 更稳
org.gradle.jvmargs=-Xmx2048m -XX:MaxMetaspaceSize=512m -XX:ReservedCodeCacheSize=256m -XX:+UseSerialGC -Dfile.encoding=UTF-8

# 并行构建会同时跑多个模块编译，内存峰值成倍上升 → 关掉
org.gradle.parallel=false

# worker 限 1，进一步压低峰值
org.gradle.workers.max=1

# 构建缓存曾出现「拒绝访问」导致缓存写入失败并连带任务失败 → 排障期先关
org.gradle.caching=false

# 配置缓存与 Kotlin Gradle 插件冲突 → 关掉
org.gradle.configuration-cache=false

# Kotlin 在 Gradle 进程内编译：省掉一个独立守护进程（约几百 MB）
kotlin.compiler.execution.strategy=in-process
```

### ★ 关键教训：用户级与项目级 `gradle.properties` 必须一致

本项目踩过的坑：**项目级设了 `-Xmx3072m`，但实际生效的是用户级
`GRADLE_USER_HOME/gradle.properties` 里的 `-Xmx4096m`** ——
守护进程按 4GB 去要内存，直接崩。

> **守护进程的内存参数以"用户级"为准（或说两者谁最后生效要看优先级），
> 排障时务必两处都检查。** 把两处设成相同值是稳妥做法。

---

## 4. ★ 排障方法论：一次拿全错误，别一次改一个

### 4.1 用 `--continue` 一次暴露全部错误

**单轮构建成本 6–24 分钟**，若一次只改一个错误然后重跑，会浪费大量时间。

```powershell
gradle -p <项目> :app:assembleDebug --continue
```

**实测效果**：首轮用 `--continue` 花 24 分钟，但**一次拿回了 24 个错误**，
信息量远大于逐模块编译（每模块约 6 分钟，且要看 N 轮）。

### 4.2 用 `:app:help` 做"快速配置校验"

改完 build 文件先做一次**不编译的配置阶段校验**：

```powershell
gradle -p <项目> :app:help
```

**实测约 2.5 分钟**，能在不进入编译的前提下快速排除 build 文件语法 / 插件 / 依赖声明问题。

### 4.3 优先怀疑自己的代码，而不是先怪环境

本项目所有构建失败最终都定位到**代码或配置缺陷**，环境问题只占少数。
分类经验：

| 报错特征 | 通常归属 |
|---|---|
| `Unresolved reference` / `^e: ` | 自己代码或漏依赖 |
| `None of the following functions can be called` | 自己代码的 API 用法 |
| `AAR metadata` / `requires compileSdk` | 依赖版本链问题（→ [04](04-dependency-versions.md)） |
| `Internal compiler error` | 内存不足（→ 本文 §3） |
| `mmap failed` | 提交内存耗尽（→ [01](01-environment-setup.md) §5.2） |
| 路径不存在但明明存在 | 中文路径（→ 本文 §1） |

---

## 5. 构建耗时预算（实测值，用于判断"是不是卡住了"）

| 任务 | 实测耗时 | 说明 |
|---|---|---|
| 单测 `:core:domain:test` | **0.05 秒**（16 用例） | 纯 JVM，无需模拟器 |
| 配置校验 `:app:help` | 约 **2.5 分钟** | 不编译 |
| 增量 `:app:assembleDebug` | **2 分 4 秒** | 只重做打包 |
| 全量 `:app:assembleDebug` | **7 分 42 秒** | `--no-daemon` |
| 首次全量（含排障期） | 约 **24 分钟** | 依赖下载 + 全模块编译 |
| 优化后全量 | **8.5 分钟** | 拆分 Compose 约定插件后 |
| `:app:assembleRelease`（R8 + lint） | **10 分 35 秒**（首次）→ **5 分 57 秒** | R8 阶段本身较慢 |

> **实战判断**：release 构建里 `lintVitalAnalyzeRelease` 会逐模块跑，
> 看到它在滚是**正常推进**，不是卡住。若超过预算上限仍无输出，才需排查。

### 一个真实的性能优化：拆分 Compose 约定插件

把 Compose 编译器从"所有库模块共用"拆成"仅需要界面的模块使用"，
**全量构建 24 分钟 → 8.5 分钟**。

原因：Compose 编译器插件很慢，且**要求类路径上必须有 Compose 运行时**，
给纯逻辑模块套上它会既拖慢又报错。详见 [04](04-dependency-versions.md) §4。

---

## 6. 增量构建的两个陷阱

### 6.1 陈旧 APK 空洞 → 体积读数虚高

**现象**：改完依赖重建，APK 体积**没有变化**，或变化不合理
（实测：debug 包显示 103.55MB，拆开只有 65MB）。

**根因**：Gradle 增量打包**未截断旧文件**，留下一段空洞。

**解法**：删掉 APK 文件再重跑打包（只需重做打包，实测 **2 分钟**）：

```powershell
Remove-Item -LiteralPath "<...>\app\build\outputs\apk\debug\app-debug.apk" -Force
gradle -p <项目> :app:assembleDebug --no-daemon
```

> 空洞**不影响运行**（zip 中心目录按声明读取，运行时跳过空洞），
> 但会**污染优化决策**。诊断与量化方法见 [05](05-apk-size-audit.md) §2。

### 6.2 改了构建配置后必须重新装机验证

改了 `build.gradle.kts` / 依赖 / 约定插件后，**不能只看"编译通过"就收工** ——
要重新装机、启动、截图、查崩溃，确认**无回归**。

> 这是本 skill 的一条硬规矩：**凡涉及构建配置，必须实跑验证再声称完成。**

---

## 7. 沙箱与权限注意事项

- Gradle 需要写入**工作区之外**的缓存目录（`GRADLE_USER_HOME`），
  在受限沙箱中会被拦截 → 构建命令需显式申请越权执行
- 某些环境会拦截 `Add-Type`（PowerShell 加载 .NET 程序集）→
  拆 APK / 算哈希等一律改用 **Python 标准库**，不要用 `System.IO.Compression`
- `cmd /c` 与 `[Diagnostics.Process]::Start` 可能被拦截 →
  用原生 PowerShell 调 `.bat`，或直接调 `java`

---

## 8. 本阶段验收清单

- [ ] 项目路径已用 **ASCII 联接**接入，命令中不再出现中文路径
- [ ] 环境变量五项已设，代理已清空
- [ ] 用户级与项目级 `gradle.properties` 的内存参数**一致**
- [ ] 构建前确认**提交可用内存** ≥ 2.5GB
- [ ] 排障用 `--continue` 一次拿全错误；配置问题先用 `:app:help` 快速验
- [ ] 看到 `BUILD SUCCESSFUL`，且 APK 文件确实生成
- [ ] 构建日志等临时文件用完已删
- [ ] 若改动过构建配置 → **已重新装机验证无回归**
