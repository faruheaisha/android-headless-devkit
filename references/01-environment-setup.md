# 阶段 1 · 环境搭建：只用命令行装出 Android 工具链

**目标**：在一台没有 Android Studio、C 盘空间紧张、网络需代理的 Windows 机器上，
装出可编译可装机的完整工具链，且**全部装在指定盘**、不污染 C 盘。

**验收标准**：`adb devices` 有输出、`gradle -v` 正常、`emulator -avd X` 能起来。

---

## 1. 先确认"没有 IDE 也行"

Android Studio 免费（Apache-2.0，无订阅、无功能阉割、个人与商业项目均可）。
但真正决定能否开工的是**命令行工具是否齐备**：

| 组件 | 作用 | 是否必需 |
|---|---|---|
| JDK 17 | Gradle 与 Kotlin 编译器运行环境 | 必需 |
| Android SDK Command-line Tools | `sdkmanager` / `avdmanager` | 必需 |
| platform-tools | `adb` | 必需（装机验收全靠它） |
| platforms;android-35 | compileSdk 对应的平台 | 必需 |
| build-tools;35.0.0 | aapt2 / d8 等 | 必需 |
| emulator + system-image | 无头模拟器 | 做装机验收则必需 |

> 两条等价的安装路径：
> **A** 装 Android Studio（一次性装好 JDK(内置 jbr) + SDK + platform-tools + 模拟器，装完不必打开它）；
> **B** 只装命令行工具（JDK 17 + Command-line Tools 约 150MB + 接受许可）。
> 工具链与 A **完全等价**。本 skill 走 B 路线。

---

## 2. 目录布局（自包含，单盘集中）

```
<AndroidDev>/
├── jdk-17/         OpenJDK 17.0.2                    （约 295MB）
├── sdk/            ANDROID_HOME                      （约 10GB）
│   ├── cmdline-tools/latest/    sdkmanager / avdmanager
│   ├── platform-tools/          adb
│   ├── platforms/android-35/
│   ├── build-tools/35.0.0/
│   ├── emulator/
│   ├── system-images/android-33/google_apis/x86_64/
│   └── licenses/                许可哈希文件
├── avd/            ANDROID_AVD_HOME
├── gradle-8.9/     Gradle 本体
├── gradle-home/    GRADLE_USER_HOME（必须外移，见 §5）
└── tmp/
```

### 环境变量（五项，每次新 shell 都要设）

```powershell
$env:JAVA_HOME        = "<AndroidDev>\jdk-17"
$env:ANDROID_HOME     = "<AndroidDev>\sdk"
$env:ANDROID_SDK_ROOT = "<AndroidDev>\sdk"     # 有些工具只认这个
$env:ANDROID_AVD_HOME = "<AndroidDev>\avd"
$env:GRADLE_USER_HOME = "<AndroidDev>\gradle-home"
```

`scripts/env.ps1` 就是这件事的可执行版本，并会顺带清空失效代理（见 §4）。

---

## 3. 装 JDK：优先用国内镜像

**实测踩坑**：Adoptium / GitHub Releases 在代理下返回 **502**，下不动。

| 源 | 结果 |
|---|---|
| **华为云镜像** `mirrors.huaweicloud.com/openjdk/` | ✅ 610KB/s，186MB 用 17.5s |
| Microsoft `aka.ms` | ⚠️ 可用但慢（173KB/s） |
| Adoptium / GitHub Releases | ❌ 代理下 502 |

装完验证：

```powershell
& "$env:JAVA_HOME\bin\java" -version
# openjdk version "17.0.2" 2022-01-18
```

---

## 4. 代理：最容易误判的一类坑

### 4.1 命令行工具读代理，Java 程序读不到

这是**最容易浪费半小时**的一处。现象：`curl` 能下载，但 `sdkmanager` / Gradle 连不上源。

