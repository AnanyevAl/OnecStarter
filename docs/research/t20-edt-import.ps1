# T-20 / Э12: 1cedtcli.exe в режимах -file и -command на тестовых рабочих областях.
# Запуск: powershell -ExecutionPolicy Bypass -File docs/research/t20-edt-import.ps1 -Step 1
# Обёртка та же, что у OneCStarter (wrap_console_utf8): chcp 65001 в той же консоли до CLI.
param([Parameter(Mandatory = $true)][int]$Step)

$Cli = 'C:\Program Files\1C\1CE\components\1c-edt-2026.1.2+2-x86_64\1cedtcli.exe'
$Jdk = 'C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin'
$Base = 'E:\tmp\edt-test'
$Imp = "$Base\imp"
$Tail = "-vm `"$Jdk`" --launcher.appendVmargs -vmargs -Xmx8192m -DnativeFormBufferedLayoutRender=true -Djava.library.path="

function Invoke-Cli([string]$Workspace, [string]$Mode, [string]$Out) {
    $line = "chcp 65001 >nul & `"$Cli`" -data `"$Workspace`" $Mode $Tail > `"$Out`" 2>&1"
    $started = Get-Date
    $proc = Start-Process -FilePath "$env:SystemRoot\System32\cmd.exe" `
        -ArgumentList "/d /v:off /c `"$line`"" -Wait -PassThru -NoNewWindow
    $seconds = [int]((Get-Date) - $started).TotalSeconds
    "шаг: код $($proc.ExitCode), $seconds с, вывод: $Out"
    $registry = Join-Path $Workspace '.metadata\.plugins\org.eclipse.core.resources\.projects'
    if (Test-Path $registry) { 'реестр: ' + ((Get-ChildItem $registry -Name) -join ', ') }
    else { 'реестр: каталога нет' }
}

switch ($Step) {
    1 { Invoke-Cli "$Base\ws-imp1" "-file `"$Imp\s1.cli`"" "$Imp\s1.out" }
    2 { Invoke-Cli "$Base\ws-imp2" "-file `"$Imp\s2.cli`"" "$Imp\s2.out" }
    3 { Invoke-Cli "$Base\ws-imp3" "-command `"import --project ['E:/tmp/edt-test/dev_tools' 'E:/tmp/edt-test/imp/консоль копия']`"" "$Imp\s3.out" }
    4 { Invoke-Cli 'E:\edt\тест_2026' "-command `"import --project 'E:/tmp/edt-test/dev_tools'`"" "$Imp\s4.out" }
    default { throw "шаг 1..4" }
}
