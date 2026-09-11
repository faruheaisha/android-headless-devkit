<#
.SYNOPSIS
    Android 装机验收闭环：安装 → 启动 → 截图 → （可选）点击 → 再次截图 → 查崩溃。

.DESCRIPTION
    把 references/03-device-verification.md 里的流程封装成一条命令。
    截图先拉到 ASCII 暂存目录再复制到目标目录 —— 因为 adb pull 的目标路径
    含中文会失败，这是实测踩到过的坑。

    输出一份小报告，含：安装结果、进程存活、崩溃缓冲区、截图路径。

    ## 两条由实跑失败倒逼出来的健壮性设计（重要）
    1. **所有 adb 调用都有超时**。实测：设备中途消失时 adb 会**无限期挂起**
       （输出 "- waiting for device -"），脚本曾因此卡住 12 分钟。
    2. **adb 输出必须校验，不能只看"非空"**。实测：adb 的报错文本曾漏进 PID 变量，
       导致设备已消失却报"进程存活 OK"。现在 pidof 结果必须是数字才认。

.PARAMETER Apk
    要安装的 APK 路径（必填）。

.PARAMETER Package
    应用包名，如 com.example.app（必填）。

.PARAMETER Activity
    Activity 类名，默认 .MainActivity。相对名会自动补成 包名/相对名。

.PARAMETER OutDir
    截图与报告的存放目录，默认 .\_verify_out。可以是中文路径
    （截图会先经 ASCII 暂存再复制）。

.PARAMETER Tap
    可选。安装启动后要点击的坐标，形如 "250,830"。点击后会截第二张图。

.PARAMETER SettleSeconds
    启动后等待秒数，默认 12（冷启动留足时间）。

.PARAMETER AfterTapSeconds
    点击后等待秒数，默认 6。

.PARAMETER AdbTimeout
    单次 adb 调用的超时秒数，默认 30。防止设备消失时脚本无限挂起。

.PARAMETER Adb
    adb.exe 路径。默认取 $env:ADB 或 $env:ANDROID_HOME\platform-tools\adb.exe。

.PARAMETER NoInstall
    跳过安装步骤。

.PARAMETER NoLaunch
    跳过启动步骤。

.EXAMPLE
    .\scripts\verify_loop.ps1 -Apk "E:\proj\app\build\outputs\apk\debug\app-debug.apk" `
        -Package "com.example.app" -Activity ".MainActivity" -OutDir "E:\out"

.EXAMPLE
    # 首页截图 + 点第二个卡片进第二页并截图
    .\scripts\verify_loop.ps1 -Apk $apk -Package "com.example.app" -Tap "250,830"

.NOTES
    退出码：0 正常 / 1 前置条件不满足（无设备、APK 缺失）/ 2 adb 超时或设备中途消失
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Apk,
    [Parameter(Mandatory = $true)][string]$Package,
    [string]$Activity = ".MainActivity",
    [string]$OutDir = "",
    [string]$Tap = "",
    [int]$SettleSeconds = 12,
    [int]$AfterTapSeconds = 6,
    [int]$AdbTimeout = 30,
    [string]$Adb = "",
    [switch]$NoInstall,
    [switch]$NoLaunch
)

$ErrorActionPreference = "Continue"
$script:TimedOut = $false
$report = New-Object System.Collections.Generic.List[string]
function Add-Line($s) { $report.Add($s); Write-Output $s }

# ==================================================================== 函数
# ⚠ PowerShell 脚本自上而下执行，函数必须在**调用之前**定义。
#   首版把函数放在文件末尾，截图整段报 CommandNotFoundException
#   —— 实跑才暴露，静态看代码不会发现。故全部提前到这里。

function Save-Report($OutDir, $Report) {
    if (-not (Test-Path -LiteralPath $OutDir)) {
        New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    }
    $p = Join-Path $OutDir "verify_report.txt"
    [System.IO.File]::WriteAllText($p, ($Report -join "`n"),
        (New-Object System.Text.UTF8Encoding($false)))
    return $p
}

