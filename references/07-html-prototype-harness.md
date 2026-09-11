# 附 · 用无头浏览器验证自己的 HTML 产出

**目标**：让"我写了一个 HTML"变成"我看过它渲染出来的样子，并且改掉了看到的问题"。

**验收标准**：每一屏都有截图，且截图是你**读过**的 —— 不是生成完就交出去。

---

## 1. 为什么需要这一步

### 1.1 同一个教训会重复两次

本项目里，"不实跑就发现不了"出现了两次，第二次尤其值得警惕：

| 场合 | 现象 |
|---|---|
| Android 界面 | 5 个 UI 缺陷（状态栏重叠、玻璃质感消失、卡片暗环、布局留白、返回键过小）**全部是装机截图后才发现的** |
| **自己写的交互原型 HTML** | 首页卡片组悬在上半部分、下方大片空白 —— **我犯了自己在 PRD 里刚批评过的同一个错误** |

第二行是这条工作流存在的根本理由：**写的时候看不出来，渲染出来一眼就看出来。**
所以凡产出 HTML，交付前必须渲染并读图。

### 1.2 典型会被渲染暴露的问题

- 内容堆在上半屏、下方大片空白（"看起来没做完"）
- 装饰元素压住正文 / 控件重叠
- 图标或图片容器缺显式尺寸 → 整块不显示或比例失衡
- 固定尺寸容器里的文字溢出被裁（标题被顶栏切掉半行）
- 绝对定位的覆盖层依赖父级 `display`，父级一隐藏它就永远不出来
- 窄屏/长中文文案下换行破版

---

## 2. 基本做法（Chrome headless）

```bash
CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"

"$CHROME" --headless --disable-gpu --hide-scrollbars --no-sandbox \
  --user-data-dir="E:/tmp/cp1" \
  --virtual-time-budget=3000 \
  --window-size=1620,1010 \
  --screenshot="E:/out/01_home.png" \
  "file:///E:/proj/page.html"
```

| 参数 | 作用 |
|---|---|
| `--headless` | 无窗口 |
| `--disable-gpu` | 无头环境更稳 |
| `--hide-scrollbars` | 截图不带滚动条，观感干净 |
| `--user-data-dir` | **必须给（见 §3.1）** |
| `--virtual-time-budget=3000` | 给 JS 与动画 3 秒虚拟时间；有 `setTimeout` 的状态需给足 |
| `--window-size` | 布局视口，按目标比例设 |
| `--screenshot` | 输出路径（**正斜杠，见 §3.2**） |

---

## 3. 三个实跑踩到的坑

### 3.1 ★ 连续启动必须各给一个 `--user-data-dir`

**现象**：单独跑一张成功；**放进 for 循环后只有第一张生成，其余静默失败**（无报错、无输出、无文件）。

**根因**：Chrome 争抢默认的 user-data-dir，后来的实例发现目录被占用就直接退出。

**解法**：每次调用给一个独立的 `--user-data-dir`。

```bash
i=0
for spec in "01_home:" "02_page:?p=detail"; do
  name="${spec%%:*}"; q="${spec#*:}"; i=$((i+1))
  "$CHROME" --headless ... --user-data-dir="E:/tmp/cp$i" \
    --screenshot="E:/out/$name.png" "file:///E:/proj/page.html$q" >/dev/null 2>&1
done
rm -rf E:/tmp/cp*
```

> **注意**：`--user-data-dir` 必须是 **Windows 风格路径**（`E:/tmp/cp1`）。
> 传 Git Bash 风格（`/e/tmp/cp1`）Chrome 认不出来，会静默失败。

### 3.2 ★ 在 bash 里用正斜杠写 `--screenshot` 路径

**现象**：循环里所有截图都"成功"，但**目录里一个文件都没有**；仔细看输出，文件名是字面量 `proto$name.png`。

**根因**：双引号里写 `"E:\\out\\$name.png"`，bash 把 `\\$` 解释成字面反斜杠 + `$`，
`$name` 不再展开 → 全都写进同一个带 `$` 的名字里。

