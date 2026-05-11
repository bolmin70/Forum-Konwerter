@echo off
REM ============================================================
REM  Forum Konwerter - Windows build script
REM  Produces a single-file standalone .exe in the "dist" folder.
REM  Run this on a Windows machine that has Python 3.10+ installed.
REM ============================================================

setlocal
cd /d "%~dp0"

echo.
echo [1/4] Creating virtual environment...
if not exist ".venv-build" (
    python -m venv .venv-build || goto :error
)

call ".venv-build\Scripts\activate.bat" || goto :error

echo.
echo [2/4] Installing dependencies...
python -m pip install --upgrade pip || goto :error
python -m pip install -r requirements.txt || goto :error
python -m pip install pyinstaller || goto :error

echo.
echo [3/4] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist ForumKonwerter.spec del /q ForumKonwerter.spec

echo.
echo [4/4] Building executable with PyInstaller...
pyinstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "ForumKonwerter" ^
    app.py || goto :error

echo.
echo ============================================================
echo  Build complete!  See: dist\ForumKonwerter.exe
echo ============================================================
endlocal
exit /b 0

:error
echo.
echo *** BUILD FAILED ***
endlocal
exit /b 1