<#
    带超时地调用 adb。
    用 Start-Process 而非 & 调用，因为后者一旦设备消失会无限阻塞。
    返回 @{ Ok; Output; TimedOut }
#>
function Invoke-Adb {
    param(
        [string[]]$Arguments,
        [int]$TimeoutSec = 30
    )

    $tag  = [System.Guid]::NewGuid().ToString("N").Substring(0, 8)
    $oF   = Join-Path $env:TEMP "ahd_$tag.out"
    $eF   = Join-Path $env:TEMP "ahd_$tag.err"

    try {
        $p = Start-Process -FilePath $script:AdbExe -ArgumentList $Arguments `
                -NoNewWindow -PassThru `
                -RedirectStandardOutput $oF -RedirectStandardError $eF `
                -ErrorAction Stop

        $timedOut = $false
        try {
            Wait-Process -Id $p.Id -Timeout $TimeoutSec -ErrorAction Stop
        } catch {
            $timedOut = $true
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }

        $out = ""
        if (Test-Path -LiteralPath $oF) { $out += (Get-Content -LiteralPath $oF -Raw -ErrorAction SilentlyContinue) }
        if (Test-Path -LiteralPath $eF) { $out += (Get-Content -LiteralPath $eF -Raw -ErrorAction SilentlyContinue) }
        if ($null -eq $out) { $out = "" }

        return @{
            Ok       = (-not $timedOut)
            Output   = $out.Trim()
            TimedOut = $timedOut
        }
    } finally {
        Remove-Item -LiteralPath $oF, $eF -Force -ErrorAction SilentlyContinue
    }
}

<# 设备是否在线。不只看输出内容，还要看是否超时。 #>
function Test-DeviceOnline {
    $r = Invoke-Adb -Arguments @("devices") -TimeoutSec $script:AdbTimeout
    if ($r.TimedOut) { return $false }
    $online = ($r.Output -split "`n") | Where-Object { $_ -match "\sdevice$" }
    return [bool]$online
}

<#
    截图：adb screencap → 拉到 ASCII 暂存目录 → 复制到目标目录。
    目标目录可以是中文（adb pull 直接写中文路径会失败）。
#>
function Get-Screenshot {
    param([string]$RemoteName, [string]$OutName)

    $remote = "/sdcard/$RemoteName"
    $local  = Join-Path $script:AsciiTmp $RemoteName
    $final  = Join-Path $script:OutDir $OutName

    # 先删旧文件 —— 否则 adb pull 失败时旧图还在，会误判为"截图成功"
    Remove-Item -LiteralPath $local -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $final -Force -ErrorAction SilentlyContinue

    $r1 = Invoke-Adb -Arguments @("shell", "screencap", "-p", $remote) -TimeoutSec $script:AdbTimeout
    if ($r1.TimedOut) { return "✗ 截图超时（设备可能已消失）" }

    $r2 = Invoke-Adb -Arguments @("pull", $remote, $local) -TimeoutSec $script:AdbTimeout
    if ($r2.TimedOut) { return "✗ adb pull 超时（设备可能已消失）" }

    if (Test-Path -LiteralPath $local) {
        Copy-Item -LiteralPath $local -Destination $final -Force
        $kb = [math]::Round((Get-Item -LiteralPath $local).Length / 1KB, 1)
        return "OK  $final  ($kb KB)"
    }
    return "✗ 截图失败：$($r2.Output)"
}

# ==================================================================== 前置解析
if ([string]::IsNullOrWhiteSpace($OutDir)) { $OutDir = Join-Path (Get-Location).Path "_verify_out" }
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }

if ([string]::IsNullOrWhiteSpace($Adb)) {
    if ($env:ADB -and (Test-Path -LiteralPath $env:ADB)) {
        $Adb = $env:ADB
    } elseif ($env:ANDROID_HOME) {
        $Adb = Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
    } else {
        $Adb = "adb"
    }
}
$script:AdbExe = $Adb
$script:OutDir = $OutDir

