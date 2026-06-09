# deploy.ps1 — 로컬 + Railway 1:1 동기화 배포
# 사용: ./deploy.ps1 또는 ./deploy.ps1 "커밋 메시지"

param([string]$msg = "")

Set-Location "C:\Users\alsdn\OneDrive\바탕 화면\fmkorea_web"

$status = git status --porcelain
if (-not $status) {
    Write-Host "변경사항 없음 — Railway만 재배포합니다"
    railway up --detach
    exit
}

if (-not $msg) {
    $msg = "update: $(Get-Date -Format 'MM-dd HH:mm')"
}

git add -A
git commit -m $msg
git push origin master
railway up --detach

Write-Host ""
Write-Host "✓ 배포 완료: $msg"
Write-Host "  로컬: http://localhost:5000"
Write-Host "  Railway: https://fmkorea-web-production.up.railway.app"