**根因**：shell 的 `http_proxy` 环境变量对 curl 等工具自动生效，
但 **Java 程序读不到它**，必须显式传 JVM 参数：

```powershell
$env:JAVA_OPTS = "-Dhttp.proxyHost=127.0.0.1 -Dhttp.proxyPort=<端口> " +
                 "-Dhttps.proxyHost=127.0.0.1 -Dhttps.proxyPort=<端口>"
```

Gradle 侧则写进 `gradle.properties`：

```properties
systemProp.http.proxyHost=127.0.0.1
systemProp.http.proxyPort=<端口>
systemProp.https.proxyHost=127.0.0.1
systemProp.https.proxyPort=<端口>
systemProp.http.nonProxyHosts=localhost|127.0.0.1
```

### 4.2 代理可能是"一次性会话代理"——失效后必须主动清掉

本项目踩到的真实情况：机器上曾配置过 `127.0.0.1:57572`，**那是一次性会话代理，
之后失效了**（端口不可连通）。若配置残留，Gradle 会**无法下载任何依赖**，
且报错信息不一定指向代理。

**所以每次构建前先清空代理环境变量**（`env.ps1` 已包含）：

```powershell
$env:HTTP_PROXY=""; $env:HTTPS_PROXY=""; $env:http_proxy=""; $env:https_proxy=""
```

判断该直连还是走代理：先测端口连通性，再测目标站可达性。
本项目最终结论是**直连可用**（`dl.google.com` 返回 200），故不配代理。

### 4.3 `Invoke-WebRequest` 的 SSL 信任问题

`dl.google.com` 对 PowerShell 的 `Invoke-WebRequest` 报 SSL 信任错误，
但 **`curl.exe` 正常**（能走代理 CONNECT）。

> **规则：所有下载一律用 `curl.exe`，不要用 `Invoke-WebRequest`。**

---

## 5. 磁盘与内存：两类会直接让构建失败的硬约束

### 5.1 `GRADLE_USER_HOME` 必须外移

Gradle 默认把依赖缓存放 `C:\Users\<用户>\.gradle`，动辄数 GB。
本项目起步时 **C 盘只剩 3.1GB** —— 不挪走必然构建失败。

```powershell
$env:GRADLE_USER_HOME = "<AndroidDev>\gradle-home"
```

**创建后总占用约 0.9GB**（依赖下载后会涨到数 GB）。空间不够时按 §5.2 的判断来清。

### 5.2 ★ `gradle-home` 满了什么能删、什么不能删（实测）

这是**最容易误删**的一块：`caches` 下的目录名很相似，但"能删"和"删了要重新下载"
差别巨大。按这张表判断，**不要凭"在 caches 目录下"就一律删**：

| 路径 | 是什么 | 可删？ | 代价 |
|---|---|---|---|
| `GRADLE_USER_HOME/caches/<版本>/`（如 `8.9/`，内含 `transforms/`） | 依赖转换后的产物 | ✅ | 下次构建重新转换（本地计算） |
| `GRADLE_USER_HOME/caches/build-cache-1/` | 构建缓存 | ✅ | 无（若已 `org.gradle.caching=false` 则纯残留） |
| **`GRADLE_USER_HOME/caches/modules-2/`** | **依赖仓库（下载来的 jar/aar）** | **❌ 不要删** | **触发全量重新下载，需联网且慢**（实测 653MB，是缓存里最大的一块） |
| `GRADLE_USER_HOME/daemon/`、`native/` | 守护进程日志与本地库 | ✅ | 无 |
| `GRADLE_USER_HOME/caches/journal-1/`、`.tmp/` | 日志与临时 | ✅ | 无 |

**判据：区分「可再生」（本地算一遍就有）与「需重新获取」（要联网下载）。**
前者随便删，后者要单独跟用户说清代价。

同理，项目里的 `**/build/` 与 `.gradle/`、`.kotlin/` 都可删，但**代价是下次构建变全量**
—— 实测增量 **2 分钟** → 全量约 **8 分钟**。这个代价必须一并告知，不能只报"省了 386MB"。

