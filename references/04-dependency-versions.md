# 阶段 4 · 依赖与版本对齐：把版本冲突一次诊断到底

**目标**：版本目录稳定、R8 能过、无用依赖剔除、构建配置可维护。

**验收标准**：`:app:assembleDebug` 与 `:app:assembleRelease` 均 `BUILD SUCCESSFUL`
（R8 无 `Missing class`），且每个已声明依赖都有代码引用。

---

## 1. ★ 核心认知：KMP 库会把整条版本线一起拉高

**这是本项目最难定位的一类问题，也是最有复用价值的认知。**

JetBrains 的 Compose Multiplatform（CMP）库（如 Haze 玻璃效果库）会把
**整条 androidx Compose / AndroidX 版本线**一起抬起来，进而抬高
`activity`，再进而要求更高的 `compileSdk` 与 `AGP`。

### 完整的传导链（实测定位）

```
我的 Compose BOM 2024.12.01 → compose 1.7.6
        ↕ 版本冲突
haze 1.7.1 → Compose Multiplatform 1.9.3 → androidx compose 1.9.4
                                        ↓
                          ui-tooling 1.9.4 拉 activity-compose
                                        ↓
                          activity 1.11.0 → 要求 compileSdk 36 + AGP 8.9.1+
```

**表现出的报错**（看起来毫不相关）：

```
IncompatibleComposeRuntimeVersionException
AAR metadata check failed: androidx.activity:activity:1.11.0 requires compileSdk 36
```

> **教训**：选版本**不能只看单个库的版本号**，要顺着"CMP → compose → activity → SDK/AGP"
> 这条链一起看。冲突报错往往出现在链条末端，根因在链条起点。

---

## 2. 实测版本对应表（可直接复用）

### 2.1 Haze（CMP 玻璃效果库）与 androidx 的绑定关系

| Haze | 其 CMP 依赖 | 对应 androidx compose | activity | 要求 |
|---|---|---|---|---|
| **1.6.10** | **1.8.0** | **1.8.x** | 1.9.x | ✅ **compileSdk 35 即可** |
| 1.7.0 – 1.7.3 | 1.9.3+ | 1.9.x | 1.11.0 | ❌ 需 compileSdk 36 + AGP 8.9.1+ |

### 2.2 Compose BOM → compose-ui 映射（Google Maven 实测）

| BOM | compose-ui |
|---|---|
| 2024.12.01 | 1.7.6 |
| 2025.02.00 / 2025.03.00 / 2025.04.00 | 1.7.8 |
| 2025.04.01 | 1.8.0 |
| 2025.05.00 | 1.8.1 |
| **2025.05.01** | **1.8.2** ← 本项目采用 |
| 2026.09.00（当时最新） | 1.12.x |

**配法**：`haze = 1.6.10` + `composeBom = 2025.05.01` —— 两者同属 compose 1.8.x 线，
与 `compileSdk 35` / `AGP 8.7.3` 相容。

> 将来若升到 `compileSdk 36 + AGP 8.9.1+`，把 haze 与 composeBom **一起**升即可。
> **关键是"一起"，不要只升一个。**

---

## 3. 诊断方法论（三步定位版本冲突）

### 3.1 导出依赖树，找"来源行及其父节点"

```powershell
gradle -p <项目> :app:dependencies --configuration debugRuntimeClasspath > deps.txt
```

然后**搜索具体版本号**，向上追它的父节点：

```powershell
Select-String -Path deps.txt -Pattern "1\.11\.0" -Context 3,0
```

**要点**：不要只看"谁引入了它"，要看**整条引入路径** ——
冲突常来自"我的 BOM 想给 1.7.6，但某个库的传递依赖给了 1.9.4"。

### 3.2 用 Maven 元数据核实版本真实性（不要靠记忆）

| 仓库 | URL 模式 |
|---|---|
| Maven Central | `https://repo1.maven.org/maven2/<group路径>/<artifact>/maven-metadata.xml` |
| **Google Maven**（androidx 全在这） | `https://dl.google.com/dl/android/maven2/<group路径>/<artifact>/maven-metadata.xml` |

```bash
curl -s "https://dl.google.com/dl/android/maven2/androidx/compose/compose-bom/maven-metadata.xml"
```

### 3.3 ★ KMP 库要看 `.module` 文件，不是 `.pom`

这是最容易踩的一处：**Kotlin Multiplatform 库（如 Haze）的版本信息在 `.module` 文件里**
（Gradle Module Metadata，JSON 格式），`.pom` 里看不到真实依赖。

```bash
# 看 .module 而不是 .pom
curl -s "https://repo1.maven.org/maven2/dev/chrisbanes/haze/haze/1.6.10/haze-1.6.10.module"
# 在里面找 compose / jetbrains 的版本约束
```

> 判断一个库是否 KMP：看它的 artifact 是否带 `-android` / `-jvm` 等后缀，
> 或文档里是否提 "Compose Multiplatform"。

### 3.4 用 `:app:help` 做快速配置校验

