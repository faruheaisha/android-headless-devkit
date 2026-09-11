# 阶段 3 · 真机验收：无头模拟器上的"构建 → 装机 → 截图 → 读图"闭环

**这是本 skill 的核心。** 一套流程的价值不在于"代码写完了"，
而在于**能证明它真的跑起来了、并且看起来是对的**。

**验收标准**：拿到首页与关键页的截图，读到画面并逐项核对；`logcat` 崩溃缓冲区为空；
进程存活。

---

## 1. 为什么必须做这一步

### 1.1 只有"看得见"才能发现的问题，占 UI 缺陷的绝大多数

本项目的真实数据：**5 个 UI 问题全部是装机截图后才发现的**，
其中 4 个在任何代码审查中都看不出来：

| # | 问题 | 为什么代码审查看不出来 |
|---|---|---|
| 1 | 状态栏与顶部内容重叠 | 代码里 `enableEdgeToEdge()` 是对的，问题在缺 `windowInsetsPadding` |
| 2 | 玻璃质感完全消失（纯白底上看不见白卡片） | alpha 0.72 在代码里"很合理"，实际渲染出来几乎隐形 |
| 3 | 卡片内部出现灰色暗环 | shadow 与半透明背景叠在同一 Box 上，阴影透上来了 —— 纯渲染问题 |
| 4 | 内容全挤在上半屏，下方大片空白"看起来没做完" | 布局约束与视觉感知的差异 |
| 5 | 返回按钮太小太隐蔽 | 对不识字用户是唯一退路，必须明显 —— 属可用性判断，不是报错 |

### 1.2 我能"看见"界面 —— 这条决定了协作方式

```
adb shell screencap -p /sdcard/s.png   →   adb pull   →   读取 PNG
```

**截图后我读取 PNG，就等于看见了界面。** 因此：

- 视觉问题**我可以自己发现并修正**，不必等用户截图反馈
- **维语/阿拉伯语等 RTL 渲染验收**尤其关键 —— 连写、方向、标点位置
  这些"必须用眼睛看"的东西，我也能验
- 这条能力边界应明确告知用户（它直接改变协作分工）

---

## 2. 无头启动模拟器

```powershell
$env:ANDROID_AVD_HOME = "<AndroidDev>\avd"
& "$env:ANDROID_HOME\emulator\emulator.exe" -avd <AVD名> `
    -no-window -no-audio -no-boot-anim -gpu swiftshader_indirect
```

| 参数 | 作用 |
|---|---|
| `-no-window` | **无窗口**：不弹窗打扰用户，适合自动化 |
| `-no-audio` | 省资源 |
| `-no-boot-anim` | 跳过开机动画，启动更快 |
| `-gpu swiftshader_indirect` | **软件渲染**：保证 Compose 界面可靠出图（硬件加速在无头环境下可能出不来画面） |

> **关键**：`-gpu swiftshader_indirect` 是无头截图能成功的前提。
> 用默认 GPU 模式在 `-no-window` 下常得到黑屏或空图。

### 启动是异步的 —— 必须等，不能靠 sleep 猜

```powershell
& $adb wait-for-device                      # 等设备连上
for($i=0; $i -lt 60; $i++){
  $b = (& $adb shell getprop sys.boot_completed 2>&1 | Out-String).Trim()
  if($b -eq "1"){ break }
  Start-Sleep -Seconds 3
}
```

**实测约 24 秒**完成启动（冷启动）。轮询 `sys.boot_completed` 比固定 sleep 可靠得多。

---

## 3. 装机 → 启动 → 截图

```powershell
$adb = "$env:ANDROID_HOME\platform-tools\adb.exe"

# 1) 安装（-r 覆盖安装，-t 允许测试包）
& $adb install -r -t "<apk路径>"

# 2) 强制停止旧进程后冷启动（避免看到的是旧版本的界面）
& $adb shell am force-stop <包名>
Start-Sleep -Seconds 2
& $adb shell am start -n "<包名>/<Activity>"
Start-Sleep -Seconds 12      # 留足冷启动时间

# 3) 截图 → 拉回本地
& $adb shell screencap -p /sdcard/s1.png
& $adb pull /sdcard/s1.png "E:\out\s1.png"
```

### ★ 截图目标路径必须是 ASCII

**中文路径会让 `adb pull` 失败**（与 Gradle 的中文路径问题是同一类编码根因）。

```powershell
# ❌ & $adb pull /sdcard/s.png "E:\claude code\爸妈专用翻译\截图.png"
# ✅ & $adb pull /sdcard/s.png "E:\out\shot1.png"
```

拉回后再由脚本/工具复制到项目内的中文目录，**不要让 adb 直接写中文路径**。

### 截图前先 `Remove-Item` 旧文件

否则 `adb pull` 失败时旧的截图还在，会**误判为"新截图成功"**：

```powershell
Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue
& $adb pull /sdcard/s1.png $dst
if(Test-Path -LiteralPath $dst){ "截图 OK" } else { "截图失败" }
```

---

## 4. 崩溃与存活检查

```powershell
# 崩溃缓冲区（只读 crash buffer，噪音小）
$crash = (& $adb logcat -d -b crash -t 12 2>&1 | Out-String).Trim()
if($crash){ $crash } else { "无崩溃" }

