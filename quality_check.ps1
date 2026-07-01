#!/usr/bin/env pwsh
param([switch]$Blocking)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "=== Quality Gate ===" -ForegroundColor Cyan
$layers = @(
    @{Name="Layer1: ruff format"; Cmd="ruff format --check ."},
    @{Name="Layer1: ruff check"; Cmd="ruff check ."},
    @{Name="Layer2: mypy strict"; Cmd="mypy --strict core/ tools/ config/"},
    @{Name="Layer2: pytest+coverage"; Cmd="pytest tests/ -v --cov=core --cov=config --cov=storage --cov=memory --cov=tools --cov-report=term --cov-fail-under=90"}
)
$failed=0;$total=0
foreach ($layer in $layers) {
    $total++
    if ($Blocking -and $failed -gt 0) { Write-Host "[SKIP] $($layer.Name)" -ForegroundColor Gray; continue }
    Write-Host "[$($layer.Name)]" -ForegroundColor Yellow
    try { Invoke-Expression $layer.Cmd; if ($LASTEXITCODE -eq 0) { Write-Host "PASS" -ForegroundColor Green } else { throw "exit $LASTEXITCODE" } }
    catch { Write-Host "FAIL" -ForegroundColor Red; $failed++ }
}
Write-Host "`n$($total - $failed)/$total PASS"
if ($failed -eq 0) { Write-Host "=== ALL GATES PASSED ===" -ForegroundColor Green; exit 0 }
else { Write-Host "=== $failed GATE(S) FAILED ===" -ForegroundColor Red; exit 1 }
