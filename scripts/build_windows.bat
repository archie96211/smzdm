@echo off
setlocal

cd /d "%~dp0\.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\build_exe.py %*
) else (
  py -3 scripts\build_exe.py %*
  if errorlevel 1 python scripts\build_exe.py %*
)
endlocal
