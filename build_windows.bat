@echo off
setlocal EnableDelayedExpansion
REM ─────────────────────────────────────────────────────────────────────────────
REM  build_windows.bat  –  Build Forum Konwerter as a single-file Windows EXE
REM
REM  Usage:
REM    build_windows.bat
REM
REM  Output:
REM    dist\ForumKonwerter.exe  (standalone, no installation needed)
REM ─────────────────────────────────────────────────────────────────────────────

set "PY_VERSION=3.13.0"
set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%-amd64.exe"

REM ── 1. Ensure Python (with pythonw.exe) is available ─────────────────────────
set "NEED_INSTALL=0"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    set "NEED_INSTALL=1"
    echo [*] Python not found.
) else (
    REM Make sure pythonw.exe exists alongside python.exe. PyInstaller's
    REM windowed mode (console=False) requires it. Microsoft Store / minimal
    REM installs may lack it, producing the "pythonw is missing" error.
    set "PY_PATH="
    for /f "delims=" %%i in ('where python 2^>nul') do (
        if not defined PY_PATH set "PY_PATH=%%i"
    )
    for %%i in ("!PY_PATH!") do set "PY_DIR=%%~dpi"
    if not exist "!PY_DIR!pythonw.exe" (
        echo [!] python.exe found but pythonw.exe is missing in:
        echo     !PY_DIR!
        echo     This usually means Python was installed from the Microsoft Store
        echo     or with a reduced component set. Reinstalling from python.org ...
        set "NEED_INSTALL=1"
    )
)

if "!NEED_INSTALL!"=="1" (
    echo [*] Downloading official Python %PY_VERSION% installer from python.org ...
    set "PY_INSTALLER=%TEMP%\python-%PY_VERSION%-amd64.exe"

    where curl >nul 2>&1
    if !errorlevel! equ 0 (
        curl -L -o "!PY_INSTALLER!" "%PY_URL%"
    ) else (
        powershell -Command "Invoke-WebRequest -Uri '%PY_URL%' -OutFile '!PY_INSTALLER!'"
    )

    if not exist "!PY_INSTALLER!" (
        echo [ERROR] Download failed. Please install Python manually from
        echo         https://www.python.org/downloads/
        pause
        exit /b 1
    )

    echo [*] Running Python installer (silent, full components incl. pythonw)...
    "!PY_INSTALLER!" /quiet ^
        InstallAllUsers=0 ^
        PrependPath=1 ^
        Include_pip=1 ^
        Include_launcher=1 ^
        Include_tcltk=1 ^
        Include_dev=1 ^
        Include_exe=1 ^
        Include_lib=1 ^
        AssociateFiles=0
    set "INSTALL_RC=!errorlevel!"
    del "!PY_INSTALLER!" >nul 2>&1

    if not "!INSTALL_RC!"=="0" (
        echo [ERROR] Python installer exited with code !INSTALL_RC!.
        pause
        exit /b 1
    )

    REM Locate the just-installed Python (PATH isn't refreshed in this session).
    set "PYTHON_EXE="
    for /f "delims=" %%i in ('where python 2^>nul') do (
        if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
    )
    if not defined PYTHON_EXE (
        for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
            if exist "%%d\python.exe" set "PYTHON_EXE=%%d\python.exe"
        )
    )
    if not defined PYTHON_EXE (
        echo [!] Python was installed but is not yet visible in this shell.
        echo     Please close this window and run build_windows.bat again.
        pause
        exit /b 0
    )

    REM Prepend the install folder to PATH for this session.
    for %%i in ("!PYTHON_EXE!") do set "PY_DIR=%%~dpi"
    set "PATH=!PY_DIR!;!PY_DIR!Scripts;!PATH!"
    echo [OK] Python installed at !PY_DIR!
)

REM Final sanity check – python.exe AND pythonw.exe must both be reachable.
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] python.exe is still not on PATH. Aborting.
    pause
    exit /b 1
)
where pythonw >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] pythonw.exe is still missing. PyInstaller cannot build a
    echo         windowed app without it. Please install Python from
    echo         https://www.python.org/downloads/ (NOT the Microsoft Store).
    pause
    exit /b 1
)
echo [OK] python.exe and pythonw.exe both available.

REM ── 2. Install / upgrade build dependencies ──────────────────────────────────
echo.
echo [*] Installing / upgrading build dependencies...
python -m pip install --upgrade pip
python -m pip install --upgrade pyinstaller PySide6
if !errorlevel! neq 0 (
    echo [ERROR] Failed to install build dependencies.
    pause
    exit /b 1
)

REM ── 3. Build the executable ──────────────────────────────────────────────────
echo.
echo [*] Building ForumKonwerter.exe ...
python -m PyInstaller forum_konwerter.spec --clean --noconfirm

echo.
if exist "dist\ForumKonwerter.exe" (
    echo [OK] Build successful!
    echo      Executable: dist\ForumKonwerter.exe
) else (
    echo [ERROR] Build failed – check the output above for details.
    pause
    exit /b 1
)

endlocal
