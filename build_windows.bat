@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  build_windows.bat  –  Build Forum Konwerter as a single-file Windows EXE
REM
REM  Requirements (run once):
REM    pip install pyinstaller PySide6
REM
REM  Usage:
REM    build_windows.bat
REM
REM  Output:
REM    dist\ForumKonwerter.exe  (standalone, no installation needed)
REM ─────────────────────────────────────────────────────────────────────────────

echo [*] Installing / upgrading build dependencies...
pip install --upgrade pyinstaller PySide6

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
