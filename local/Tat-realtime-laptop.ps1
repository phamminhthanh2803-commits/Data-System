# Tat-realtime-laptop.ps1 — CHUYEN GIAO bo thu real-time DNSE tu laptop sang GitHub Actions (12/10/2026).
# DNSE chi cho 10 ket noi WebSocket / user -> laptop (task "Realtime DNSE" 08:40 T2-T6) va cloud (realtime-sang/chieu.yml)
# KHONG duoc chay cung luc: ben vao sau bi MAX_CONNECTIONS_EXCEEDED (cloud log ro, thu 3 lan cach 60 s roi thoat ma 0).
#
# Khi nao chay: sau khi 2 job cloud "Realtime SANG" + "Realtime CHIEU" chay XANH tron 1 ngay (du kien 13/10/2026) va app
# hien "live 1 phut (cloud)" -> chay file nay (khong can admin) de tat task laptop:
#     powershell -ExecutionPolicy Bypass -File D:\cloud-deploy\local\Tat-realtime-laptop.ps1
# Chi DISABLE task (khong xoa). Tien trinh dnse_stream.py dang chay (neu co) KHONG bi dung — tu thoat sau 15:10 hoac
# them -Kill de dung ngay. Bat lai (quay ve laptop):  ... Tat-realtime-laptop.ps1 -Enable
param([switch]$Enable, [switch]$Kill)

$task = 'Realtime DNSE'
$t = Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
if (-not $t) { Write-Host "Khong thay task '$task' (da xoa?)"; exit 0 }

if ($Enable) {
    Enable-ScheduledTask -TaskName $task | Out-Null
    Write-Host "DA BAT lai task '$task' (08:40 T2-T6). Nho TAT 2 workflow cloud (Actions -> Realtime SANG/CHIEU -> ... -> Disable workflow) de khong tranh ket noi."
    exit 0
}

Disable-ScheduledTask -TaskName $task | Out-Null
$st = (Get-ScheduledTask -TaskName $task).State
Write-Host "DA TAT task '$task' (State=$st). Tu mai bo thu chay tren GitHub Actions (08:25-11:40, 12:50-15:15 gio VN), app doc Drive."

$procs = Get-CimInstance Win32_Process -Filter "name like 'python%'" | Where-Object { $_.CommandLine -like '*dnse_stream.py*' }
if ($procs) {
    $pids = ($procs | ForEach-Object { $_.ProcessId }) -join ', '
    if ($Kill) {
        $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Write-Host "Da dung tien trinh dnse_stream.py dang chay (PID $pids)."
    } else {
        Write-Host "Luu y: dnse_stream.py van dang chay (PID $pids) - de no tu thoat sau 15:10, hoac chay lai voi -Kill de dung ngay."
    }
}
Write-Host "Kiem tra: schtasks /Query /TN `"$task`"  |  app: Kho du lieu -> 'Nguon cloud' / thanh LIVE 'live 1 phut (cloud)'."
