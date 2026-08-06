@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Invoke-LegacyCanceledInspectionCleanup.ps1"
set "cleanup_exit_code=%ERRORLEVEL%"

echo.
if "%cleanup_exit_code%"=="0" (
    echo Cleanup command completed successfully.
) else (
    echo Cleanup command failed with exit code %cleanup_exit_code%.
)
pause
exit /b %cleanup_exit_code%
