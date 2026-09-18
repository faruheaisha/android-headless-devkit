# 运行期复盘：相机、裁剪、文档解析与“无法翻译”

本篇把一次真实 Android Compose 应用的运行期故障复盘成可迁移的验收方法。它不是某个业务项目的修复说明，而是给任何需要“拍照/裁剪 → OCR → 翻译”和“本地 PDF/DOCX → 分块处理”的应用使用的案例章。

## 0. 先把结论分层

一次检查至少要分成五档，不能把“能编译”写成“功能可用”：

| 档位 | 证明什么 | 最低证据 |
|---|---|---|
| 构建 | 工程能被工具链编译 | `BUILD SUCCESSFUL` 日志、APK 路径 |
| 单测 | 纯逻辑和边界成立 | 测试数量、失败数、日志 |
| 装机 | APK 能安装并启动 | `adb install`、进程 PID、启动截图 |
| 渲染 | 页面和控件画对了 | 截图 + UI 树 + 设备型号/API |
| 链路 | 输入真的走到输出 | 阶段日志、样本 ID、输出文件/截图；注明网络/缓存/本地路径 |

本篇所有“已验证”都必须带设备和样本；没有物理设备或真实服务端时，写“未验证”，不能用“应该可以”替代。

## 1. 基线环境：先消除非业务变量

Windows 无 IDE 场景的可复现基线：

```powershell
$env:JAVA_HOME = '<DevRoot>\\jdk-17'
$env:ANDROID_HOME = '<DevRoot>\\sdk'
$env:ANDROID_SDK_ROOT = '<DevRoot>\\sdk'
$env:GRADLE_USER_HOME = '<GradleHome>'
$env:HTTP_PROXY = ''; $env:HTTPS_PROXY = ''
$env:http_proxy = ''; $env:https_proxy = ''
& '<DevRoot>\\gradle-8.9\\bin\\gradle.bat' -p '<ASCII-project-link>' :app:assembleDebug --no-daemon
```

中文项目路径不要直接传给 `gradle.bat`。建立 ASCII junction，只把它当构建入口；源文件仍留在原位置。构建日志必须落盘，避免长任务被会话回收后只剩一句“daemon disappeared”。

设备侧固定动作：

```bash
adb wait-for-device
adb shell settings put global window_animation_scale 0
adb shell settings put global transition_animation_scale 0
adb shell settings put global animator_duration_scale 0
adb shell pm clear <包名>
adb logcat -c
```

`pm clear` 是清除缓存、历史、授权状态等验收污染的硬门；要测试“跨缓存”的路径，必须换一份全新的输入。

## 2. 相机：强退不是“权限提示没弹出来”这么简单

### 2.1 典型症状和正确判据

症状：点“拍照”后应用直接退回桌面，或者黑屏数秒后进程死亡。

不要用“截图还在”判断没有崩溃。正确判据是目标进程的崩溃缓冲区：

```bash
adb logcat -d -b crash > camera-crash.txt
grep -nE 'FATAL EXCEPTION|AndroidRuntime|Process: <包名>' camera-crash.txt
```

SystemUI 的 `isn't responding` 对话框属于无头软件 GPU 的环境噪声；只有目标包的 `FATAL EXCEPTION`、native tombstone 或目标进程死亡才算应用崩溃。截图与 `camera-crash.txt` 必须成对归档。

### 2.2 最小安全路径

相机页面应当有四个明确状态：`请求权限`、`准备中`、`可拍摄`、`不可用/回退相册`。绑定 CameraX 时：

1. 先确认 `CAMERA` 权限已授予；拒绝或永久拒绝都不能继续绑定。
2. 等 `ProcessCameraProvider` 返回后再绑定生命周期；不要在 Compose 重组期间重复绑定。
3. 每次绑定前 `unbindAll()`，并在离开页面的 `DisposableEffect` 中解绑。
4. 捕获 provider、selector、bind 及 `ImageCapture` 的异常，把状态切到“相机暂时不可用，可从相册选择”，不能让异常穿过 Compose。
5. 模拟器没有真实摄像头时仍要能进入页面；预览黑屏是环境限制，不是成功拍摄证据。

CameraX 依赖要锁在项目的单一版本目录中。一个已实测的样例组合是 `androidx.camera:*:1.5.3`；许可证为 Apache-2.0。版本号只是候选基线，升级后必须重新跑相机回归，不得只看编译。

### 2.3 必须覆盖的相机矩阵

| 场景 | 通过标准 | 证据 |
|---|---|---|
| 已授权、模拟器无摄像头 | 页面不崩，显示回退提示 | 页面截图 + 无 `FATAL EXCEPTION` |
| 首次未授权 | 出现系统权限框或解释页 | 权限前后截图 |
| 永久拒绝 | 有设置入口或相册回退 | UI 树节点 + 点击后截图 |
| 快门成功 | 产生可读的本地 URI/文件 | 文件大小、校验和、日志 |
| 快门异常 | 用户可见错误，可返回 | 错误日志 + 页面截图 |
| 物理真机 | 真实预览和快门成功 | 真机型号、系统版本、原图 |

