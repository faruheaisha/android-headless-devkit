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
adb exec-out screencap -p > s.png   →    读取 PNG
```

**截图后我读取 PNG，就等于看见了界面。** 因此：

- 视觉问题**我可以自己发现并修正**，不必等用户截图反馈
- **维语/阿拉伯语等 RTL 渲染验收**尤其关键 —— 连写、方向、标点位置
  这些"必须用眼睛看"的东西，我也能验
- 更进一步：**功能链路也能自动验**（把操作跑一遍再截图），见 §9
- 这条能力边界应明确告知用户（它直接改变协作分工）

> 反之也要清楚：**截图能看的是"像素"，看不到的是"路径"**。
> 界面显示出正确结果，不代表请求真的发到了该去的地方 —— 详见 §9.2。

---

## 2. 无头启动模拟器

```bash
export ANDROID_AVD_HOME="<AndroidDev>/avd"
"<ANDROID_HOME>/emulator/emulator.exe" -avd <AVD名> \
    -no-window -no-audio -no-boot-anim -gpu swiftshader_indirect \
    -cores 4 -memory 2048
```

| 参数 | 作用 |
|---|---|
| `-no-window` | **无窗口**：不弹窗打扰用户，适合自动化 |
| `-no-audio` | 省资源 |
| `-no-boot-anim` | 跳过开机动画，启动更快 |
| `-gpu swiftshader_indirect` | **软件渲染**：保证 Compose 界面可靠出图（硬件加速在无头环境下可能出不来画面） |
| `-cores N -memory M` | **显式指定**，否则模拟器可能按主机可用内存自行缩水，导致后续 SystemUI ANR |

> **关键**：`-gpu swiftshader_indirect` 是无头截图能成功的前提。
> 用默认 GPU 模式在 `-no-window` 下常得到黑屏或空图。

### ★ 启动前必须自愈：清掉残留的锁与进程

被中断的上一次运行会留下两样东西，**让模拟器完全起不来且不给明确报错**：

| 残留物 | 症状 | 处置 |
|---|---|---|
| `multiinstance.lock`（0 字节，在 `<AVD>.avd/` 下） | 模拟器静默退出，表现为"启动失败" | 确认无 qemu 进程后 `rm` 掉 |
| 残留的 `qemu-system-x86_64` 进程 | 端口被占 | `taskkill /F /IM qemu-system-x86_64.exe` |

```bash
"$ADB" kill-server
"$ADB" emu kill                     # 先尝试优雅关闭
sleep 2
if tasklist 2>/dev/null | grep -qiE "qemu"; then
  taskkill //F //IM qemu-system-x86_64.exe
  sleep 2
fi
# ★ 只有在确认无 qemu 进程后，删锁才是安全的
if [ -e "<AVD>.avd/multiinstance.lock" ] && ! tasklist 2>/dev/null | grep -qiE "qemu"; then
  rm -f "<AVD>.avd/multiinstance.lock"
fi
```

### ★ 模拟器必须与整条流程在同一个任务内

后台启动的模拟器**会随发起它的任务结束一起被回收**。
把它放在一个独立任务里启动、再到另一个任务里用 —— 第二个任务会看到"设备不存在"。

**做法**：把「起模拟器 → 装包 → 截图 → 收工」写进**同一个脚本**，一次跑完。

### 启动是异步的 —— 必须等，不能靠 sleep 猜

```bash
"$ADB" wait-for-device                      # 等设备连上
for i in $(seq 1 80); do
  b=$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r\n ')
  [ "$b" = "1" ] && break
  sleep 4
done
```

**实测约 24–36 秒**完成启动（冷启动）。轮询 `sys.boot_completed` 比固定 sleep 可靠得多。

---

## 3. 装机 → 启动 → 截图

```bash
ADB="<ANDROID_HOME>/platform-tools/adb.exe"

# 1) 安装（-r 覆盖安装）
"$ADB" install -r "<apk路径>"

# 2) 开机后先降压（见 §7.5.1，不做这步后面会被 SystemUI ANR 干扰）
for k in window_animation_scale transition_animation_scale animator_duration_scale; do
  "$ADB" shell settings put global $k 0
