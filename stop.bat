@echo off
chcp 65001 >nul
title AIOperator — 关闭所有服务

echo 正在关闭 AIOperator 所有服务...

:: 关闭所有 Python 进程（MCP Servers + 主应用）
powershell -Command "Get-Process python* -ErrorAction SilentlyContinue | Where-Object { \$_.MainWindowTitle -match 'MCP|AIOperator|uvicorn' -or \$_.Id -eq (Get-NetTCPConnection -LocalPort 9900,8003,8004,8005 -ErrorAction SilentlyContinue).OwningProcess } | Stop-Process -Force -ErrorAction SilentlyContinue" 2>nul

:: 兜底：按端口杀
for %%p in (8003 8004 8005 9900) do (
    powershell -Command "$c=Get-NetTCPConnection -LocalPort %%p -ErrorAction SilentlyContinue; if($c){Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue}" 2>nul
)

echo 所有服务已关闭。
pause
