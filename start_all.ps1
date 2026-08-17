$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$parser = $null
if (Test-Path ".env") {
  $parser = (Select-String -Path ".env" -Pattern '^\s*PAPERLENS_PARSER=(\S+)' | Select-Object -First 1).Matches.Groups[1].Value
}
if ($parser -eq "pymupdf") {
  uv sync
} else {
  uv sync --extra mineru
}
uv run alembic upgrade head

$backend = Start-Process -PassThru -NoNewWindow -FilePath "uv" -ArgumentList @(
  "run", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"
)

Push-Location frontend
if (-not (Test-Path "node_modules")) { npm install }
$frontend = Start-Process -PassThru -NoNewWindow -FilePath "npm" -ArgumentList @("run", "dev")
Pop-Location

Write-Host "后端: http://0.0.0.0:8000"
Write-Host "前端: http://0.0.0.0:5173"
Write-Host "按 Ctrl+C 结束..."

try {
  Wait-Process -Id $backend.Id, $frontend.Id
} finally {
  if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue }
  if (-not $frontend.HasExited) { Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue }
}
