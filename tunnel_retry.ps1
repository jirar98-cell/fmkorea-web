while ($true) {
    Write-Host "cloudflared 시도중..."
    $out = cloudflared tunnel --url http://localhost:5000 2>&1
    $url = $out | Select-String "https://" | Select-Object -First 1
    if ($url) { Write-Host $url; break }
    Write-Host "실패. 5초 후 재시도..."
    Start-Sleep -Seconds 5
}
Write-Host "완료. 이 창을 닫지 마세요."
pause
