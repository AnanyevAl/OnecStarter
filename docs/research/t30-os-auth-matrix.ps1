<#
Эксперимент T-30 / T-32: как ключ WA в ibases.v8i и ключи /WA+ /WA- командной строки
влияют на вход в базу, где пользователь Windows сопоставлен с пользователем ИБ.
Запускает заказчик на тестовой машине. Порядок подготовки — t30-os-auth-protocol.md.

Скрипт сам выставляет WA в секции тестовой базы перед запуском (резервная копия
ibases.v8i делается при первом запуске) и дописывает строку в t30-results.md.
Имя учётной записи Windows скрипт не пишет никуда — файл результатов идёт в репозиторий.

Примеры:
  .\t30-os-auth-matrix.ps1 -BinDir "C:\Program Files\1cv8\8.3.27.2214\bin" -IbName "Тест ОС" -Run A1
  .\t30-os-auth-matrix.ps1 -BinDir "C:\Program Files\1cv8\8.3.27.2214\bin" -IbName "Тест ОС" -Run B1 -Note "повтор после входа с сохранением"
  .\t30-os-auth-matrix.ps1 -IbName "Тест ОС" -ShowWa
  .\t30-os-auth-matrix.ps1 -Restore

Запуски (WA в файле / ключи / режим):
  A1  WA=1       —                   ENTERPRISE   контроль: вход по ОС без диалога
  A0  WA=0       —                   ENTERPRISE
  AX  нет ключа  —                   ENTERPRISE   главная гипотеза T-30
  B1  WA=1       /WA-                ENTERPRISE   нужен T-32
  B0  WA=0       /WA+                ENTERPRISE
  C1  WA=1       /WA- /N"<User>"     ENTERPRISE   подставится ли имя в диалог
  D0  WA=1       —                   DESIGNER     контроль для D1
  D1  WA=1       /WA-                DESIGNER
#>
param(
    [string] $BinDir = "",
    [string] $IbName = "",
    [ValidateSet("A1", "A0", "AX", "B1", "B0", "C1", "D0", "D1")] [string] $Run = "",
    [string] $User = "tester",
    [string] $Note = "",
    [switch] $ShowWa,
    [switch] $Restore
)

$ErrorActionPreference = "Stop"
$ibases = Join-Path $env:APPDATA "1C\1CEStart\ibases.v8i"
$backup = "$ibases.t30-backup"
$results = Join-Path $PSScriptRoot "t30-results.md"

function Quote([string] $value) { '"' + $value.Replace('"', '""') + '"' }

if ($Restore) {
    if (-not (Test-Path $backup)) { Write-Host "Резервной копии нет: $backup"; exit 1 }
    Copy-Item $backup $ibases -Force
    Remove-Item $backup
    Write-Host "ibases.v8i восстановлен из резервной копии, копия удалена."
    exit 0
}

if (-not $IbName) { Write-Host "Нужен -IbName"; exit 1 }

# --- Чтение и запись ibases.v8i без потерь: BOM и переводы строк — как были. ---

function Read-V8i {
    $bytes = [IO.File]::ReadAllBytes($ibases)
    $bom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    $offset = if ($bom) { 3 } else { 0 }
    $strict = New-Object System.Text.UTF8Encoding($false, $true)
    $text = $strict.GetString($bytes, $offset, $bytes.Length - $offset)
    $eol = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
    return @{ Bom = $bom; Eol = $eol; Lines = [Collections.Generic.List[string]]($text -split "\r?\n") }
}

function Write-V8i($doc) {
    $text = [string]::Join($doc.Eol, $doc.Lines)
    $body = (New-Object System.Text.UTF8Encoding($false)).GetBytes($text)
    $prefix = if ($doc.Bom) { [byte[]](0xEF, 0xBB, 0xBF) } else { [byte[]]@() }
    $tmp = "$ibases.t30-tmp"
    [IO.File]::WriteAllBytes($tmp, [byte[]]($prefix + $body))
    Move-Item $tmp $ibases -Force
}

function Find-Section($doc) {
    $header = "[$IbName]"
    $starts = @()
    for ($i = 0; $i -lt $doc.Lines.Count; $i++) {
        if ($doc.Lines[$i].Trim() -eq $header) { $starts += $i }
    }
    if ($starts.Count -ne 1) {
        Write-Host "Секция $header найдена $($starts.Count) раз(а), нужна ровно одна. Ничего не меняю."
        exit 1
    }
    $start = $starts[0]
    $end = $doc.Lines.Count
    for ($i = $start + 1; $i -lt $doc.Lines.Count; $i++) {
        if ($doc.Lines[$i].StartsWith("[")) { $end = $i; break }
    }
    return @{ Start = $start; End = $end }
}

function Get-Wa {
    $doc = Read-V8i
    $s = Find-Section $doc
    for ($i = $s.Start + 1; $i -lt $s.End; $i++) {
        if ($doc.Lines[$i] -match '^WA=(.*)$') { return $Matches[1] }
    }
    return $null
}