**解法**：**统一用正斜杠**（Chrome 接受，bash 也不会误解变量）：

```bash
--screenshot="E:/out/$name.png"      # ✅ 变量正确展开
```

> 排查手法：**不要对循环里的失败抑制输出**。先手写两轮看真实报错，
> 再回到循环——本坑就是靠"单独跑成功、循环为 0"这个对比定位的。

### 3.3 中文路径 → 先复制到 ASCII 路径

`file://` 下的中文路径需要 URL 编码，容易出现"有的能开有的开不了"。
最省事的做法是**先 cp 到纯 ASCII 路径**再截：

```bash
cp "E:/中文目录/proto.html" /e/tmp/proto.html
BASE="file:///E:/tmp/proto.html"
```

---

## 4. ★ 给产出加"深链"，让逐屏自检成为可能

如果一屏是交互式原型（多页面切换），**给它加一个查询参数入口**：

```js
const QS = new URLSearchParams(location.search);
if (QS.get('p')) go(QS.get('p'));        // ?p=detail 直接打开某屏
if (QS.get('lang')) lang = QS.get('lang');
```

两个收益：

1. **可逐屏截图** —— 否则无头浏览器只能截到初始页，内部状态永远看不到
2. **评审可分享** —— 把 `?p=confirm` 这个链接直接甩给评审，对方一眼看到那一屏

配合批量脚本即可一次性验证全部页面：

```bash
for spec in "01_home:" "02_camera:?p=camera" "03_confirm:?p=confirm"; do
  name="${spec%%:*}"; q="${spec#*:}"
  # ...截图
done
```

---

## 5. 交互原型中特别容易犯的两类错

### 5.1 覆盖层（弹层/全屏模式）被父级隐藏

**现象**：点"全屏展示"，屏幕全白。

**根因**：实现成了 `display:none` 的页面切换，而全屏覆盖层嵌在某个页面内部。
切换时该页面被隐藏，覆盖层自然也不显示；而它自己又不在页面列表里，
于是"没有任何页面是 on" → 白屏。

**解法**：把覆盖层登记到一个"宿主页"映射里，切换时让宿主页保持可见：

```js
const OVERLAY_HOST = { handover:'result' };     // 覆盖层 → 它的宿主页
function go(p){
  const host = OVERLAY_HOST[p] || p;
  pages.forEach(s => s.classList.toggle('on', s.dataset.p === host));
  overlay.classList.toggle('on', p === 'handover');
}
```

### 5.2 内部动作切换链路，导致侧栏步骤指示器错位

**现象**：在 A 链路里点了个按钮跳到 B 链路的页面，侧栏的"交互顺序"仍显示 A 链路的步骤，
当前步高亮找不到位置。

**解法**：内部动作若跨越了链路边界，**同时切换 flow 并同步按钮高亮**：

```js
if (pg.dataset.p === 'paste') { flow = 'paste'; syncFlowBtns(); }
```

---

## 6. 自检清单

- [ ] 每一屏都有截图，且**逐张读过**（不是生成完就交）
- [ ] 循环截图时每轮给了独立 `--user-data-dir`，且是 Windows 风格路径
- [ ] `--screenshot` 路径用正斜杠，变量能正确展开（检查文件名有没有残留 `$`）
- [ ] 中文路径已先复制到 ASCII 路径
- [ ] 有交互状态的产出已加深链（`?p=`），能逐屏截图
- [ ] 覆盖层类界面已登记宿主页，不会白屏
- [ ] 发现的问题**已修并重新渲染确认**（不是只记下来）
- [ ] 对照第 1.2 节的清单逐项检查过（留白 / 重叠 / 尺寸 / 裁切）

---

## 7. 顺带一条纪律

渲染验证的产出**不要直接交付**。改完必须**再渲染一次确认** ——
本项目的设置页第一版分区标题被顶栏裁掉半行，改完 padding 后重截才确认修好。
"我改了"和"改对了"之间，隔着一次截图。
