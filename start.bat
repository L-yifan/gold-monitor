@echo off
set "ENV_PYTHON=D:\anaconda3\envs\yolotrain\python.exe"
set "APP_PATH=D:\programdata\code\test\gold-monitor\app.py"

echo ================================================
echo   Gold Price Monitor - Au99.99 - Fast Launch
echo ================================================

:: Start browser in background after 1s delay
start /b "" cmd /c "timeout /t 1 >nul && start http://localhost:5000"

:: Check Python and start app
if exist "%ENV_PYTHON%" (
    "%ENV_PYTHON%" -u "%APP_PATH%"
) else (
    echo [ERROR] Python environment not found: %ENV_PYTHON%
    pause
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Application exited with error.
    pause
)
