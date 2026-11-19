# 把 AutoDL 上合并好的 HF 目录转成 GGUF 并量化。
#
# 前置：
#   1. 下载 llama.cpp Windows 预编译包（llama-bXXXX-bin-win-cpu-x64.zip 或 vulkan 版），
#      解压到任意目录，把该目录传给 -LlamaCppDir。
#   2. pip install -r quant/requirements-quant.txt
#   3. 本脚本要在普通 PowerShell 里跑，不要用 IDE 沙箱：Ollama 的模型目录
#      (%USERPROFILE%\.ollama) 对沙箱是只读的。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File quant\convert_and_quantize.ps1 `
#       -MergedDir E:\downloads\jrvs-orbiter-merged -LlamaCppDir E:\tools\llama.cpp
param(
    [Parameter(Mandatory = $true)][string]$MergedDir,
    [Parameter(Mandatory = $true)][string]$LlamaCppDir,
    [string]$OutDir = "",
    [string]$QuantizeExe = "",
    [string]$Python = "py",
    [string]$ModelName = "jrvs-orbiter"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $OutDir) { $OutDir = Join-Path $root "quant\out" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$convert = Join-Path $LlamaCppDir "convert_hf_to_gguf.py"
if (-not (Test-Path $convert)) { throw "找不到 $convert，-LlamaCppDir 应指向 llama.cpp 源码目录" }

if (-not $QuantizeExe) {
    $candidates = @(
        (Join-Path $LlamaCppDir "llama-quantize.exe"),
        (Join-Path $LlamaCppDir "llama-quantize"),
        (Join-Path $LlamaCppDir "build\bin\Release\llama-quantize.exe"),
        (Join-Path $LlamaCppDir "build\bin\llama-quantize.exe")
    )
    $QuantizeExe = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $QuantizeExe -or -not (Test-Path $QuantizeExe)) {
    throw "找不到 llama-quantize 可执行文件，请用 -QuantizeExe 显式指定"
}

$f16 = Join-Path $OutDir "jrvs-orbiter-f16.gguf"
$q8 = Join-Path $OutDir "jrvs-orbiter-Q8_0.gguf"
$q4 = Join-Path $OutDir "jrvs-orbiter-Q4_K_M.gguf"

Write-Host "[1/3] HF -> F16 GGUF"
& $Python $convert $MergedDir --outtype f16 --outfile $f16
if ($LASTEXITCODE -ne 0) { throw "convert_hf_to_gguf 失败" }

Write-Host "[2/3] F16 -> Q8_0"
& $QuantizeExe $f16 $q8 Q8_0
if ($LASTEXITCODE -ne 0) { throw "Q8_0 量化失败" }

Write-Host "[3/3] F16 -> Q4_K_M"
& $QuantizeExe $f16 $q4 Q4_K_M
if ($LASTEXITCODE -ne 0) { throw "Q4_K_M 量化失败" }

$modelfile = Join-Path $OutDir "Modelfile.generated"
& $Python (Join-Path $root "tools\render_modelfile.py") --base $q4 --out $modelfile
if ($LASTEXITCODE -ne 0) { throw "Modelfile 渲染失败" }

Write-Host ""
Write-Host "产物："
Get-ChildItem $f16, $q8, $q4 | ForEach-Object { "  {0}  {1:N2} GB" -f $_.Name, ($_.Length / 1GB) }
Write-Host ""
Write-Host "注册到 Ollama（在普通 PowerShell 中执行）："
Write-Host "  ollama create $ModelName -f `"$modelfile`""
