@echo off
chcp 65001 >nul 2>&1
title 5.1 Surround WEP WebUI

echo.
echo ====================================================
echo   5.1 Surround Upmix - WEP Pipeline
echo   Starting Web UI... Browser will open shortly.
echo ====================================================
echo.

cd /d "%~dp0"

:: ── 自动激活 vep_venv 虚拟环境（如果存在）───
if exist "vep_venv\Scripts\activate.bat" (
    echo [OK] 检测到虚拟环境，正在激活...
    call "vep_venv\Scripts\activate.bat"
) else (
    echo [提示] 未检测到 vep_venv，将使用系统 Python
    echo        如提示缺少依赖，请先运行 pip install .
)

echo Starting Gradio WebUI on http://127.0.0.1:7860 ...
echo.
echo [TIP] Drop your MP3/WAV/FLAC in the browser to start.
echo [TIP] Press Ctrl+C in this window to stop the server.
echo.

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

python "%~dp0wep_webui.py"

pause
