# Сборка поставки. Порядок обязателен: smoke идёт ДО артефактов —
# сборка, не прошедшая smoke, не существует (CLAUDE.md, «Сборка»).
param([switch]$SkipInstaller)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$version = uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Host "== OneCStarter $version =="

# Запуск из Git Bash подмешивает в PATH C:\Program Files\Git\mingw64\bin, и
# PyInstaller уносит оттуда чужие libcrypto-3-x64.dll/libssl-3-x64.dll
# (RC 2.0.0, 30.08.2026: +6 МБ в _internal рядом со штатными libcrypto-3.dll/
# libssl-3.dll из DLLs Python). Зависимости ищем без каталогов Git.
$env:PATH = ($env:PATH -split ";" | Where-Object { $_ -notmatch "\\Git\\(mingw64|usr)\\bin" }) -join ";"

uv run pyinstaller build/onecstarter.spec --noconfirm --distpath dist --workpath build/pyi
if ($LASTEXITCODE -ne 0) { Write-Host "PyInstaller: отказ"; exit 1 }

uv run python build/smoke.py dist/OneCStarter
if ($LASTEXITCODE -ne 0) { Write-Host "smoke: отказ"; exit 1 }

$zip = "dist/OneCStarter-$version-portable.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "dist/OneCStarter" -DestinationPath $zip
Write-Host ("zip: {0:N1} МБ" -f ((Get-Item $zip).Length / 1MB))

if (-not $SkipInstaller) {
    $iscc = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { Write-Host "Inno Setup 6 не найден (ISCC.exe)"; exit 1 }
    & $iscc "/DAppVersion=$version" /Odist build/installer.iss
    if ($LASTEXITCODE -ne 0) { Write-Host "ISCC: отказ"; exit 1 }
    $setup = "dist/OneCStarter-$version-setup.exe"
    Write-Host ("setup: {0:N1} МБ" -f ((Get-Item $setup).Length / 1MB))
}

$size = (Get-ChildItem dist/OneCStarter -Recurse | Measure-Object Length -Sum).Sum
Write-Host ("dist: {0:N1} МБ. Готово." -f ($size / 1MB))
