<#
.SYNOPSIS
    一键设置 Android 无头构建所需的环境变量。

.DESCRIPTION
    设置 JAVA_HOME / ANDROID_HOME / ANDROID_SDK_ROOT / ANDROID_AVD_HOME /
    GRADLE_USER_HOME，默认清空可能残留的失效代理，并做几项快速体检
    （JDK 版本、adb 可用性、提交可用内存）。

    每次新开 shell 都要执行一次 —— PowerShell 的环境变量不跨会话保留。

.PARAMETER DevRoot
    工具链根目录，默认 E:\AndroidDev。子目录约定：
    jdk-17 / sdk / avd / gradle-home / gradle-8.9

.PARAMETER GradleBin
    显式指定 gradle.bat 路径。默认取 <DevRoot>\gradle-8.9\bin\gradle.bat。

.PARAMETER KeepProxy
    加这个开关则保留现有代理环境变量（默认会清空）。

.EXAMPLE
    . .\scripts\env.ps1
    . .\scripts\env.ps1 -DevRoot "D:\AndroidDev"
    . .\scripts\env.ps1 -DevRoot "D:\AndroidDev" -KeepProxy

.NOTES
    用点源（. 空格）执行才能在**当前会话**生效：
        . .\scripts\env.ps1
    直接运行（.\scripts\env.ps1）只会在子作用域生效，设完就没了。
#>
[CmdletBinding()]
param(
    [string]$DevRoot = "E:\AndroidDev",
    [string]$GradleBin = "",
    [switch]$KeepProxy
)

$ErrorActionPreference = "Continue"

# ---------------------------------------------------------------- 路径推导
$jdkPath     = Join-Path $DevRoot "jdk-17"
$sdkPath     = Join-Path $DevRoot "sdk"
$avdHome     = Join-Path $DevRoot "avd"
$gradleHome  = Join-Path $DevRoot "gradle-home"

if ([string]::IsNullOrWhiteSpace($GradleBin)) {
    $GradleBin = Join-Path $DevRoot "gradle-8.9\bin\gradle.bat"
}

# ---------------------------------------------------------------- 设置变量
$env:JAVA_HOME        = $jdkPath
$env:ANDROID_HOME     = $sdkPath
$env:ANDROID_SDK_ROOT = $sdkPath
$env:ANDROID_AVD_HOME = $avdHome
$env:GRADLE_USER_HOME = $gradleHome

# 便利变量（供构建/验收脚本引用）
$env:GRADLE_BIN = $GradleBin
$env:ADB        = Join-Path $sdkPath "platform-tools\adb.exe"

if (-not $KeepProxy) {
    # 这几项若残留指向已失效的代理，Gradle 会无法下载任何依赖，
    # 且报错信息通常不指向代理本身 —— 所以默认清空。
    $env:HTTP_PROXY  = ""
    $env:HTTPS_PROXY = ""
    $env:http_proxy  = ""
    $env:https_proxy = ""
}

# ---------------------------------------------------------------- 体检输出
$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("=== 已设置的环境变量 ===")
foreach ($name in @("JAVA_HOME","ANDROID_HOME","ANDROID_SDK_ROOT","ANDROID_AVD_HOME","GRADLE_USER_HOME")) {
    $lines.Add(("  {0,-20} {1}" -f $name, (Get-Item "env:$name" -ErrorAction SilentlyContinue).Value))
}
$proxyState = if ($KeepProxy) { "保留（未清空）" } else { "已清空" }
$lines.Add(("  代理变量            {0}" -f $proxyState))

$lines.Add("")
$lines.Add("=== 体检 ===")

# JDK
$javaExe = Join-Path $jdkPath "bin\java.exe"
if (Test-Path -LiteralPath $javaExe) {
    # java -version 把版本信息写到 stderr，且 PowerShell 会加 "java.exe :" 前缀 → 清掉
    $raw = (& $javaExe -version 2>&1 | Out-String)
    $v = ($raw -split "`n" | Where-Object { $_ -match "version" } | Select-Object -First 1)
    if ($v) { $v = $v.Trim() -replace "^.*?java\.exe\s*:\s*", "" }
    if (-not $v) { $v = ($raw -split "`n" | Select-Object -First 1).Trim() }
    $lines.Add("  JDK        OK   $v")
} else {
    $lines.Add("  JDK        缺失 $javaExe")
}

# adb
if (Test-Path -LiteralPath $env:ADB) {
    $lines.Add("  adb        OK   $env:ADB")
} else {
    $lines.Add("  adb        缺失 $env:ADB  （需装 platform-tools）")
}

# gradle
if (Test-Path -LiteralPath $GradleBin) {
    $lines.Add("  gradle     OK   $GradleBin")
} else {
    $lines.Add("  gradle     缺失 $GradleBin")
}

# AVD
if (Test-Path -LiteralPath $avdHome) {
    $avds = Get-ChildItem -LiteralPath $avdHome -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "*.avd" } |
            ForEach-Object { $_.Name -replace "\.avd$", "" }
    if ($avds) {
        $lines.Add("  AVD        OK   $($avds -join ', ')")
    } else {
        $lines.Add("  AVD        目录存在但无 AVD：$avdHome")
    }
} else {
    $lines.Add("  AVD        目录缺失 $avdHome")
}

# 提交可用内存 —— 这是最容易忽略、又最致命的一项
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
if ($os) {
    $commitAvailGB = [math]::Round($os.FreeVirtualMemory / 1MB, 2)
    $physAvailGB   = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
    $lines.Add("")
    $lines.Add("=== 内存 ===")
    $lines.Add(("  物理可用    {0}GB" -f $physAvailGB))
    $lines.Add(("  提交可用    {0}GB   <-- 构建真正受限于这一项" -f $commitAvailGB))
    if ($commitAvailGB -lt 2.5) {
        $lines.Add("  ⚠ 提交可用低于 2.5GB，构建可能因 JVM 原生内存分配失败而崩溃。")
        $lines.Add("    先退出云盘客户端（OneDrive 实测可单独提交十几 GB）、不用的浏览器。")
    } else {
        $lines.Add("  OK 提交内存充足")
    }
}

$lines.Add("")
$lines.Add("下一步：")
$lines.Add("  & `$env:GRADLE_BIN -p <项目> `":app:assembleDebug`" --no-daemon")
$lines.Add("  .\scripts\verify_loop.ps1 -Apk <apk> -Package <包名> -Activity .MainActivity")

Write-Output ($lines -join "`n")