if ($Activity.StartsWith(".")) { $ActivityFull = "$Package/$Activity" } else { $ActivityFull = $Activity }

# 截图暂存目录：必须是纯 ASCII，否则 adb pull 会失败
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$script:AsciiTmp = Join-Path $env:TEMP "ahd_shots\$stamp"
New-Item -ItemType Directory -Force -Path $script:AsciiTmp | Out-Null

Add-Line "=== 装机验收 ==="
Add-Line "  APK       $Apk"
Add-Line "  包名      $Package"
Add-Line "  Activity  $ActivityFull"
Add-Line "  输出目录  $OutDir"
Add-Line "  截图暂存  $($script:AsciiTmp)  (ASCII，绕开 adb pull 中文路径限制)"
Add-Line "  adb 超时  ${AdbTimeout}s/次"
Add-Line ""

# ==================================================================== 设备检查
Add-Line "=== 设备 ==="
$dev = Invoke-Adb -Arguments @("devices") -TimeoutSec $AdbTimeout
if ($dev.TimedOut) {
    Add-Line "  ✗ adb devices 超过 ${AdbTimeout}s 无响应 —— adb 服务可能已卡死。"
    Add-Line "    处置：Stop-Process -Name adb -Force   然后重试。"
    $p = Save-Report $OutDir $report
    Add-Line "  报告：$p"
    exit 2
}
$online = ($dev.Output -split "`n") | Where-Object { $_ -match "\sdevice$" }
if (-not $online) {
    Add-Line "  ✗ 没有在线设备。先启动模拟器或连接真机："
    Add-Line "    emulator -avd <名称> -no-window -no-audio -no-boot-anim -gpu swiftshader_indirect"
    Add-Line ""
    Add-Line $dev.Output
    $p = Save-Report $OutDir $report
    Add-Line "  报告：$p"
    exit 1
}
Add-Line ("  OK  " + (($online | ForEach-Object { $_.Trim() }) -join " | "))
Add-Line ""

# ==================================================================== 安装
if (-not $NoInstall) {
    Add-Line "=== 安装 ==="
    if (-not (Test-Path -LiteralPath $Apk)) {
        Add-Line "  ✗ APK 不存在：$Apk"
        $p = Save-Report $OutDir $report
        Add-Line "  报告：$p"
        exit 1
    }
    Add-Line ("  包体 {0} MB" -f [math]::Round((Get-Item -LiteralPath $Apk).Length / 1MB, 2))

    $ins = Invoke-Adb -Arguments @("install", "-r", "-t", $Apk) -TimeoutSec 180
    if ($ins.TimedOut) {
        Add-Line "  ✗ 安装超时（180s）—— 设备可能已消失"
        $p = Save-Report $OutDir $report
        exit 2
    }
    Add-Line "  $($ins.Output)"
    if ($ins.Output -match "INSTALL_FAILED_NO_MATCHING_ABIS") {
        Add-Line "  ✗ ABI 不匹配：APK 缺设备架构的原生库。"
        Add-Line "    模拟器是 x86_64，真机多为 arm64-v8a。用 apk_report.py 核对 lib/ 下的 ABI。"
    } elseif ($ins.Output -notmatch "Success") {
        Add-Line "  ⚠ 安装未返回 Success，请检查上面的输出。"
    }
    Add-Line ""
}