**实测释放量**（一次真实清理）：删掉全部 `**/build/`（386MB）+ `caches/8.9`
与 `build-cache-1`、`daemon`、`native`（236MB）+ 项目级 `.gradle`/`.kotlin`（23MB），
内容量合计 **645MB**，`gradle-home` 从 917MB 降到 654MB（只剩 `modules-2`）。

> ⚠️ **`gradle-home` 里只有缓存，删它的子目录不影响 Gradle 本体** ——
> Gradle 安装在 `<AndroidDev>/gradle-8.9`（与 `gradle-home` 是兄弟目录），
> 但如果你误删整个 `gradle-home`，依赖缓存与代理配置一起没了（见 §4.1 代理写在里面）。

> ⚠️ **内容量 ≠ 实际腾出的空间。** 实测删掉 645MB 内容，盘符可用空间只涨了约 290MB
> —— 期间有其他进程在写盘、页面文件在涨。**分别报这两个数**，
> 不要把内容量当成腾出的空间，也不要因此以为删除失败。

### 5.3 真正的瓶颈是"提交内存"，不是物理内存

**这是最难自查的一类故障。** 现象：Gradle 守护进程 JVM 直接**原生内存崩溃**：

```
Native memory allocation (mmap) failed to map 333447168 bytes for G1 virtual space
```

崩溃时的机器状态（实测）：

```
物理内存 15.7GB / 可用约 1GB
提交上限 42.1GB / 已提交 41.2GB / 可用 0.89GB
C: 仅剩 4.4GB  →  页面文件无法自动扩容  →  提交上限被卡死在 42GB
```

**根因链**（三条互相叠加）：

1. **提交量最大的进程是 OneDrive，单独提交了 14.5GB**（而物理占用仅 719MB）
2. C 盘空间不足以让页面文件自动扩容 → 提交上限被锁死
3. 任何新 JVM 进程都分配不到内存 → 构建崩溃

**处置**：

- 构建前先看**提交可用**（不是物理可用）：`Get-CimInstance Win32_OperatingSystem`
  的 `FreeVirtualMemory`
- **提示用户退出 OneDrive / 云盘客户端**（实测退出后提交可用从 0.84GB → 7.26GB，
  构建立刻跑得起来）
- 长期方案：把页面文件从空间紧张的盘迁到空闲盘（需管理员权限，通常要重启）
- 工程侧同时压内存参数（见 [02-build-workflow.md](02-build-workflow.md) §3）

> **教训**：报"内存不足"时，先查**提交内存**。物理内存看起来充足也可能崩。

---

## 6. 装 SDK 组件：无 TTY 环境下的两个拦路问题

### 6.1 `sdkmanager` 的许可接受需要 TTY

`sdkmanager --licenses` 是**交互式**的，在无终端（无 TTY）环境里读不到输入，会卡住。

**解法：直接写许可哈希文件**到 `sdk/licenses/`。

本机实际写入的四个文件与内容（**多来源交叉验证过的值**）：

| 文件名 | 内容 |
|---|---|
| `android-sdk-license` | `8933bad161af4178b1185d1a37fbf41ea5269c55`<br>`d56f5187479451eabf01fb78af6dfcb131a6481e`<br>`24333f8a63b6825ea9c5514f83c2829b004d1fee` |
| `android-sdk-preview-license` | `84831b9409646a918e30573bab4c9c91346d8abd` |
| `android-googletv-license` | `601085b94cd77f0b54ff86406957099ebe79c4d6` |
| `intel-android-extra-license` | `d975f751698a77b662f1254ddbeed3901e976f5a` |

> ⚠️ **这意味着代用户接受了 Google 的 Android SDK 许可条款。**
> 这是自动化 SDK 安装的标准做法，但既然是以用户名义接受，**应当明确告知用户**。

