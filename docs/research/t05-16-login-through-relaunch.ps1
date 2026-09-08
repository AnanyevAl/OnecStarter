<#
Замер T-05.16 № 13: проходит ли вход по /N и /P, когда платформа переигрывает
версию и переносит эти ключи в порождённый ею процесс, удваивая /N.

Что уже измерено (№ 9, 08.09.2026, на ЛОЖНЫХ учётных данных): платформа
переносит /N и /P в свою командную строку, /N в ней удваивается. Успешность
входа при этом проверить было нельзя — данные были заведомо неверные, и
появившееся окно входа одинаково согласуется с «ключи приняты и отвергнуты»
и с «ключи проигнорированы».

Этот замер закрывает разницу. На нём стоит работоспособность авторизации v2.2
для веб- и серверных баз.

ПАРОЛЬ НИКУДА НЕ ЗАПИСЫВАЕТСЯ: спрашивается интерактивно, в выводе заменяется
на <пароль>, в файлы не пишется. Образец — t05-15-launch-matrix.ps1.

Запускает заказчик. Скрипт временно дописывает секцию в живой
%APPDATA%\1C\1CEStart\ibases.v8i и восстанавливает файл побайтово.

Пример:
  .\t05-16-login-through-relaunch.ps1 -Srvr "localhost" -Ref "INITKZ-1373" -User "Иванов"
#>
param(
    [Parameter(Mandatory)] [string] $Srvr,
    [Parameter(Mandatory)] [string] $Ref,
    [Parameter(Mandatory)] [string] $User,
    # Версия, заведомо НЕ совпадающая с версией кластера, — чтобы платформа
    # гарантированно переиграла выбор и перенесла ключи в новый процесс.
    [string] $WrongVersion = "8.3.27.2214",
    [string] $Exe = "C:\Program Files\1cv8\8.3.27.2214\bin\1cv8c.exe"
)

$ErrorActionPreference = "Stop"
$ib = Join-Path $env:APPDATA "1C\1CEStart\ibases.v8i"
$name = "t0516-login-probe"

function Quote([string] $value) { '"' + $value.Replace('"', '""') + '"' }

# Симметричная сборка: показываемая и настоящая строки строятся одной функцией,
# различаясь только секретом. Так вывод никогда не разойдётся с реальным
# экранированием — Replace() по готовой строке промахнулся бы на пароле
# с кавычкой.
function Build([string] $secret) {
    return "ENTERPRISE /IBName$(Quote $name) /N$(Quote $User) /P$(Quote $secret) /AppAutoCheckVersion"
}

Write-Host "Кластер должен работать, база $Ref должна быть на нём." -ForegroundColor Cyan
Write-Host "Версия в секции: $WrongVersion — заведомо не версия кластера." -ForegroundColor Cyan
Write-Host ""
$password = Read-Host "Пароль пользователя $User (в файл не попадёт)"
if (-not $password) { Write-Host "Без пароля замер бессмыслен."; exit 1 }

$orig = [System.IO.File]::ReadAllBytes($ib)
$before = (Get-FileHash $ib -Algorithm SHA256).Hash
Write-Host "ibases.v8i: $($orig.Length) байт, sha $($before.Substring(0,16))"

$section = "[$name]`r`nConnect=Srvr=`"$Srvr`";Ref=`"$Ref`";`r`nID=$([guid]::NewGuid())`r`n" +
           "OrderInList=999990`r`nFolder=/`r`nOrderInTree=99990`r`nExternal=0`r`n" +
           "App=ThinClient`r`nVersion=$WrongVersion`r`n"
[System.IO.File]::WriteAllBytes($ib, $orig + [System.Text.Encoding]::UTF8.GetBytes($section))

try {
    $existing = @(Get-CimInstance Win32_Process -Filter "Name LIKE '1cv8%'" | Select-Object -ExpandProperty ProcessId)
    Write-Host ""
    Write-Host "Запуск:" -ForegroundColor Yellow
    Write-Host "  `"$Exe`" $(Build '<пароль>')"
    Write-Host ""

    $proc = Start-Process -FilePath $Exe -ArgumentList (Build $password) -PassThru
    $ourPid = $proc.Id

    $relaunched = $null
    for ($i = 1; $i -le 20; $i++) {
        Start-Sleep -Seconds 3
        $alive = Get-Process -Id $ourPid -ErrorAction SilentlyContinue
        $others = @(Get-CimInstance Win32_Process -Filter "Name LIKE '1cv8%'" |
                    Where-Object { $existing -notcontains $_.ProcessId -and $_.ProcessId -ne $ourPid })
        $state = if ($alive) { "жив" } else { "завершился" }
        $titles = $others | ForEach-Object {
            $t = (Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue).MainWindowTitle
            "$(($_.ExecutablePath -split '\\')[-3]) [$t]"
        }
        Write-Host "t=$($i*3)s: наш процесс $state; поднято платформой: $($titles -join ' | ')"
        if ($others.Count -gt 0) { $relaunched = $others[0] }
        # Окно входа или рабочее окно — оба означают, что исход определился.
        if ($titles -match 'Доступ к информационной базе') { break }
        if ($titles -match '1С:Предприятие') { break }
    }

    Write-Host ""
    Write-Host "=== ЧТО СНЯТО ===" -ForegroundColor Green
    if ($relaunched) {
        $shown = $relaunched.CommandLine.Replace($password, '<пароль>')
        Write-Host "Командная строка процесса, поднятого платформой:"
        Write-Host "  $shown"
        Write-Host ""
        Write-Host "Ключей /N в ней: $(([regex]::Matches($relaunched.CommandLine, '/N')).Count)"
        Write-Host "Ключей /P в ней: $(([regex]::Matches($relaunched.CommandLine, '/P')).Count)"
    } else {
        Write-Host "Платформа новый процесс не подняла — версия совпала? Проверь -WrongVersion."
    }
    Write-Host ""
    Write-Host "ГЛАВНЫЙ ВОПРОС: было ли окно «Доступ к информационной базе»?" -ForegroundColor Yellow
    Write-Host "  окно есть  -> вход по /N //P НЕ прошёл, авторизация v2.2 на этих базах не работает"
    Write-Host "  окна нет, открылась база -> вход прошёл, метка [Д] снимается"
    Write-Host ""
    Write-Host "Посмотри на экран и ответь. Клиент оставлен запущенным намеренно."
}
finally {
    [System.IO.File]::WriteAllBytes($ib, $orig)
    $after = (Get-FileHash $ib -Algorithm SHA256).Hash
    Write-Host ""
    Write-Host "ibases.v8i восстановлен: sha $($after.Substring(0,16)) — совпадает: $($after -eq $before)" -ForegroundColor Cyan
    Write-Host "Запущенный клиент закрой сам, когда посмотришь." -ForegroundColor Cyan
}
