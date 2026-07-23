@echo off
chcp 65001 >nul
echo ============================================
echo   AIOperator — 一键启动全部服务
echo ============================================
echo.

cd /d "%~dp0"

:: 激活虚拟环境（如果存在）
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

echo [1/6] 启动 MCP Time Server    (8003)...
start "AIO-MCP-Time"     cmd /c "python mcp_servers/time_server.py"

echo [2/6] 启动 MCP DB Server      (8004)...
start "AIO-MCP-DB"       cmd /c "python mcp_servers/db_server.py"

echo [3/6] 启动 MCP PPT Server     (8005)...
start "AIO-MCP-PPT"      cmd /c "python mcp_servers/ppt_server.py"

echo [4/6] 启动 MCP Docker Server  (8006)...
start "AIO-MCP-Docker"   cmd /c "python mcp_servers/docker_server.py"

echo [5/6] 启动 MCP Search Server  (8007)...
start "AIO-MCP-Search"   cmd /c "python mcp_servers/search_server.py"

echo [6/6] 启动 主应用             (9900)...
start "AIO-Main"         cmd /c "python app/main.py"

echo.
echo ============================================
echo   全部服务已启动！浏览器打开:
echo   http://127.0.0.1:9900
echo ============================================
echo.
pause