无头模拟器只能证明页面和异常回退，不能证明物理 Camera HAL、自动对焦或真实成像质量。

## 3. 裁剪：不要再维护一套手势坐标系统

### 3.1 为什么“缩小后拖不动”很常见

自绘蓝色裁剪框通常同时承担了图片缩放、平移、四角调整和完成按钮命中。常见缺陷有：

- `pointerInput` 把当前 selection 作为 key，拖动更新状态后协程被重启，手势看起来像卡住；
- 图片显示坐标、裁剪框坐标、原图像素坐标混用，缩放后位移被 clamp 回原值；
- 点击“递给对方看”页面时，正文滚动手势被误判为退出手势；
- 拖动命中的是覆盖层而不是可调整的 handle，UI 看起来可拖、实际没有状态变化。

优先采用维护中的开源 View 组件，把手势和边界处理交给组件；Compose 只负责生命周期和结果回传。一个已验证过的候选是 CanHub Android Image Cropper：`com.vanniktech:android-image-cropper:4.7.0`，上游 tag commit `b54e71f1d0b6b935baefd81df192af487fff14d9`，Apache-2.0。引入时必须在项目的 `NOTICE`/依赖清单登记制品、版本、commit 和许可证。

### 3.2 Compose 接入规则

`AndroidView` 只做三件事：设置源图、设置初始裁剪框、监听完成/取消。不要在 Compose 的每次状态变化里重新创建 View 或覆盖 selection。结果回调后把“原图 URI、裁剪图 URI、原图尺寸、裁剪矩形、旋转角”持久化，后续 OCR 和译图不能重新猜坐标。

“递给对方看”是内容阅读页，不是裁剪页：

- 正文区域允许上下滚动和内部点击；点击正文或拖动不退出；
- 退出只有固定的“完成”按钮和系统返回键；
- 禁止用全屏 `pointerInput` 把任意抬手事件解释为退出；
- 自动化验证必须覆盖“滚动到底 → 点击正文 → 系统返回”和“点完成”两条不同出口。

### 3.3 裁剪回归用例

每次升级裁剪库或修改布局都跑同一组用例，并保存四张截图：

1. 进入裁剪页：框与图片边界对齐；
2. 缩小两次：框确实变小，图片仍可见；
3. 拖动中心：框位置发生变化，不能只改变触摸指针；
4. 拖动角点：宽高变化且四角仍在图片范围内。

截图后再取 UI 树，确认完成按钮仍可点；不要只看命令返回码。真两指 pinch 在无头模拟器上通常未验证，报告中必须单列。

## 4. 文档解析：本地、流式、可恢复

### 4.1 输入边界

文件选择使用 `ACTION_OPEN_DOCUMENT`/DocumentsUI，取得 `content://` URI 后立即：

1. 校验扩展名、MIME、可读性和大小预算；
2. 复制到应用私有目录，使用临时文件写入后原子 rename；
3. 保存 `sourceUri`、文件大小、SHA-256 和解析任务 ID；
4. 解析过程按块产生事件，禁止 `readBytes().toString()` 或把整个文档拼成一个 `String`；
5. 每个块有幂等的 `jobId + blockIndex`，成功后 checkpoint，取消/重启可恢复，失败可重试。

“几 MB 到几十 MB”不能靠一个拍脑袋的数字放行。至少同时限制：原始文件字节数、ZIP entry 数、单 entry 解压字节数、压缩比、页数、单页渲染像素和总任务时长。超限必须给出可理解的错误，不能静默截断。

### 4.2 DOCX：Android SAX 的兼容陷阱

轻量主线应读取 OOXML ZIP 中的 `word/document.xml`，用 SAX/XmlPullParser 按事件输出段落、表格和图片占位，不把 XML DOM 全部载入内存。POI 可作为质量对照器，但不应未经包体、内存和许可证门禁直接进入运行时。

Android Expat 对 SAX feature 的支持不完整；在某些 API 33 运行时，直接调用 `SAXParserFactory.isXIncludeAware = false` 会抛 `UnsupportedOperationException`，报错包含 `Unknown version "0.0"`。安全 feature 要逐项 `runCatching`：能设置就设置，平台不支持就跳过；XXE 防护不能因此取消，必须再用无外部实体/DTD 样本实跑。

DOCX 最低真值集：普通段落、长段落、标题、表格在段落前、图片占位、损坏 ZIP、DTD/XXE、ZIP bomb/超 entry 数。每个样本记录块顺序、字符数、解析耗时、峰值 PSS、失败类型。

### 4.3 PDF：文本层和扫描页是两条路径

PDF 文本层可用 PDFBox Android（样例版本 `2.0.27.0`，Apache-2.0）抽取；逐页预览/扫描页 raster 使用系统 `PdfRenderer`，OCR 作为明确的回退路径。不要把“PDF 能打开”当成“文字可翻译”：必须分别验证文本 PDF、扫描 PDF、旋转页、加密 PDF、损坏 PDF 和大页数文件。

