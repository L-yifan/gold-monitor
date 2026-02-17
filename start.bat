@echo off
setlocal enabledelayedexpansion

:: ================================================
:: Gold-Fund Monitor - Auto-Adaptive Launcher
:: ================================================

:: 1. Dynamically locate app.py in the script's directory
set "APP_PATH=%~dp0app.py"
set "ENV_PYTHON="

:: 2. Check Configuration File (Priority 0)
:: First check new location (config/launcher.ini), then fallback to old location
set "INI_FILE=%~dp0config\launcher.ini"
if not exist "%INI_FILE%" (
    set "INI_FILE=%~dp0launcher.ini"
)

if exist "%INI_FILE%" (
    echo [INFO] Reading configuration from %INI_FILE%...
    for /f "usebackq tokens=1,* delims==" %%A in ("%INI_FILE%") do (
        set "KEY=%%A"
        set "VAL=%%B"
        :: Remove spaces
        set "KEY=!KEY: =!"
        
        if /i "!KEY!"=="python_path" (
            if not "!VAL!"=="" (
                set "CONFIG_PYTHON=!VAL!"
            )
        )
    )
)

if defined CONFIG_PYTHON (
    if exist "!CONFIG_PYTHON!" (
        set "ENV_PYTHON=!CONFIG_PYTHON!"
        echo [INFO] Using configured Python: !ENV_PYTHON!
        goto :FOUND
    ) else (
        echo [WARN] Configured python_path not found: !CONFIG_PYTHON!
        echo [WARN] Falling back to auto-detection...
    )
)

:: 3. Auto-detect Python Environment

:: Priority 1: Local 'venv' (Standard Virtual Env)
if exist "%~dp0venv\Scripts\python.exe" (
    set "ENV_PYTHON=%~dp0venv\Scripts\python.exe"
    echo [INFO] Found local virtual environment: venv
    goto :FOUND
)

:: Priority 2: Local '.venv' (Hidden Virtual Env)
if exist "%~dp0.venv\Scripts\python.exe" (
    set "ENV_PYTHON=%~dp0.venv\Scripts\python.exe"
    echo [INFO] Found local virtual environment: .venv
    goto :FOUND
)

:: Priority 3: Specific Anaconda Environment (Legacy User Config)
if exist "D:\anaconda3\envs\yolotrain\python.exe" (
    set "ENV_PYTHON=D:\anaconda3\envs\yolotrain\python.exe"
    echo [INFO] Found Anaconda environment: yolotrain
    goto :FOUND
)

:: Priority 4: System Default (Fallback)
set "ENV_PYTHON=python"
echo [INFO] Using system default Python

:FOUND
echo ================================================
echo   App Path: %APP_PATH%
echo ================================================

:: Start browser in background after 2s delay
start /b "" cmd /c "timeout /t 2 >nul && start http://localhost:5000"

:: Start the Application
"!ENV_PYTHON!" -u "%APP_PATH%"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %ERRORLEVEL%.
    echo.
    echo Troubleshooting:
    echo 1. Check config/launcher.ini configuration.
    echo 2. If using system python, ensure it is added to PATH.
    echo 3. Ensure dependencies are installed: pip install -r requirements.txt
    echo.
    pause
)