# 进程是否还活着（PID 非空即存活）
& $adb shell pidof <包名>
```

**两个检查配合看**：

- 进程存在 + 崩溃缓冲区为空 → 正常
- 进程存在但截图是白屏/黑屏 → 渲染问题（换 `swiftshader_indirect` 重试）
- 进程不存在 → 启动即崩，看 crash buffer 与 `logcat -d | Select-String "FATAL|AndroidRuntime"`

> 光看"安装成功"不够 —— 装上了、启动了、**并且跑起来了**才是三件事。

---

## 5. 与界面交互（能力有限，要清楚边界）

```powershell
& $adb shell input tap <x> <y>       # 按坐标点击
& $adb shell input swipe x1 y1 x2 y2 # 滑动
& $adb shell input text "abc"        # 输入（仅 ASCII）
```

**边界**：`input tap` 是**盲点** —— 我不知道当前界面元素的确切坐标，
只能按设计稿估算。点击后**必须再截一张图确认结果**，不能假定"点到了"。

**可靠做法**：截一张图 → 从图上量出目标元素的坐标 → 再点 → 再截图确认。

验证导航是否正常（本项目用法）：点第二个卡片 → 截图 → 确认进入了对应页面：

```powershell
& $adb shell input tap 250 830       # 第二个卡片
Start-Sleep -Seconds 6
& $adb shell screencap -p /sdcard/s2.png
```

---

## 6. 模拟器的关闭方式：优雅 vs 强杀

```powershell
# ✅ 优雅关闭
& $adb emu kill
Start-Sleep -Seconds 8