一次 API 33 软件 GPU 样例中，小 PDF 的 parse benchmark 返回 `format=PDF`、`blocks=1`；该耗时只属于该设备和样本，不可外推到真机。扫描 PDF 的 OCR 回退必须在日志里明确标记，避免把空文本误报成“翻译失败”。

### 4.4 DocumentsUI 的真路径验收

自动把文件推到 `/sdcard` 再直接调用内部解析，不等于用户真的会用。至少要有一条人工/脚本路径：打开选择器 → Recent/Downloads → 选 DOCX/PDF → 回到 App → 显示文件名、格式、解析进度和结果。系统选择器是独立进程，验收序列应放在最后；`am force-stop <包名>` 杀不掉 DocumentsUI。

## 5. “无法翻译”：先分类，再修

页面显示“无法翻译”至少可能来自四条完全不同的路径：

| 类别 | 需要的证据 | 最小修复 |
|---|---|---|
| 本地代理未启动/地址错误 | endpoint、连接异常、设备路由 | debug 用可配置本机地址；启动前健康检查；release 只接受 HTTPS |
| HTTP/协议错误 | 状态码、响应体摘要、request ID | 分层错误映射，禁止把所有错误折成一句“失败” |
| 200 但内容为空 | `finish_reason`、content 长度、原始响应结构 | 空内容单独报错；翻译任务关闭不必要的 reasoning；保留 request ID |
| 命中缓存/历史 | cache hit 标记、无网络日志 | 报告写“缓存链路已验证”，不能写“云端链路已验证” |

状态指示只提示，不得 gate 核心按钮。`NET_CAPABILITY_VALIDATED` 依赖外部探测，在受限网络可能长期为 false；应用仍可能访问可用的内网/代理。验收时分别记录系统层、事实层、应用层网络状态。

链路证据推荐三连：

```text
TRANSLATE_PREPARED job=<id> inputSha=<sha> blocks=<n>
TRANSLATE_REQUESTED job=<id> endpointClass=<local|https> block=<i>
TRANSLATE_COMPLETED job=<id> path=<network|cache|fallback> chars=<n>
```

日志不得写 API key、完整用户文本或个人文件内容。没有公开可访问的翻译服务时，翻译成功只能标为“未验证”，不能用旧 APK、缓存或静态 UI 截图替代。

## 6. 一轮可复用的验证顺序

```text
环境体检
  → 清代理/确认 JDK SDK Gradle
  → ASCII 项目入口构建
  → 安装 debug APK，pm clear
  → 直启 camera，验证权限/回退/快门
  → crop：缩小 ×2、中心拖、角点拖、完成
  → 结果页：原图/译图/文字对照与 block 几何
  → DocumentsUI：DOCX、PDF 真选择
  → benchmark：解析顺序、字符数、PSS、耗时
  → 翻译：新输入，确认 network/cache/fallback 路径
  → 断网/代理关闭：错误文案、取消、重试、恢复
  → 清 logcat，查 FATAL EXCEPTION，归档证据
```

每个节点都要写设备、API、APK SHA-256、样本 ID、命令、日志文件和截图路径。模拟器通过不代表真机通过；真机未接入时，最终报告必须保留“物理 Camera HAL、双指 pinch、厂商权限策略、真实网络性能：未验证”。

## 7. 依赖与许可证记录模板

| 能力 | 候选/实测制品 | 版本/commit | 许可证 | 合入门 |
|---|---|---|---|---|
| 相机 | AndroidX CameraX | `1.5.3`（样例基线） | Apache-2.0 | 相机异常回退 + 真机快门 |
| 裁剪 | CanHub Android Image Cropper | `4.7.0` / `b54e71f…` | Apache-2.0 | 四张几何回归截图 |
| PDF 文本 | PDFBox Android | `2.0.27.0`（样例基线） | Apache-2.0 | 文本/加密/损坏/扫描矩阵 |
| PDF 页图 | Android `PdfRenderer` | 设备平台 API | Android SDK license | 逐页关闭资源、无泄漏 |
| DOCX 对照 | Apache POI | 仅 benchmark | Apache-2.0 | 不得未经体积/内存门禁进 runtime |

版本、commit、许可证和 NOTICE 必须随应用仓库提交；本 devkit 只记录方法，不把第三方二进制或应用源码带进来。

## 8. 未验证项的写法

推荐使用下面这种明确措辞：

- **已验证（API 33 软件 GPU 模拟器）**：页面进入不崩、裁剪四种手势状态变化、DOCX/PDF 样本解析、错误状态可见。
- **未验证（物理真机）**：真实 Camera HAL、自动对焦、双指 pinch 手感、厂商 ROM 权限与后台策略。
- **未验证（真实公网服务）**：翻译请求是否到达供应商、供应商计费和公网时延。
- **不属于缺陷的环境限制**：无头软件 GPU 的 SystemUI ANR、无摄像头预览黑屏、无目标语言系统语音包。

这四类状态必须在 Evidence Pack 中分开，不能用一张“功能成功”截图覆盖全部结论。
