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

$password = Read-Host "Пароль пользователя $User (в файл не попадёт)"

switch ($Run) {
    "A"  { $extra = "" }
    "B"  { $extra = "/N$(Quote $User) /P$(Quote $password)" }
    "B2" { $extra = "/N$User /P$password" }
    "C"  { $extra = "/N$(Quote $User) /P$(Quote $password) /WA-" }
    "D"  { $extra = "/N$(Quote $User) /P$(Quote $password)" }
}
if ($Run -eq "D") {
    if (-not $FilePath) { Write-Host "Для D нужен -FilePath"; exit 1 }
    $target = "/IBConnectionString$(Quote "File=""$FilePath"";")"
} else {
    $target = "/IBName$(Quote $IbName)"
}
$arguments = "ENTERPRISE $target $extra /AppAutoCheckVersion /AppAutoCheckMode".Trim()
$shown = $arguments.Replace($password, "<пароль>")

$before = (Get-FileHash $ibases -Algorithm SHA256).Hash
Write-Host ""
Write-Host "Запуск $Run`:"
Write-Host "  `"$Exe`" $shown"
Write-Host ""
Start-Process -FilePath $Exe -ArgumentList $arguments
Start-Sleep -Seconds 6

$snapshot = Get-CimInstance Win32_Process -Filter "Name='1cv8.exe' OR Name='1cv8c.exe'" |
    Select-Object -ExpandProperty CommandLine
$snapshotShown = ($snapshot -join "`n").Replace($password, "<пароль>")
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
