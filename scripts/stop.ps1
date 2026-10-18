# 停止本地五链投研台（只杀 8000 端口的监听进程）
$conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
  $pidToStop = ($conn | Select-Object -First 1).OwningProcess
  Stop-Process -Id $pidToStop -Force
  Write-Host "已停止进程 $pidToStop (:8000)" -ForegroundColor Yellow
} else {
  Write-Host ":8000 没有监听进程"
}
