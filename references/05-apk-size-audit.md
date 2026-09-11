# 阶段 5 · APK 体积审计与死依赖剔除

**目标**：说清包体由什么构成、找出死重量、确认 release 达标。

**验收标准**：给出 **debug 与 release 两个实测体积数字**（不是估算）+ 构成占比 +
已剔除的死重量清单。

> 本文件与独立 skill `android-apk-size-audit` 同源；本仓库自带可执行脚本
> `scripts/apk_report.py`（只依赖 Python 标准库）。

---

## 1. 回报数字：实测 vs 估算

**本项目实测**（同一份代码，两种构建类型）：

| 产物 | 大小 | 构成 |
|---|---|---|
| `app-debug.apk` | **65.26MB** | 18 个 dex（不混淆）+ arm64-v8a & x86_64 双 ABI |
| `app-release-unsigned.apk` | **2.80MB** | 单 dex 2.30MB（R8 后）+ 仅 arm64-v8a |

**R8 对 dex 的压缩量级：64.32MB → 2.30MB（约 1/28）。**
若 R8 后 dex 降幅远小于此，检查是否有大库被反射整体 `keep` 住。

---

## 2. 第一步：拆解体积构成

不要凭直觉。本项目一开始的直觉是"应用代码写多了"，
实际拆开发现**一个原生库占了发布包 82%**。

```powershell
python scripts\apk_report.py "<apk>"
```

或直接写（Python 标准库即可，**不要用 PowerShell 的 `Add-Type` / `System.IO.Compression`，
在某些环境会被安全策略拦截**）：

```python
import zipfile, os, collections
apk = r'path/to/app.apk'
sz = os.path.getsize(apk)
z = zipfile.ZipFile(apk)
items = [(i.filename, i.file_size, i.compress_size) for i in z.infolist()]

g = collections.defaultdict(int)
for n, u, c in items:
    if n.startswith('lib/'):        k = 'lib/' + n.split('/')[1]
    elif n.startswith('classes') and n.endswith('.dex'): k = 'dex'
    elif n.startswith('res/'):      k = 'res/'
    elif n.startswith('assets/'):   k = 'assets/'
    else:                           k = '其他'
    g[k] += c
for k, v in sorted(g.items(), key=lambda x: -x[1]):
    print(f'  {k:<24}{v/1048576:>9.2f}MB  {v/sz*100:>5.1f}%')
```

### 判读要点

| 现象 | 含义 | 处置 |
|---|---|---|
| `lib/*` 占比高 | 原生库是主因 | 查是否必要、ABI 是否精简（见 §3） |
| 出现多个 ABI | release 带了无关架构 | `abiFilters` 只留 `arm64-v8a` |
| `dex` 大（release） | R8 未生效或被反射 keep 住 | 查 `-keep` 规则是否过宽（→ [04](04-dependency-versions.md) §6） |
| `dex` 大（debug） | 正常（不混淆） | 不必优化 |
| `res/` 达 MB 级 | 图片未压缩 | 开 `shrinkResources` |

---

## 3. ★ 第二步：找死依赖（本项目最大一笔收益）

### 症状

发布包里有一个 **16.76MB 的 `libonnxruntime.so`**，占 20.54MB 发布包的 **82%**。

### 核实

```powershell
# 1) 全工程搜它被声明在哪
Select-String -Path (Get-ChildItem -Recurse -Filter build.gradle.kts).FullName -Pattern "onnxruntime"

# 2) 全工程搜它被代码引用在哪
Select-String -Path (Get-ChildItem -Recurse -Filter *.kt).FullName -Pattern "ai\.onnx|onnxruntime"
```

**结果**：**只在一处 `build.gradle.kts` 里被声明，全工程零处代码引用它** ——
该模块连一个 `.kt` 文件都没有（属后续里程碑范围）。

### 处置（保守而可逆）

```kotlin
dependencies {
    implementation(libs.kotlinx.coroutines.core)

    // ---- ONNX Runtime 推理引擎：M2 实现 OCR 时启用 ----
    // 实测：这一行会让发布包多出 17.63MB（libonnxruntime.so 16.76MB +
    // libonnxruntime4j_jni.so 0.87MB），占 20.54MB 发布包的 82%。
    // 而当前本模块还没有任何代码引用它 → 属于纯增量负担，
    // 与"轻量"目标直接冲突，故先不装载。实现 OCR 时解除注释即可。
    // implementation(libs.onnxruntime.android)
}
```

**要点**：

- **只注释依赖行 + 写明恢复条件与量化理由**，不删模块、不删版本目录条目
- 保留架构完整性 → 将来复活的成本是"解除一行注释"
- 注释里**写清实测数字**，让后来者不需要重新量一遍就能判断

### 结果

**release APK：20.54MB → 2.80MB（缩小 7.3 倍）。**