done

# 3) 强制停止旧进程后冷启动（避免看到的是旧版本的界面）
"$ADB" shell am force-stop <包名>
"$ADB" shell am start -n "<包名>/<Activity>"

# 4) ★ 轮询等焦点落到自家 App，再等首帧（不要固定 sleep）
for i in $(seq 1 18); do
  top=$("$ADB" shell dumpsys window 2>/dev/null | grep -m1 mCurrentFocus)
  printf '%s' "$top" | grep -q "<包名>" && { sleep 3; break; }
  sleep 2
done

# 5) ★ 截图 —— 用 exec-out 直接走 stdout，不落设备文件
"$ADB" exec-out screencap -p > /c/out/s1.png
```

### ★ 截图优先用 `exec-out`，而不是 `screencap` + `pull`

```bash
# ✅ 推荐：一步到位，不依赖设备侧可写目录
"$ADB" exec-out screencap -p > "C:/out/s1.png"

# ⚠️ 备选：需要设备侧目录可写（/sdcard 在清空 userdata 后可能未挂载）
"$ADB" shell screencap -p /sdcard/s1.png && "$ADB" pull /sdcard/s1.png "C:/out/s1.png"
```

`exec-out` 的两个好处：**不依赖 `/sdcard` 是否挂载**，
也**不产生设备侧临时文件**。若走备选路线且报错，先试
`adb shell mkdir -p /data/local/tmp && screencap /data/local/tmp/s1.png`。

### ★ 传给 `adb.exe` 的路径要用 Windows 形式

**`adb.exe` 是 Windows 程序，读不懂 Git Bash 的 `/c/...` 形式**。
混用会让 `pull` / `push` 报"找不到路径"，而 bash 自己的 `ls` 却能读到同一路径
（因为它读得懂 `/c/...`）。这一条同时适用于 `python.exe` 等任何 Windows 程序。

```bash
adb pull /data/local/tmp/ui.xml /c/out/ui.xml     # ❌ adb 读不懂 /c/...
adb pull /data/local/tmp/ui.xml C:/out/ui.xml     # ✅
```

### 中文输出路径同样是禁区

**中文路径会让 `adb pull` 失败**（与 Gradle 的中文路径问题是同一类编码根因）。
用一个纯 ASCII 的中间目录，拉回后再由 bash 复制到项目内的中文目录。

### 截图前先删旧文件

否则 `adb pull` 失败时旧的截图还在，会**误判为"新截图成功"**：

```bash
rm -f "$dst"
"$ADB" exec-out screencap -p > "$dst"
# 校验 PNG magic（8 byte 头），比只看文件大小可靠
[ "$(head -c 4 "$dst" | od -An -tx1 | tr -d ' ')" = "89504e47" ] && echo "OK" || echo "失败"
```

---

## 4. 崩溃与存活检查

```bash
# 崩溃缓冲区（只读 crash buffer，噪音小）
"$ADB" logcat -d -b crash

# 进程是否还活着（PID 非空即存活）
"$ADB" shell pidof <包名>
```

### ★ 判据要用 `FATAL EXCEPTION`，不要用应用名模糊匹配

**实测过的误报**：崩溃缓冲区里会有 **SystemUI 的 ANR 记录**，
而这类记录**会提到当时的前台应用名** —— 用 `grep <包名>` 会命中它，
于是报出一个**并不存在**的自家崩溃，让你去查一个假 bug。

```bash
# ❌ 会误报（ANR 记录里含前台应用名）
grep "<包名>" crash.log

