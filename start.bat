@echo off

title AIOperator һ������



echo ============================================

echo   AIOperator �� �������з���

echo ============================================

echo.



cd /d "%~dp0"

set PYTHONPATH=%~dp0



:: =============================================

:: 1. MCP ����

:: =============================================

echo [1/4] ���� MCP ʱ����� (8003)...

start "MCP-Time" cmd /c "set PYTHONPATH=%PYTHONPATH% && python mcp_servers\time_server.py"

echo        �ȴ�����...

timeout /t 2 /nobreak >nul



echo [2/4] ���� MCP ���ݿ���� (8004)...

start "MCP-DB" cmd /c "set PYTHONPATH=%PYTHONPATH% && python mcp_servers\db_server.py"

echo        �ȴ�����...

timeout /t 2 /nobreak >nul



echo [3/4] ���� MCP PPT���� (8005)...

start "MCP-PPT" cmd /c "set PYTHONPATH=%PYTHONPATH% && python mcp_servers\ppt_server.py"

echo        �ȴ�����...

timeout /t 2 /nobreak >nul



:: =============================================

:: 2. ��Ӧ��

:: =============================================

echo [4/4] ���� AIOperator ��Ӧ�� (9900)...

start "AIOperator" cmd /c "set PYTHONPATH=%PYTHONPATH% && python app\main.py"

timeout /t 5 /nobreak >nul



:: =============================================

:: 3. ��֤

:: =============================================

echo.

echo ============================================

echo   ��֤����״̬...

echo ============================================

curl -s -o NUL -w "  ʱ�����  (8003): %%{http_code}\n" http://127.0.0.1:8003/mcp

curl -s -o NUL -w "  ���ݿ�    (8004): %%{http_code}\n" http://127.0.0.1:8004/mcp

curl -s -o NUL -w "  PPT����   (8005): %%{http_code}\n" http://127.0.0.1:8005/mcp

curl -s -o NUL -w "  ��Ӧ��    (9900): %%{http_code}\n" http://127.0.0.1:9900/health



echo.

echo ============================================

echo   ȫ��������ɣ�

echo   �������: http://127.0.0.1:9900

echo ============================================

echo.

echo   �رշ�ʽ: �ر����е����������д���

echo.



pause