# ⚠️ 仅在优雅关闭无效时使用
Get-Process -Name qemu-system-x86_64,emulator -ErrorAction SilentlyContinue | Stop-Process -Force
```

### 为什么强调"优雅"

**实测**：强杀（`Stop-Process -Force`）会在 AVD 目录留下一个 **约 2GB 的 `ram.img`
（内存快照残留）**；优雅关闭会自动清理它。

残留处置：确认模拟器进程已停后直接删除（**下次启动会自动重建**，不是数据丢失）：

```powershell
Remove-Item -LiteralPath "<avd>\<名称>.avd\ram.img" -Force -ErrorAction SilentlyContinue
# 同理可删 snapshots/ 与 *.qcow2 快照（均为可重建产物）
```

> 空间紧张时这一步能立刻回收 2GB。**但务必先确认模拟器进程已完全停止**。

---

## 7. ABI 不匹配：装机失败的头号原因

```
INSTALL_FAILED_NO_MATCHING_ABIS
```

**根因**：APK 里没有设备/模拟器对应架构的原生库（`.so`）。

- **模拟器是 x86_64**，真机几乎都是 **arm64-v8a**
- 只要依赖里有原生库（推理引擎、图像处理、部分媒体库），就必须包含匹配的 ABI

**标准配置**（本项目做法）：

```kotlin
buildTypes {
    getByName("debug") {
        // 调试包额外带 x86_64 —— 开发用的模拟器是 x86_64 架构
        ndk { abiFilters.clear(); abiFilters.addAll(listOf("arm64-v8a", "x86_64")) }
    }
    getByName("release") {
        // 发布包只保留 arm64-v8a：现代机型均为 64 位，去掉其他可显著减小体积
        ndk { abiFilters.clear(); abiFilters.addAll(listOf("arm64-v8a")) }
    }
}
```

**判断方法**：装机失败时先查 APK 里有哪些 ABI：

```powershell
python scripts\apk_report.py "<apk>"      # 会列出 lib/ 下的全部 ABI
```

---

## 8. ★ UI 验收清单（实战沉淀，逐项对着截图看）

### 8.1 通用项

| 检查项 | 判据 | 本项目踩过的坑与解法 |
|---|---|---|
| **系统栏适配** | 内容不与状态栏时间/图标重叠，也不被导航栏遮挡 | `enableEdgeToEdge()` 后必须加 `windowInsetsPadding(WindowInsets.safeDrawing)` |
| **玻璃/半透明质感** | 浅色背景上卡片能看出"浮起" | **浅色底上的玻璃质感主要靠"浮起感"（阴影+高光描边）表达，而非透明度**。alpha 提高到 0.92 + 加强阴影 + 背景渐变下沿加深 |
| **卡片是否有污边/暗环** | 卡片内部不应有灰边 | **分两层画**：外层负责 shadow，内层负责玻璃面。同层叠加会让阴影透上来 |
| **内容是否填满** | 不能大片空白显得"没做完" | 卡片组用 `weight(1f)` + `Arrangement.Center` 垂直居中，留白均分到上下 |
| **最小触控尺寸** | 任何可点元素 ≥ 48dp | 主按钮做到 112dp、返回键 56dp（面向中老年/视力不佳用户刻意做大） |
| **可点元素数量** | 首屏尽量少 | 本项目首屏 6 个（3 主入口 + 粘贴条 + 2 顶栏图标），让用户靠位置+图标记住用法 |
| **返回/退出路径是否明显** | 一眼可见，不能是细小箭头 | 改成 56dp 圆形按钮 + `Icons.AutoMirrored.Outlined.ArrowBack` |

### 8.2 RTL（阿拉伯字母系语言：维语/阿拉伯语/希伯来语）专项

**这类界面必须逐项对着截图看**，代码里"写对了"不等于渲染对了。

| 检查项 | 正确表现 |
|---|---|
| 整体镜像 | 图标在**右**、文字**右对齐**、列表方向镜像 |
| 文字连写 | 字母正确连写，**无乱码、无方框（豆腐块）** |
| 字体可用性 | 若出现方框，说明设备缺该语言字体 → 需内嵌字体 |
| **返回箭头方向** | 用 `Icons.AutoMirrored.*` 让箭头在 RTL 下自动翻转（指向右侧 = 该语言习惯的"返回"） |
| 标点与数字方向 | 句末标点、数字串遵循双向算法（bidi），不跑到错误一侧 |
| 高光/阴影方向 | **不随镜像翻转** —— 光的方向应全应用一致，否则光照混乱 |
| 换行是否切断字母 | 阿拉伯字母连写不能从字母中间断开 |

> `supportsRtl="true"` 是 RTL 生效的**硬性前提**（写在 `AndroidManifest.xml`）。
> Compose 用 `LayoutDirection.Rtl` 一次性镜像整棵树，这是选 Compose 的关键理由之一。

### 8.3 布局顺序敏感项

如果界面是"多个等权重的块"，注意**块怎么分配剩余空间**：

- 用 `weight(1f)` 让每块均分 → 块会被拉得很高，在大屏上显得空
- 用**固定高度** + 剩余空间统一留白 → 大按钮仍然远超最小触控标准，视觉更稳
- 关键：**留白要集中在下方**，而不是块之间散开（散开看起来像"没做完"）

---

## 9. 如何"验证"到什么程度：区分已验证与未验证

汇报时必须分清，不能把"编译通过"说成"功能可用"：

| 说法 | 含义 | 需要的证据 |
|---|---|---|
| **编译通过** | 代码语法与类型正确 | `BUILD SUCCESSFUL` |
| **单元测试通过** | 纯逻辑正确 | 测试输出（N 用例全通过） |
| **装机运行** | 在真实 Android 运行时能启动 | `install` 成功 + 进程存活 + 无崩溃 |
| **界面验收** | 渲染符合设计 | **截图 + 逐项核对** |
| **功能可用** | 端到端能完成一件真实的事 | **真实数据的端到端跑通**（最难，最容易被误报） |

**本项目的一个真实例子**：UI 与导航都已装机验证 ✅，
但"点翻译按钮"这条路**至今没有端到端跑通** —— 因为没配 API 密钥，
所有翻译实现都被判定为不可用，用户拿到的是一个语焉不详的错误。
**这类"看着都好了但核心功能没通"的状态，必须如实说明，不能含糊过去。**

> **纪律**：主动区分"已验证"与"未验证"，并为已验证的部分交付**可复现的证据**
> （截图、日志、命令输出），而不是"我检查过代码，应该没问题"。

---

## 10. 一键脚本

`scripts/verify_loop.ps1` 把本节流程封装成一条命令：

```powershell
.\scripts\verify_loop.ps1 -Apk "<apk>" -Package "com.example.app" `
    -Activity ".MainActivity" -OutDir "E:\out" -Tap "250,830" -SettleSeconds 12
```

它依次完成：安装 → 强制停止 → 启动 → 等冷启动 → 首页截图 → （可选）点击 → 二次截图
→ 崩溃检查 → 进程存活检查，并把结果写成一份小报告。

---

## 11. 本阶段验收清单

- [ ] 模拟器以 `-no-window -gpu swiftshader_indirect` 启动
- [ ] 通过轮询 `sys.boot_completed` 确认启动完成（不是固定 sleep）
- [ ] 安装成功（无 `INSTALL_FAILED_NO_MATCHING_ABIS`；ABI 已用 `apk_report.py` 核对）
- [ ] 启动前 `am force-stop`（避免看到旧版本界面）
- [ ] 截图**目标路径为 ASCII**，且截图前已删旧文件
- [ ] **已读取截图并逐项核对** UI 验收清单（含 RTL 专项）
- [ ] 崩溃缓冲区为空 + 进程存活
- [ ] 若点击过界面 → 已二次截图确认结果
- [ ] 模拟器已**优雅关闭**；若曾强杀，已检查并清理 `ram.img`
- [ ] 汇报中已区分**已验证**与**未验证**，并给出可复现证据