# ==================================================================== 启动
if (-not $NoLaunch) {
    Add-Line "=== 启动 ==="
    Invoke-Adb -Arguments @("shell", "am", "force-stop", $Package) -TimeoutSec $AdbTimeout | Out-Null
    Start-Sleep -Seconds 2

    $st = Invoke-Adb -Arguments @("shell", "am", "start", "-n", $ActivityFull) -TimeoutSec $AdbTimeout
    if ($st.TimedOut) {
        Add-Line "  ✗ 启动超时（设备可能已消失）"
        $p = Save-Report $OutDir $report
        exit 2
    }
    Add-Line "  $($st.Output)"
    Add-Line "  等待 $SettleSeconds 秒（冷启动）"
    Start-Sleep -Seconds $SettleSeconds
    Add-Line ""

    Add-Line "=== 截图 1（启动后）==="
    Add-Line "  $(Get-Screenshot -RemoteName "s1.png" -OutName "01_home.png")"

    if (-not [string]::IsNullOrWhiteSpace($Tap)) {
        Add-Line ""
        Add-Line "=== 点击 ($Tap) ==="
        $parts = $Tap -split ","
        if ($parts.Count -eq 2) {
            $tp = Invoke-Adb -Arguments @("shell", "input", "tap", $parts[0].Trim(), $parts[1].Trim()) -TimeoutSec $AdbTimeout
            if ($tp.TimedOut) {
                Add-Line "  ✗ 点击超时（设备可能已消失）"
                $p = Save-Report $OutDir $report
                exit 2
            }
            Add-Line "  已点击，等待 $AfterTapSeconds 秒"
            Start-Sleep -Seconds $AfterTapSeconds
            Add-Line "=== 截图 2（点击后）==="
            Add-Line "  $(Get-Screenshot -RemoteName "s2.png" -OutName "02_after_tap.png")"
        } else {
            Add-Line "  ⚠ -Tap 格式应为 `"x,y`"，已跳过"
        }
    }
    Add-Line ""
}

# ==================================================================== 崩溃与存活
Add-Line "=== 崩溃检查 ==="
$cr = Invoke-Adb -Arguments @("logcat", "-d", "-b", "crash", "-t", "15") -TimeoutSec $AdbTimeout
if ($cr.TimedOut) {
    Add-Line "  ✗ 超时（设备可能已消失）"
    $script:TimedOut = $true
} elseif ([string]::IsNullOrWhiteSpace($cr.Output)) {
    Add-Line "  OK 崩溃缓冲区为空"
} else {
    Add-Line "  ✗ 崩溃缓冲区非空："
    foreach ($c in ($cr.Output -split "`n")) {
        if ($c.Trim()) { Add-Line "    $($c.Trim())" }
    }
}

Add-Line ""
Add-Line "=== 进程存活 ==="
# ★ 这里必须校验输出格式：实测 adb 报错文本曾漏进变量，
#   导致设备已消失却报"进程存活 OK"。pidof 的结果必须是数字才算数。
$pi = Invoke-Adb -Arguments @("shell", "pidof", $Package) -TimeoutSec $AdbTimeout
if ($pi.TimedOut) {
    Add-Line "  ✗ 超时（设备可能已消失）"
    $script:TimedOut = $true
} elseif ($pi.Output -match "^\d+(\s+\d+)*$") {
    Add-Line "  OK 进程存活  PID=$($pi.Output)"
} else {
    $why = if ([string]::IsNullOrWhiteSpace($pi.Output)) { "pidof 无输出" } else { "pidof 输出非数字：$($pi.Output)" }
    Add-Line "  ✗ 进程不存在（$why）"
    Add-Line "    可能是启动即崩 → 看 crash buffer 与："
    Add-Line "    adb logcat -d | Select-String 'FATAL|AndroidRuntime'"
}

# ==================================================================== 结论
Add-Line ""
Add-Line "=== 下一步（必须做，不能跳）==="
Add-Line "  1. 打开上面的截图**用眼睛逐项核对** UI（含 RTL 专项：图标在右、文字右对齐、"
Add-Line "     连写无方框、返回箭头方向）→ references/03-device-verification.md §8"
Add-Line "  2. 汇报时区分「已验证」与「未验证」，别把编译通过说成功能可用"

$reportPath = Save-Report $OutDir $report
Add-Line "  报告：$reportPath"
Write-Output ""
Write-Output "报告已写入: $reportPath"

if ($script:TimedOut) { exit 2 }
exit 0