# ✅ 只认真正的崩溃
grep -E "FATAL EXCEPTION|AndroidRuntime.*<包名>" crash.log
```

**三个检查配合看**：

- 进程存在 + 崩溃缓冲区无 `FATAL` → 正常
- 进程存在但截图是白屏/黑屏 → 渲染问题（换 `swiftshader_indirect` 重试）
- 进程不存在 → 启动即崩，看 `logcat -d | grep -E "FATAL|AndroidRuntime"`

> 光看"安装成功"不够 —— 装上了、启动了、**并且跑起来了**才是三件事。

---

## 5. 与界面交互：别盲点，用 UI 树取真实坐标

```bash
adb shell input tap <x> <y>          # 点击
adb shell input swipe x1 y1 x2 y2    # 滑动
adb shell input text "abc"           # 输入（★ 仅 ASCII，中文见 §5.3）
```

### 5.1 先拿 UI 树，再点 —— 不要按设计稿估坐标

早期做法是"截图 → 肉眼量坐标 → 点"，这有两个问题：估算本身有误差；
且**界面一旦随内容变化（换行、键盘弹出、状态条出现），估算值就失效**。

`uiautomator dump` 能直接给出每个控件的真实 `bounds`：

```bash
# 落到 /data/local/tmp —— 清空 userdata 后 /sdcard 可能未挂载、不可写
adb shell uiautomator dump /data/local/tmp/ui.xml
adb pull /data/local/tmp/ui.xml C:/out/ui.xml     # ★ 目标路径用 Windows 形式
```

`bounds="[x1,y1][x2,y2]"`，中心点即 `((x1+x2)/2, (y1+y2)/2)`。

### 5.2 ★ 识别"主操作按钮"的正确启发式

想自动点"页面里最主要的那个按钮"（如"翻译""保存"）时，
一个自然的想法是**取宽度最大的可点元素**。**这个启发式会错。**

实测某翻译页的可点元素：

| 元素 | bounds | 宽度 |
|---|---|---|
| **输入框（EditText）** | `[95,305][985,1305]` | **890** ← 最宽 |
| 主操作按钮 | `[53,1379][848,1526]` | 795 |
| 方向切换键 | `[880,1379][1027,1526]` | 147 |

输入框比主按钮**还宽**。按"最宽"取会把点击落在输入框上 ——
表现是**弹出键盘**、页面看起来"没反应"，而真正的按钮从未被点到。
排查时很容易误判成"按钮不可点"或"点击被吞"，实际上只是选错了目标。

**正确做法：先排除 `EditText`，再在剩余 clickable 节点里取最宽者。**

```python
for n in re.findall(r'<node[^>]*>', xml):
    if 'clickable="true"' not in n: continue
    if 'EditText' in n: continue            # ★ 关键：排除输入框
    b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', n)
    if not b: continue
    x1, y1, x2, y2 = map(int, b.groups())
    cands.append(((x1+x2)//2, (y1+y2)//2, x2-x1))
best = max(cands, key=lambda c: c[2]) if cands else None
```

> **通用教训**：用代理指标（宽度、位置、序号）识别元素时，
> 一定要先验证这个指标**在所有目标场景下都成立**。
> 这里"最宽 = 主按钮"只在没有输入框的页面上成立。

### 5.3 ★ `input text` 打不了中文 —— 用 base64 参数绕开

`adb shell input text` **只支持 ASCII**。界面是中文输入（或任何非 ASCII）时，
常规自动化路径直接断掉。

解法：给 App 加一个**仅 debug 生效**的参数入口，用 base64 传参 ——
base64 是纯 ASCII，与 shell、编码环境、系统 locale 全部无关：

```bash
adb shell am start -n com.example.app/.MainActivity \
  --es route text \
  --es input "b64:5L2g5aW977yM6K+35L2g5YiwMzAx5Y+3"     # ← base64 编码后的中文
```

App 侧解码（前缀之外的值按明文处理，便于手敲短文本调试）：

```kotlin
val debugInput = if (BuildConfig.DEBUG) {
    intent?.getStringExtra(EXTRA_INPUT)?.let(::decodeInput)
} else null      // release 包不接受外部指定内容

fun decodeInput(raw: String): String? = runCatching {
    if (raw.startsWith("b64:")) String(Base64.decode(raw.removePrefix("b64:"), Base64.DEFAULT))
    else raw
}.getOrNull()
```

**为什么这不是"作弊"**：它同时是真实的可测试性改进 ——
每页/每种初始状态从此可被独立拉起、独立断言，验收不再依赖易断的连续点击；
将来做「从通知或快捷方式直达某页」时，这条路径直接复用。
**用 `BuildConfig.DEBUG` 门控，release 包不受影响。**

### 5.4 点击后必须再截图确认

无论坐标从哪来，点完都要**再截一张图**核对结果。
`input tap` 永远可能落空 —— 尤其是被系统模态对话框挡住时（见 §7.5）。

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

## 7.5 ★ 两类"看不见的干扰"会让自动化全线失效

无头模拟器上，最难查的不是崩溃，而是**界面看着好好的、命令也全成功，
但操作就是没落到自家 App 上**。两种来源：

### 7.5.1 SystemUI 的 ANR 对话框（模态，吞掉后续所有点击）

无头 + 软件 GPU 下渲染负载高，**SystemUI 会持续 ANR**，弹出
「System UI isn't responding」对话框。它的三个特征让人极易误判：

- 报的是 **`System UI`，不是自家 App** —— 与本项目代码无关
- 它是**系统窗口且模态**，会吞掉其后**所有** `input tap`
- 截图里盖在自家界面上，看起来像"自己的页面卡住了"

**三重缓解（叠起来用）**：

```bash
# ① 降压：关掉三个动画。这是最有效的一招
adb shell settings put global window_animation_scale 0
adb shell settings put global transition_animation_scale 0
adb shell settings put global animator_duration_scale 0

# ② 每次操作前确认焦点在自家 App，不在就按 BACK 关掉对话框再拉起
adb shell dumpsys window | grep -m1 mCurrentFocus

# ③ 根治：给 App 加仅 debug 生效的页面/参数直启入口（见 §5.3），
#    彻底不依赖连续点击
```

### 7.5.2 系统选择器抢走前台，且杀不掉

"选文件/选相册/选图片"这类页面**进页即拉起系统选择器**（这是好设计：少让用户点一下）。
但系统选择器是**独立进程**，`am force-stop <自家包名>` **杀不掉它**。
它会一直占据前台，导致后续**所有** `am start` 都没有效果 ——
表现是"后面每一页的截图都是同一个界面"。

**解法：把"会拉起系统选择器"的页面排在验收序列的最后一位。**
（本项目实测：相册页排在中间时，其后的文本页、译文页全部验收失败。）

**通用判据**：截图内容与预期页面不符时，
先查焦点 `dumpsys window | grep mCurrentFocus` ——
如果焦点包名不是自家 App，那就是被别的窗口挡住了，**不是页面渲染问题**。

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

## 9. ★★ 链路验收：从"页面能渲染"到"功能真能跑通"

这是本阶段最容易自欺的一步。**UI 全绿 ≠ 功能可用**，而且——
更隐蔽的是 —— **"功能看起来成功了"也可能是假的**。

### 9.1 五个档位，不能用低档位的证据声称高档位的结论

| 说法 | 含义 | 需要的证据 |
|---|---|---|
| **编译通过** | 代码语法与类型正确 | `BUILD SUCCESSFUL` |
| **单元测试通过** | 纯逻辑正确 | 测试输出（N 用例全通过） |
| **装机运行** | 在真实 Android 运行时能启动 | `install` 成功 + 进程存活 + 无崩溃 |
| **界面验收** | 渲染符合设计 | **截图 + 逐项核对** |
| **功能可用** | 端到端能完成一件真实的事 | **真实数据端到端跑通 + 路径证据** |

### 9.2 ★ 关键：一次"成功"可能有三种路径，证据各不相同

带降级链、缓存、多实现架构的系统里，界面显示成功**不代表你验证了那一条链路**。

本项目实测到的真实案例：

> 结果页显示出了完全正确的目标语言译文 —— 看起来云端链路已通。
> 但细看折叠条，写的是**「从历史保存的」**。
> 也就是说请求**命中了缓存层，从未到达云端**。
> 如果把这次当成"云端链路已验证"写进报告，结论就是错的。

**三种路径的判据要分开**：

| 路径 | 界面特征 | 日志特征 | 验证到了什么 |
|---|---|---|---|
| **走了网络** | 无缓存标记 | 客户端网络层有记录（如 token 用量） | ✅ 真正的链路验证 |
| **命中缓存/本地** | 有"来自历史/缓存"之类标记 | 无网络层日志 | ⚠️ 只验证了降级链 |
| **真失败** | 有可理解的错误提示 | 有错误日志 | ✅ 验证了错误处理 |

所以判定脚本必须**三者都查**，只查"有没有网络日志"会把**缓存命中误报成失败**，
只查"界面有没有结果"会把**缓存命中误报成链路已通**。

### 9.3 ★ 持久化数据会让第二次跑与第一次不同

磁盘状态（缓存、历史、已授权、登录态）会跨运行保留，
于是同一脚本第二次跑的结果和第一次不一样 —— 这是最容易把验收变成"玄学"的原因。

两条纪律：

1. **验收脚本开头 `pm clear`**，回到零状态再跑：
   ```bash
   adb shell pm clear <包名>            # 会同时清掉权限，需重新 grant
   adb shell pm grant <包名> android.permission.CAMERA
   ```
2. **要跨过缓存的测试，必须换用全新输入**，不能复用同一份数据。
   （本项目断网降级测试第一次就因此失效：复用同一句原文 → 命中缓存 → 请求根本没走到云端 → "断网也能翻"看起来像通过，实则云端失败分支从未被触发。）

### 9.4 怎么让链路"可被自动化"

链路验收的难点是**没有真人输入**。几条实测有效的办法：

| 障碍 | 办法 |
|---|---|
| 打不了中文（`input text` 仅 ASCII） | 给 App 加 base64 参数入口（§5.3） |
| 连续点击会被系统对话框吞 | 改成**每页直启 + 参数注入**，不依赖点击（§5.3、§7.5） |
| 不知道点哪个按钮 | UI 树取真实坐标，排除 `EditText`（§5.1、§5.2） |
| 需要外部服务凭据 | 把凭据做成**构建期注入**（`local.properties` → `BuildConfig`），不进版本库 |
| 需要构造特殊前置状态 | 用参数入口直接构造，而不是"点若干次到达" |

> **共同思路**：与其对抗不稳定的环境，不如**让 App 本身可测**。
> 富余的调试入口不是权宜之计，而是让"每一页、每一种初始状态"都变成可断言的对象。

### 9.5 用可核对的证据收尾

功能验收的结论必须能被人独立复核。优先级从高到低：

1. **服务端/客户端的真实日志**（如 token 用量）—— 证明请求真的发出且被接受
2. **界面截图** —— 证明用户看到的是对的内容
3. **负面证据** —— 崩溃缓冲区为空、无错误日志

---

## 9b. 如何"验证"到什么程度：区分已验证与未验证

汇报时必须分清，不能把"编译通过"说成"功能可用"。
即使做到了 §9 的功能验收，也仍有未覆盖的部分，要主动说明：

| 状态 | 如实说法 |
|---|---|
| 只在模拟器软渲染下验过 | "未在真机（硬件 GPU）上验证，性能数据不可外推" |
| 只在 happy path 验过 | "错误分支未全部覆盖，已验 X 与 Y" |
| 依赖外部服务 | "受服务可用性影响，限流/超额分支未触发" |
| 界面文案是占位 | "文案为开发期占位，需母语者校对" |

**本项目的一个真实例子**（修好前）：UI 与导航都已装机验证 ✅，
但"点翻译按钮"这条路**没有端到端跑通** —— 因为没配 API 密钥，
所有翻译实现都被判定为不可用，用户拿到的是一个语焉不详的错误。
**这类"看着都好了但核心功能没通"的状态，必须如实说明，不能含糊过去。**

> **纪律**：主动区分"已验证"与"未验证"，并为已验证的部分交付**可复现的证据**
> （截图、日志、命令输出），而不是"我检查过代码，应该没问题"。

---

## 9c. ★ 状态指示必须与实际能力一致

界面上任何"能用 / 不能用"的指示，本身也是要验的功能 ——
**指示错了比没有指示更伤信任**。用户看到"不可用"而其实可用时，
他不会去尝试，只会认为 App 坏了。

本项目实测到的真实缺陷：**联网状态下首页显示「翻译需联网」，但翻译实际成功**。

根因是判定口径依赖了本地网络探测：

```
Android 判定"网络已验证"要打 connectivitycheck 主机
 → 该探测在部分网络环境下被阻断、必然超时
 → 系统只给 PARTIAL_CONNECTIVITY、永不给 VALIDATED
 → 判定为"离线" → 提示"需联网"，而网络其实完全可用
```

**两条通用结论**：

1. **判定"是否在线"要保守选择信号源**。
   优先"网络是否存在"（`NET_CAPABILITY_INTERNET`）而不是
   "系统是否已探测到外网可达"（`NET_CAPABILITY_VALIDATED`）——
   后者依赖一次可能被阻断的外部探测，在受限网络下会持续误报。
2. **★ 状态指示永远只做提示，不要 gate 功能。**
   本项目唯一的幸运之处是 `isOnline` 只用于显示状态点，
   没有任何地方拿它 `disabled` 按钮 —— 所以影响被限制在"提示不准"。
   **若当初写成 `if (!isOnline) disabled`，同样的根因会让核心功能
   在受限网络下完全不可用。**

> 验收时对状态指示要**做对照实验**：在"指示说不可用"的状态下，
> 实际发一次请求，看能不能成。**指示与事实不一致，就是缺陷。**

---

## 10. 一键脚本

`scripts/verify_loop.ps1` 把"装 → 启 → 截图 → 查崩溃"封装成一条命令：

```powershell
.\scripts\verify_loop.ps1 -Apk "<apk>" -Package "com.example.app" `
    -Activity ".MainActivity" -OutDir "E:\out" -Tap "250,830" -SettleSeconds 12
```

它依次完成：安装 → 强制停止 → 启动 → 等冷启动 → 首页截图 → （可选）点击 → 二次截图
→ 崩溃检查 → 进程存活检查，并把结果写成一份小报告。

> 覆盖的是 §3–§4（渲染验收）。**它是链路验收的起点，不是终点** ——
> 涉及网络、多实现降级、持久化状态的链路，需要按 §9 单独设计脚本。

---

## 11. 本阶段验收清单

**渲染验收（§3–§8）**

- [ ] 模拟器以 `-no-window -gpu swiftshader_indirect` 启动，**且与整条流程同一任务内**
- [ ] 启动前清理残留的 `multiinstance.lock`（确认无 qemu 进程后）
- [ ] 通过轮询 `sys.boot_completed` 确认启动完成（不是固定 sleep）
- [ ] 加载后**关闭三个动画**（降压，避免 SystemUI ANR）
- [ ] 安装成功（无 `INSTALL_FAILED_NO_MATCHING_ABIS`；ABI 已用 `apk_report.py` 核对）
- [ ] 启动前 `am force-stop`（避免看到旧版本界面）
- [ ] 截图用 `adb exec-out screencap -p > x.png`（不依赖设备侧文件）
- [ ] 截图前**轮询等焦点**落到自家 App，再等 3 秒取首帧
- [ ] **已读取截图并逐项核对** UI 验收清单（含 RTL 专项）
- [ ] 崩溃缓冲区检索 `FATAL EXCEPTION`（不用应用名模糊匹配）
- [ ] 进程存活
- [ ] "会拉起系统选择器"的页面**排在最后**

**链路验收（§9）**

- [ ] 已跑通**至少一条**真实业务链路（不是只有页面渲染）
- [ ] 已区分并记录这次成功走的是**哪条路径**（网络 / 缓存 / 本地）
- [ ] 有**服务端或客户端的真实日志**作为请求发出的证据
- [ ] 验收脚本开头 `pm clear`，保证从零状态开始
- [ ] 跨缓存的测试**换用了全新输入**
- [ ] 已验**失败分支**（断网/超时），且错误提示用户能理解、不崩溃不卡死
- [ ] 状态指示与实际能力做过**对照实验**（指示"不可用"时实际能否用）
- [ ] 已明确列出**仍未验证**的部分（真机 / 硬件加速 / 限流分支 / 占位文案）
- [ ] 若点击过界面 → 已二次截图确认结果
- [ ] 模拟器已**优雅关闭**；若曾强杀，已检查并清理 `ram.img`
- [ ] 汇报中已区分**已验证**与**未验证**，并给出可复现证据
