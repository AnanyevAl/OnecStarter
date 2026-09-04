<#
Эксперимент T-05.14 (спека v2.2, §1): работает ли /N /P при запуске по /IBName.
Запускает заказчик. Пароль в файл результатов НЕ пишется — заменяется на <пароль>.

Пример:
  .\t05-14-launch-matrix.ps1 -Exe "C:\Program Files\1cv8\8.3.25.1633\bin\1cv8c.exe" `
      -IbName "Тест пароля" -User tester -Run B
#>
param(
    [Parameter(Mandatory)] [string] $Exe,
    [Parameter(Mandatory)] [string] $IbName,
    [Parameter(Mandatory)] [string] $User,
    [Parameter(Mandatory)] [ValidateSet("A", "B", "B2", "C", "D")] [string] $Run,
    [string] $FilePath = ""   # только для D: каталог файловой базы
)

$ibases = Join-Path $env:APPDATA "1C\1CEStart\ibases.v8i"
$results = Join-Path $PSScriptRoot "t05-14-results.md"

function Quote([string] $value) { '"' + $value.Replace('"', '""') + '"' }

# Симметричная сборка вместо Replace() по готовой строке: $arguments и $shown
# строит одна и та же функция, различаясь только переданным секретом. Так
# показ/запись никогда не расходятся с реальным экранированием Quote() —
# в частности, если пароль содержит `"`, Quote() удваивает её (pa"ss -> pa""ss),
# и Replace(pa"ss, ...) по уже собранной строке такую двойную форму не находит,
# и настоящий пароль остаётся в строке. Symmetric build исключает это в принципе.
function Build-Arguments([string] $secret) {
    switch ($Run) {
        "A"  { $extra = "" }
        "B"  { $extra = "/N$(Quote $User) /P$(Quote $secret)" }
        "B2" { $extra = "/N$User /P$secret" }
        "C"  { $extra = "/N$(Quote $User) /P$(Quote $secret) /WA-" }
        "D"  { $extra = "/N$(Quote $User) /P$(Quote $secret)" }
    }
    if ($Run -eq "D") {
        if (-not $FilePath) { Write-Host "Для D нужен -FilePath"; exit 1 }
        $target = "/IBConnectionString$(Quote "File=""$FilePath"";")"
    } else {
        $target = "/IBName$(Quote $IbName)"
    }
    return "ENTERPRISE $target $extra /AppAutoCheckVersion /AppAutoCheckMode".Trim()
}

if ($Run -eq "A") {
    # A не передаёт учётные данные вовсе — спрашивать пароль незачем.
    $password = ""
} else {
    $password = Read-Host "Пароль пользователя $User (в файл не попадёт)"
    if (-not $password) {
        Write-Host "Для запуска $Run нужен пароль"
        exit 1
    }
}

$arguments = Build-Arguments $password
$shown = Build-Arguments "<пароль>"

$before = (Get-FileHash $ibases -Algorithm SHA256).Hash
Write-Host ""
Write-Host "Запуск $Run`:"
Write-Host "  `"$Exe`" $shown"
Write-Host ""
Start-Process -FilePath $Exe -ArgumentList $arguments
Start-Sleep -Seconds 6

$snapshot = Get-CimInstance Win32_Process -Filter "Name='1cv8.exe' OR Name='1cv8c.exe'" |
    Select-Object -ExpandProperty CommandLine
$snapshotShown = $snapshot -join "`n"
if ($password) {
    # WMI отдаёт командную строку так, как она реально легла в память процесса:
    # для B/C/D пароль внутри кавычек Quote() — в удвоенной форме (pa"ss ->
    # pa""ss); для B2 без кавычек — в исходной. Гасим сначала удвоенную форму,
    # потом исходную, иначе неэкранированный "хвост" останется в открытом виде.
    $doubled = $password.Replace('"', '""')
    $snapshotShown = $snapshotShown.Replace($doubled, "<пароль>").Replace($password, "<пароль>")
}
Write-Host "Win32_Process.CommandLine (пароль заменён):"
Write-Host $snapshotShown
Write-Host ""

$dialog = Read-Host "Диалог авторизации появился? (y/n)"
$who = Read-Host "Под кем вошли (заголовок окна / «О программе»; пусто если не вошли)"
Read-Host "Закройте клиент 1С и нажмите Enter"
$after = (Get-FileHash $ibases -Algorithm SHA256).Hash
$changed = if ($before -eq $after) { "нет" } else { "ДА" }

$row = "| $Run | ``$shown`` | $dialog | $who | $changed |"
Add-Content -Path $results -Value $row -Encoding UTF8
Write-Host "Записано: $row"