# $value = $null — убрать ключ. Существующая строка WA правится на месте,
# новая встаёт сразу после Connect= (или после заголовка, если Connect нет).
function Set-Wa($value) {
    $doc = Read-V8i
    $s = Find-Section $doc
    $done = $false
    for ($i = $s.End - 1; $i -gt $s.Start; $i--) {
        if ($doc.Lines[$i] -match '^WA=') {
            if ($null -ne $value -and -not $done) { $doc.Lines[$i] = "WA=$value"; $done = $true }
            else { $doc.Lines.RemoveAt($i) }
        }
    }
    if ($null -ne $value -and -not $done) {
        $s = Find-Section $doc
        $at = $s.Start + 1
        for ($i = $s.Start + 1; $i -lt $s.End; $i++) {
            if ($doc.Lines[$i].StartsWith("Connect=")) { $at = $i + 1; break }
        }
        $doc.Lines.Insert($at, "WA=$value")
    }
    Write-V8i $doc
}

function Show-Wa($wa) { if ($null -eq $wa) { "нет ключа" } else { "WA=$wa" } }

if ($ShowWa) {
    Write-Host "Секция [$IbName]: $(Show-Wa (Get-Wa))"
    exit 0
}

if (-not $BinDir -or -not $Run) { Write-Host "Нужны -BinDir и -Run (или -ShowWa / -Restore)"; exit 1 }

$plan = @{
    "A1" = @{ Wa = "1";   Keys = "";                          Mode = "ENTERPRISE" }
    "A0" = @{ Wa = "0";   Keys = "";                          Mode = "ENTERPRISE" }
    "AX" = @{ Wa = $null; Keys = "";                          Mode = "ENTERPRISE" }
    "B1" = @{ Wa = "1";   Keys = "/WA-";                      Mode = "ENTERPRISE" }
    "B0" = @{ Wa = "0";   Keys = "/WA+";                      Mode = "ENTERPRISE" }
    "C1" = @{ Wa = "1";   Keys = "/WA- /N$(Quote $User)";     Mode = "ENTERPRISE" }
    "D0" = @{ Wa = "1";   Keys = "";                          Mode = "DESIGNER" }
    "D1" = @{ Wa = "1";   Keys = "/WA-";                      Mode = "DESIGNER" }
}[$Run]

$exeName = if ($plan.Mode -eq "DESIGNER") { "1cv8.exe" } else { "1cv8c.exe" }
$exe = Join-Path $BinDir $exeName
if (-not (Test-Path $exe)) { Write-Host "Не найден $exe"; exit 1 }

$running = Get-Process -Name "1cv8", "1cv8c", "1cestart" -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "Запущены процессы 1С ($(($running | ForEach-Object Name) -join ', ')). Закройте их и повторите."
    exit 1
}

if (-not (Test-Path $backup)) {
    Copy-Item $ibases $backup
    Write-Host "Резервная копия: $backup  (вернуть: -Restore)"
}

Set-Wa $plan.Wa
$waBefore = Get-Wa
if ($waBefore -ne $plan.Wa) { Write-Host "WA не выставился как нужно ($(Show-Wa $waBefore)). Стоп."; exit 1 }

$arguments = "$($plan.Mode) /IBName$(Quote $IbName) $($plan.Keys) /AppAutoCheckVersion /AppAutoCheckMode" -replace '\s+', ' '
$before = (Get-FileHash $ibases -Algorithm SHA256).Hash

Write-Host ""
Write-Host "Запуск $Run, в файле: $(Show-Wa $waBefore)"
Write-Host "  `"$exe`" $arguments"
Write-Host ""
Start-Process -FilePath $exe -ArgumentList $arguments
Start-Sleep -Seconds 6

$dialog = Read-Host "Диалог входа появился? (y/n)"
$prefill = ""
if ($dialog -eq "y") {
    $prefill = Read-Host "Какое имя пользователя было в диалоге сразу (пусто — поле пустое)"
}
$who = Read-Host "Под каким пользователем 1С вошли («О программе»; ИМЯ ПОЛЬЗОВАТЕЛЯ 1С, не учётная запись Windows; пусто — не вошли)"
Read-Host "Закройте 1С и нажмите Enter"

$after = (Get-FileHash $ibases -Algorithm SHA256).Hash
$changed = if ($before -eq $after) { "нет" } else { "ДА, WA теперь: $(Show-Wa (Get-Wa))" }
$version = (Split-Path (Split-Path $BinDir -Parent) -Leaf)

$row = "| $Run | $(Show-Wa $waBefore) | ``$arguments`` | $dialog | $prefill | $who | $changed | $version | $Note |"
Add-Content -Path $results -Value $row -Encoding UTF8
Write-Host "Записано: $row"