### 6.2 PowerShell 管道给 `.bat` 的 stdin 无效

`sdkmanager.bat` 收不到管道输入。绕过 `.bat`，直接调 Java 入口：

```powershell
java -classpath "$sdk\cmdline-tools\latest\lib\sdkmanager-classpath.jar" `
     com.android.sdklib.tool.sdkmanager.SdkManagerCli <参数>
```

### 6.3 需要装的组件

```powershell
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0" `
           "emulator" "system-images;android-33;google_apis;x86_64"
```

> **为什么测的是 android-33 而不是 35**：模拟器镜像选低一档更稳、占用更小；
> 编译用 compileSdk 35，运行在 API 33 上即可（minSdk 29）。
> `google_apis`（非 `google_apis_playstore`）不带 Play 商店，便于调试且可写系统分区。

---

## 7. 编码坑：`-Encoding UTF8` 会写 BOM

PowerShell 5.1 的 `-Encoding UTF8` **会写入 BOM**（`EF BB BF`），这会：

- 破坏 `javac` 编译（源码首字符被当作非法字符）
- 破坏 `sdkmanager` 的**许可哈希校验**（文件内容前面多了三个字节）

**必须用无 BOM 写法**：

```powershell
[System.IO.File]::WriteAllText($path, $content, (New-Object System.Text.UTF8Encoding($false)))
```

> 这是本环境**贯穿始终**的一条硬规则，所有由脚本写出的文件都要走这个写法。

---

## 8. 模拟器加速：查 WHPX，不要找 HAXM

```powershell
& "$env:ANDROID_HOME\emulator\emulator-check.exe" accel
```

实测输出：

```
accel: 0
WHPX(10.0.26200) is installed and usable.
```

- **`accel: 0` 表示硬件加速就绪**（返回 `0` 是"一切正常"，不是错误码）
- **Intel 11 代及以后的 CPU 用 WHPX**，不要去找 HAXM（Intel 已废弃该方案）
- 若不可用，模拟器会退化为纯软件模拟，极慢

---

## 9. 创建 AVD（含实测参数）

```powershell
avdmanager create avd -n <名称> -k "system-images;android-33;google_apis;x86_64" `
                      -d medium_phone
```

`medium_phone` 是现代中端机档案 —— **贴合中低端真机的性能与屏幕条件**，
比用平板或高端机档案更能暴露性能问题。

本机实际生成的关键配置（`config.ini` 实测值）：

| 项 | 值 | 说明 |
|---|---|---|
| `abi.type` / `hw.cpu.arch` | `x86_64` | 与宿主机同架构，最快 |
| `hw.lcd.width × height` | `1080 × 2400` | 现代手机竖屏 |
| `hw.lcd.density` | `420` | |
| `hw.ramSize` | `2048` | 2GB，够用且省内存 |
| `disk.dataPartition.size` | 6442450944 | 约 6GB |
| `hw.cpu.ncore` | `4` | |
| `PlayStore.enabled` | `no` | 便于调试 |
| `hw.gpu.enabled` | `no` | 无头模式不需要；用 `-gpu swiftshader_indirect` |

> **创建后总占用约 3.9GB**（含系统镜像）。空间紧张时先确认可用空间。

---

## 10. 本阶段验收清单

- [ ] `& "$env:JAVA_HOME\bin\java" -version` 输出 17.x
- [ ] `adb devices` 能跑（无设备也可，只要不报命令不存在）
- [ ] `gradle -v` 正常，且 `GRADLE_USER_HOME` 指向非 C 盘
- [ ] `emulator-check accel` 返回 `accel: 0`
- [ ] `avdmanager list avd` 能看到刚建的 AVD
- [ ] 已确认**提交可用内存** ≥ 2.5GB，且已提醒用户退出云盘/浏览器
- [ ] 已告知用户：**已代其接受 Google Android SDK 许可条款**
- [ ] 所有脚本写文件都走**无 BOM UTF-8**
