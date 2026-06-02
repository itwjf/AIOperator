@echo off
chcp 65001 >nul
title AIOperator 一键启动

echo ============================================
echo   AIOperator — 启动所有服务
echo ============================================
echo.

cd /d "%~dp0"
set PYTHONPATH=%~dp0

:: =============================================
:: 1. MCP 服务
:: =============================================
echo [1/4] 启动 MCP 时间服务 (8003)...
start "MCP-Time" cmd /c "set PYTHONPATH=%PYTHONPATH% && python mcp_servers\time_server.py"
echo        等待就绪...
timeout /t 2 /nobreak >nul

echo [2/4] 启动 MCP 数据库服务 (8004)...
start "MCP-DB" cmd /c "set PYTHONPATH=%PYTHONPATH% && python mcp_servers\db_server.py"
echo        等待就绪...
timeout /t 2 /nobreak >nul

echo [3/4] 启动 MCP PPT服务 (8005)...
start "MCP-PPT" cmd /c "set PYTHONPATH=%PYTHONPATH% && python mcp_servers\ppt_server.py"
echo        等待就绪...
timeout /t 2 /nobreak >nul

:: =============================================
:: 2. 主应用
:: =============================================
echo [4/4] 启动 AIOperator 主应用 (9900)...
start "AIOperator" cmd /c "set PYTHONPATH=%PYTHONPATH% && python app\main.py"
timeout /t 5 /nobreak >nul

:: =============================================
:: 3. 验证
:: =============================================
echo.
echo ============================================
echo   验证服务状态...
echo ============================================
curl -s -o NUL -w "  时间服务  (8003): %%{http_code}\n" http://127.0.0.1:8003/mcp
curl -s -o NUL -w "  数据库    (8004): %%{http_code}\n" http://127.0.0.1:8004/mcp
curl -s -o NUL -w "  PPT服务   (8005): %%{http_code}\n" http://127.0.0.1:8005/mcp
curl -s -o NUL -w "  主应用    (9900): %%{http_code}\n" http://127.0.0.1:9900/health

echo.
echo ============================================
echo   全部启动完成！
echo   浏览器打开: http://127.0.0.1:9900
echo ============================================
echo.
echo   关闭方式: 关闭所有弹出的命令行窗口
echo.

pause
