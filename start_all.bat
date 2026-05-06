@echo off
REM ================================================================
REM  Desibots — Start All Services Locally (No Docker)
REM  Starts 6 services in separate windows:
REM    1. Main Backend     (Node.js   :8000)
REM    2. FirstAid API     (FastAPI   :8510)
REM    3. HisabBot API     (FastAPI   :8511)
REM    4. PakOrderBot API  (FastAPI   :8512)
REM    5. LawBot API       (FastAPI   :8513)
REM    6. Main Frontend    (Vite      :5173)
REM
REM  NOTE: No more Streamlit processes needed!
REM        All bot UIs are built into the React frontend.
REM ================================================================

echo ============================================================
echo    DESIBOTS — Starting All Services (React Frontend)
echo ============================================================
echo.

REM -- 1. Main Backend (Node.js / Express) -------------------------
echo [1/6] Starting Main Backend on port 8000...
start "Desibots - Main Backend :8000" cmd /k "cd /d %~dp0main-backend && node server.js"
timeout /t 2 /nobreak >nul

REM -- 2. FirstAid API (FastAPI) -----------------------------------
echo [2/6] Starting FirstAid API on port 8510...
start "Desibots - FirstAid API :8510" cmd /k "cd /d %~dp0firstaid-project\backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8510 --reload"
timeout /t 2 /nobreak >nul

REM -- 3. HisabBot API (FastAPI) -----------------------------------
echo [3/6] Starting HisabBot API on port 8511...
start "Desibots - HisabBot API :8511" cmd /k "cd /d %~dp0hisabbot && python -m uvicorn app.main:app --host 127.0.0.1 --port 8511 --reload"
timeout /t 2 /nobreak >nul

REM -- 4. PakOrderBot API (FastAPI) --------------------------------
echo [4/6] Starting PakOrderBot API on port 8512...
start "Desibots - PakOrder API :8512" cmd /k "cd /d %~dp0pakorderbot && python -m uvicorn agent.main:app --host 127.0.0.1 --port 8512 --reload"
timeout /t 2 /nobreak >nul

REM -- 5. LawBot API (FastAPI) ------------------------------------
echo [5/6] Starting LawBot API on port 8513...
start "Desibots - LawBot API :8513" cmd /k "cd /d %~dp0lawyerbot && python -m uvicorn server:app --host 127.0.0.1 --port 8513 --reload"
timeout /t 2 /nobreak >nul

REM -- 6. Main Frontend (Vite / React) ----------------------------
echo [6/6] Starting Main Frontend on port 5173...
start "Desibots - Frontend :5173" cmd /k "cd /d %~dp0main-frontend && npm run dev"

echo.
echo ============================================================
echo    All 6 services started!
echo.
echo    Frontend:  http://localhost:5173
echo    Backend:   http://localhost:8000
echo.
echo    Bot APIs  (called by React frontend via backend proxy):
echo      FirstAid   : http://localhost:8510
echo      HisabBot   : http://localhost:8511
echo      PakOrder   : http://localhost:8512
echo      LawBot     : http://localhost:8513
echo.
echo    No Streamlit needed anymore!
echo ============================================================
echo.
echo Close this window or press any key to exit.
pause >nul