> **这是"声明了 ≠ 用到了"最典型的案例。**
> 依赖树看不出这件事 —— 必须逐个大依赖去源码里核对引用。

---

## 4. ★ 第三步：诊断"陈旧空洞"（体积读数虚高的头号原因）

### 症状

改完依赖重建后，**debug 包体积没有变化**，且读数与内容对不上：

```
文件大小              103.55MB
所有条目 compress 合计  65.13MB
差值                   38.42MB   ← 不合理
```

### 诊断

```python
tot = sum(c for _, _, c in items)
print(f'文件 {sz/1048576:.2f}MB / 内容 {tot/1048576:.2f}MB / 差 {(sz-tot)/1048576:.2f}MB')

# 定位空隙位置
infos = sorted(z.infolist(), key=lambda x: x.header_offset)
prev_end, gaps = 0, []
for i in infos:
    if i.header_offset > prev_end:
        gaps.append((i.header_offset - prev_end, prev_end, i.filename))
    prev_end = max(prev_end, i.header_offset + 30 + len(i.filename.encode())
                   + len(i.extra) + i.compress_size)
for g, off, name in sorted(gaps, reverse=True)[:5]:
    print(f'  空隙 {g/1048576:>8.3f}MB @ {off/1048576:>7.2f}MB 之后是 {name[:50]}')
```

实测输出：**在 64.38MB 处有一段 37.97MB 的空洞**（位于 `AndroidManifest.xml` 之前），
是 **Gradle 增量打包未截断旧文件**留下的旧 dex 残留。

### 关键：确认空洞里没有"活数据"

```python
with open(apk, 'rb') as f: data = f.read()
for kw in [b'onnxruntime', b'ai/onnxruntime']:
    print(kw, data.count(kw))     # 实测 0 次 → 确认无残留依赖
```

实测该空洞**非全零但熵极低**（字节值只分布在 0–9），属旧 dex 数据，**不含被删依赖的代码**。

**结论**：空洞**不影响运行**（zip 中心目录按声明读取，运行时跳过空洞），
但会让**体积读数虚高，污染优化决策**。

### 解法

删掉 APK 文件后**只重跑打包任务**（实测 **2 分钟**，不必 `clean` 触发全量重编）：

```powershell
Remove-Item -LiteralPath "<...>\app-debug.apk" -Force
gradle -p <项目> :app:assembleDebug --no-daemon
# → 65.26MB ✅
```

> **仅在 debug 包上观察到**（增量打包所致），release 少见。

---

## 5. ABI 精简

```python
abis = sorted({n.split('/')[1] for n, c in items if n.startswith('lib/')})
print('ABI:', abis)
```

| 构建类型 | 应含 ABI | 理由 |
|---|---|---|
| debug | `arm64-v8a` + `x86_64` | 模拟器是 x86_64，缺了会 `INSTALL_FAILED_NO_MATCHING_ABIS` |
| release | 仅 `arm64-v8a` | 现代机型均为 64 位，去掉其他显著减体积 |

配置写法见 [03-device-verification.md](03-device-verification.md) §7。

---

## 6. dex 与 R8 核对

```python
dexn = sum(1 for n, c in items if n.startswith('classes') and n.endswith('.dex'))
print('dex 文件数:', dexn)
```

| 构建 | 预期 | 实测 |
|---|---|---|
| debug | 多个 dex（不混淆，方法数超限自动分包） | **18 个** |
| release | **单 dex** | **1 个**（2.30MB） |

release 若仍是多 dex → R8 没生效，或被反射陷阱整体 keep 住。

---

## 7. 目标核对

以"轻量"为目标的项目可参考本项目设定的阈值：

| 指标 | 目标 | 实测 | 结论 |
|---|---|---|---|
| APK（release） | ≤ 80MB | **2.80MB** | 余量极大 |
| 冷启动 | ≤ 1.5s | 未实测 | 待验 |
| 内存占用 | ≤ 400MB | 未实测 | 待验 |

> **注意**：目标阈值应与"实际用户机型底线"挂钩
> （本项目按"中端 8GB 机型"设定），不要照抄数字。

---

## 8. 本阶段验收清单

- [ ] 已按分类量出体积占比，找到占比最大的两项
- [ ] 已核对"文件大小 vs 条目 compress 合计"，差值 >1MB 已查空洞
- [ ] 已确认每个 `lib/` 下的 ABI 都是必要的
- [ ] **已对每个大依赖确认源码里有引用**（无引用即死重量）
- [ ] 死依赖处置方式为"注释 + 写明恢复条件"，架构完整性保留
- [ ] 已在剔除后**重建并真机复验无回归**（不是只看编译通过）
- [ ] 已实跑 `assembleRelease` 并看到 `BUILD SUCCESSFUL` + R8 无 `Missing class`
- [ ] 已给出 debug / release **两个实测数字**，并核对目标阈值