改完依赖声明先跑它（实测约 2.5 分钟，不编译），快速排除语法/解析问题：

```powershell
gradle -p <项目> :app:help
```

---

## 4. ★ 保守优先：锁版本，而不是升级整条工具链

面对"传递依赖要求更高 compileSdk"时，有两条路：

| 方案 | 做法 | 代价 |
|---|---|---|
| **升级工具链** | 升 AGP + Gradle + compileSdk 36 | 连锁改动大、回归风险高、可能引入新问题 |
| **锁低版本**（推荐） | 把冲突的传递依赖降到与当前工具链相容的版本 | 需确认降级后的库仍满足需求 |

**本项目选择锁低版本**：只改两个版本号（`haze 1.7.1 → 1.6.10`、
`composeBom 2024.12.01 → 2025.05.01`），
**保住了 `compileSdk 35` / `AGP 8.7.3`**，没有动整条链。

> **判断原则**：**不为迁就一个传递依赖去升级 AGP + Gradle + compileSdk 整条链。**
> 这与"可能返工的选型要保守"是同一条原则。

### 顺带纠正一个错误修法

曾经因为**误判**（以为是 activity 版本问题）加过一个 `constraints` 块去强行锁 activity ——
**那是错的**，问题在 BOM 与 haze 的配对。定位到真正根因后该块已删除。

> **教训**：报错位置（activity）不等于根因位置（BOM 配对）。
> 定位到根因后，**要把基于误诊加的临时修补删掉**，否则会留下误导后来者的"技术债"。

---

## 5. 构建配置的组织：约定插件 + 版本目录

### 5.1 版本目录（`gradle/libs.versions.toml`）是版本的单一真相来源

所有版本号集中一处，模块 build 文件只引用别名。好处：升级时只改一个地方，
且**冲突关系可以写在注释里**（本项目就把 Haze 的版本链原因写在版本条目旁边）。

### 5.2 ★ 必须拆分"通用库插件"与"Compose 库插件"

**Compose 编译器插件有一条硬性要求：类路径上必须有 Compose 运行时**，
否则编译期直接抛 `IncompatibleComposeRuntimeVersionException`。

早期把 Compose 塞进通用库插件 → 给纯逻辑模块（如核心工具库）也套上 Compose 编译器
→ 它没有 Compose 依赖 → **编译失败**。

**拆法**：

| 插件 | 用于 | 内容 |
|---|---|---|
| `android.library`（通用） | 纯逻辑模块（common / network / data:*） | 不含 Compose |
| `android.library.compose` | 含界面的模块（designsystem / ui / data:image） | 通用 + Compose 编译器 + 最小 Compose 依赖集 |
| `android.feature` | feature 模块 | 基于 compose 版 |

**收益**（实测）：既修好问题，**全量构建从 24 分钟降到 8.5 分钟**
（Compose 编译器插件很慢，不给不需要的模块加装它）。

> **设计要点**：约定插件只保留"所有模块都必须一致"的基线
> （compileSdk/minSdk/JVM 版本/Compose/测试依赖）；
> **模块专属配置（ABI 过滤、混淆、打包、注解处理器参数）全部下放到各模块 build 文件**。
> 只为 1 个模块服务的约定插件是过度设计 —— 直接写进该模块 build 文件即可。

### 5.3 ★ 约定插件源码里的两个真 bug（容易踩）

**Bug 1：`apply("...")` 会被解析成 `Project.apply`**

在 `with(target) { }` 里写 `apply("com.android.library")`，Kotlin 会优先解析到**成员函数**
`Project.apply`（只接受 closure/options/action，不接受 String），报：

```
None of the following functions can be called with the arguments supplied: apply(closure...)
```

**必须写 `pluginManager.apply("...")`。**

**Bug 2：约定插件的 Kotlin 源码拿不到版本目录的类型安全访问器**

```kotlin
import org.gradle.accessors.dm.LibrariesForLibs   // Unresolved reference: accessors
```

**Gradle 只为 `build.gradle.kts` 脚本生成访问器，不为约定插件的 Kotlin 源码生成**
（需额外的 `files(libs.javaClass...)` hack 才生效）。

**解法：改用字符串别名查找 + 友好报错的辅助函数**：

```kotlin
internal val Project.libs: VersionCatalog
    get() = extensions.getByType<VersionCatalogsExtension>().named("libs")

internal fun Project.dep(alias: String): Provider<MinimalExternalModuleDependency> {
    val found = libs.findLibrary(alias)
    return if (found.isPresent) found.get()
    else error("版本目录里找不到依赖别名 \"$alias\"，请检查 gradle/libs.versions.toml")
}
```

代价是别名写错要到运行时才发现（用上面的 `error()` 给出可读提示弥补）。

### 5.4 关闭 configuration-cache（与 KGP 冲突）

```
Failed to instrument class ... CustomPropertiesFileValueSource$Parameters
```

`org.gradle.configuration-cache=false`。排障期不必强求开启。

---

## 6. R8 / ProGuard：首次 release 构建前必须补的规则

