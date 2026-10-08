$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$cloudflareLog = Join-Path $env:TEMP "stocklart-cloudflare.log"
$cloudflareErrorLog = Join-Path $env:TEMP "stocklart-cloudflare-error.log"
Remove-Item $cloudflareLog, $cloudflareErrorLog -Force -ErrorAction SilentlyContinue

Write-Host "A iniciar Cloudflare Tunnel..."
$cloudflare = Start-Process cloudflared `
    -ArgumentList "tunnel", "--url", "http://localhost:5000" `
    -RedirectStandardOutput $cloudflareLog `
    -RedirectStandardError $cloudflareErrorLog `
    -PassThru

$cloudflareUrl = $null
for ($attempt = 0; $attempt -lt 30 -and -not $cloudflareUrl; $attempt++) {
    Start-Sleep -Seconds 1
    $text = @(
        (Get-Content $cloudflareLog -Raw -ErrorAction SilentlyContinue)
        (Get-Content $cloudflareErrorLog -Raw -ErrorAction SilentlyContinue)
    ) -join "`n"
    if ($text -match "https://[a-z0-9-]+\.trycloudflare\.com") {
        $cloudflareUrl = $Matches[0]
    }
}

if (-not $cloudflareUrl) {
    Stop-Process -Id $cloudflare.Id -Force -ErrorAction SilentlyContinue
    throw "Nao foi possivel detetar o endereco do Cloudflare. Verifica se cloudflared esta instalado."
}

$env:PUBLIC_BASE_URL = $cloudflareUrl
Write-Host "Cloudflare: $cloudflareUrl"
Write-Host "A iniciar ngrok e Flask..."

$ngrok = Start-Process ngrok `
    -ArgumentList "http", "5000", "--url", "https://outtakes-parsley-drastic.ngrok-free.dev", "--traffic-policy-file", "policy.yaml" `
    -PassThru

try {
    Write-Host "Site: https://outtakes-parsley-drastic.ngrok-free.dev"
    Write-Host "Imagens no Sheets: $cloudflareUrl"
    Write-Host "Pressiona Ctrl+C para parar."
    python app.py
}
finally {
    Stop-Process -Id $ngrok.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $cloudflare.Id -Force -ErrorAction SilentlyContinue
}
