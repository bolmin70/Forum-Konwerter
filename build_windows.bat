@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  build_windows.bat  –  Build Forum Konwerter as a single-file Windows EXE
REM
REM  Usage:
REM    build_windows.bat
REM
REM  Output:
REM    dist\ForumKonwerter.exe  (standalone, no installation needed)
REM ─────────────────────────────────────────────────────────────────────────────

REM ── 1. Ensure Python is available ────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Python not found. Downloading and installing Python 3.13 ...

    REM Check for winget (available on Windows 10 1709+ / Windows 11)
    winget --version >nul 2>&1
    if %errorlevel% equ 0 (
        echo [*] Installing Python via winget ...
        winget install --id Python.Python.3.13 --silent --accept-package-agreements --accept-source-agreements
        if %errorlevel% neq 0 (
            echo [ERROR] winget install failed. Please install Python manually from https://www.python.org/downloads/
            pause
            exit /b 1
        )
    ) else (
        REM Fallback: download installer with curl (available on Windows 10 1803+)
        echo [*] winget not available. Downloading Python installer via curl ...
        set "PY_INSTALLER=%TEMP%\python_installer.exe"
        curl -L -o "%PY_INSTALLER%" "https://www.python.org/ftp/python/3.13.0/python-3.13.0-amd64.exe"
        if %errorlevel% neq 0 (
            echo [ERROR] Download failed. Please install Python manually from https://www.python.org/downloads/
            pause
            exit /b 1
        )
        echo [*] Running Python installer (silent) ...
        "%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1
        del "%PY_INSTALLER%"
    )

    REM Refresh PATH so python is available in this session
    for /f "delims=" %%i in ('where python 2^>nul') do set "PYTHON_EXE=%%i"
    if not defined PYTHON_EXE (
        echo [!] Python was installed but is not yet on PATH in this session.
        echo     Please close this window and run build_windows.bat again.
        pause
        exit /b 0
    )
    echo [OK] Python installed successfully.
) else (
    echo [OK] Python already installed.
)

REM ── 2. Install / upgrade build dependencies ──────────────────────────────────
echo.
echo [*] Installing / upgrading build dependencies...
pip install --upgrade pyinstaller PySide6

REM ── 3. Build the executable ───────────────────────────────────────────────────
echo.
echo [*] Building ForumKonwerter.exe ...
pyinstaller forum_konwerter.spec --clean --noconfirm

echo.
if exist "dist\ForumKonwerter.exe" (
    echo [OK] Build successful!
    echo      Executable: dist\ForumKonwerter.exe
) else (
    echo [ERROR] Build failed – check the output above for details.
    exit /b 1
)
