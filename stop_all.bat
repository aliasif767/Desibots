@echo off
REM ================================================================
REM  Desibots — Stop All Services
REM  Kills all running Node and Uvicorn processes
REM  (No more Streamlit to kill!)
REM ================================================================

echo ============================================================
echo    DESIBOTS — Stopping All Services
echo ============================================================
echo.

echo Stopping Node.js processes (main-backend, frontend)...
taskkill /FI "WINDOWTITLE eq Desibots*" /F >nul 2>&1

echo Stopping any remaining node processes...
taskkill /IM node.exe /F >nul 2>&1

echo Stopping Uvicorn processes (FastAPI bots)...
taskkill /IM uvicorn.exe /F >nul 2>&1

echo.
echo ============================================================
echo    All Desibots services stopped.
echo ============================================================
echo.
pause