**不要等到发版才发现 R8 过不去。** R8 报 `Missing class` 时 AGP 8.x **默认视为致命错误**。

### 常见需要 `-dontwarn` 的库

`okhttp3` / `okio` / `org.conscrypt` / `org.bouncycastle` / `org.openjsse`、
ML Kit（若引入）、各厂商推送 SDK。

### 常见需要 `-keep` 的（反射 / 序列化 / JNI 调用方最容易漏）

```proguard
# Kotlin 序列化：靠注解生成序列化器，混淆会失效
-keepclassmembers class **$$serializer { *; }
-keepclasseswithmembers class * { kotlinx.serialization.KSerializer serializer(...); }

# Room
-keep class * extends androidx.room.RoomDatabase

# Hilt / Dagger
-keep class dagger.hilt.** { *; }
-keep class javax.inject.** { *; }

# JNI 反射调用的推理引擎（按实际包名）
-keep class ai.onnxruntime.** { *; }
-dontwarn ai.onnxruntime.**

# 保留行号便于崩溃定位
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile
```

### 验证方法

```powershell
gradle -p <项目> :app:assembleRelease --no-daemon 2>&1 | Tee-Object rel.log
Select-String -Path rel.log -Pattern "BUILD SUCCESSFUL|Missing class|R8|error:"
```

**实测结果**：无 `Missing class`、无 fatal error → 规则足够。
同时 `lintVitalAnalyzeRelease` 也会跑（release 的致命 lint 能拦住会崩的问题）。

---

## 7. 依赖准入：许可干净 + 真的被用到

### 7.1 许可准入清单（本项目标准：只允许 MIT / Apache-2.0 / BSD）

逐项核实后的结论（供参考）：

| 用途 | 采用 | 许可 |
|---|---|---|
| 玻璃拟态 | Haze | Apache-2.0 |
| 图片加载缓存 | Coil 3 | Apache-2.0 |
| 手势缩放 | Telephoto | Apache-2.0 |
| 端侧 OCR | RapidOCR（ONNX Runtime） | Apache-2.0 / MIT |
| 数据库 | Room | Apache-2.0 |
| 依赖注入 | Hilt | Apache-2.0 |
| 网络 | OkHttp | Apache-2.0 |

**明确排除及理由**：

- **ML Kit** —— 闭源专有，且依赖 GMS（国内缺失）
- **LaMa / MI-GAN 类修复模型** —— 体积大（约 200MB）+ 权重许可未明确
- **老牌模糊库（Blurry/BlurView/BlurKit）** —— 传统 View 体系，**与 Compose 不兼容**
- **EtsyBlur** —— 依赖已废弃的 RenderScript，**构建直接失败**
- **全部 GPL / AGPL / LGPL** —— 传染性，与项目许可目标冲突

> **挑库不能只看 star 数，要看"技术代际"。**
> EtsyBlur 当年很流行，因 Android 废弃 RenderScript 而整体作废；
> 几个高星模糊库属 View 体系，在 Compose 项目里不可用。
> 更实际的隐性标准是：**三年后这个库还在不在**（优先选有稳定版本线的）。

### 7.2 ★ "声明了" ≠ "用到了"（体积审计的最大收益点）

依赖树**看不出**"声明了但零引用"。这必须单独检查：

```powershell
# 每个模块声明了什么
Select-String -Path */build.gradle.kts -Pattern "libs\.[a-zA-Z0-9._]*"

# 源码里是否真的 import 了它
Select-String -Path (Get-ChildItem -Recurse -Filter *.kt).FullName -Pattern "<包名关键字>"
```

**本项目实例**：一个推理引擎原生库被声明在某模块里，但该模块**连一个 `.kt` 文件都没有**
（属后续里程碑范围），结果让发布包多出 **17.63MB（占 82%）**。
剔除后发布包 **20.54MB → 2.80MB**。

**处置方式**：**注释掉依赖行 + 写明恢复条件**，
保留模块与版本目录条目不变（不删架构），将来实现该功能时一行恢复。
判定与量化方法见 [05-apk-size-audit.md](05-apk-size-audit.md) §3。

---

## 8. 本阶段验收清单

- [ ] 已按"CMP → compose → activity → SDK/AGP"链条检查版本相容性
- [ ] 冲突的传递依赖已**用 Maven 元数据核实**过版本（KMP 库看 `.module`）
- [ ] 已选择"锁低版本"而非"升级整条工具链"，并记录原因
- [ ] 基于**误诊**加的临时修补已删除
- [ ] 版本号集中在版本目录，冲突关系写在注释里
- [ ] Compose 编译器插件只作用于真正写 Compose 的模块
- [ ] 约定插件用 `pluginManager.apply("...")`，版本目录用字符串别名查找
- [ ] `assembleRelease` 已实跑通过，**R8 无 `Missing class`**
- [ ] 每个已声明依赖都已在源码中找到引用（无引用即死重量 → 处理）
- [ ] 所有依赖许可为 MIT / Apache-2.0 / BSD，无 GPL/AGPL/LGPL
