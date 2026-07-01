#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
git diff --quiet
if ($LASTEXITCODE -eq 0) { Write-Host "无变更，跳过提交"; exit 0 }
git add -A
git commit -m "fix: v0.2.1-bugfix 测试覆盖率提升+质检脚本+env旁路"
git tag -a v0.2.1-bugfix -m "v0.2.1-bugfix: 测试覆盖≥90%/质检脚本/env旁路"
Write-Host "=== v0.2.1-bugfix 归档完成 ===" -ForegroundColor Green
