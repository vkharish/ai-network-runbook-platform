@echo off
:: ============================================================
:: AI Network Runbook Platform — Windows Installer
:: Run once to set up everything on a fresh Windows machine
:: Usage: scripts\install_windows.bat
:: ============================================================

setlocal EnableDelayedExpansion
title AI Runbook Platform — Windows Setup

echo.
echo ============================================================
echo   AI Network Runbook Platform — Windows Installer
echo ============================================================
echo.

:: ── Check prerequisites ──────────────────────────────────────
echo [1/6] Checking prerequisites...

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    echo         Make sure to tick "Add Python to PATH"
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK]  Python %PY_VER%

git --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git not found. Install from https://git-scm.com
    pause & exit /b 1
)
echo [OK]  Git found

docker --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker not found. Install Docker Desktop from https://docker.com
    echo         Start Docker Desktop and wait for the whale icon in the taskbar.
    pause & exit /b 1
)
echo [OK]  Docker found

:: ── Virtual environment ──────────────────────────────────────
echo.
echo [2/6] Setting up Python virtual environment...

if not exist ".venv" (
    python -m venv .venv
    echo [OK]  Virtual environment created
) else (
    echo [OK]  Virtual environment already exists
)

:: ── Install dependencies ─────────────────────────────────────
echo.
echo [3/6] Installing Python dependencies...

call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed. Check requirements.txt
    pause & exit /b 1
)
echo [OK]  Dependencies installed

:: ── Set up .env ──────────────────────────────────────────────
echo.
echo [4/6] Setting up .env file...

if not exist ".env" (
    copy .env.example .env >nul
    echo [OK]  .env created from .env.example
    echo.
    echo *** IMPORTANT: Edit .env and set these values before continuing:
    echo     APP_SECRET_KEY  — any 32+ char random string
    echo     ANTHROPIC_API_KEY — your sk-ant-... key
    echo.
    echo Opening .env in Notepad...
    notepad .env
    echo.
    echo Press any key when you have saved .env...
    pause >nul
) else (
    echo [OK]  .env already exists
)

:: ── Start infrastructure ─────────────────────────────────────
echo.
echo [5/6] Starting Docker infrastructure (postgres, redis, chromadb)...

docker compose -f docker/docker-compose.yml up -d postgres redis chromadb
if errorlevel 1 (
    echo [ERROR] Docker compose failed. Is Docker Desktop running?
    pause & exit /b 1
)

:: Wait for postgres to be ready
echo Waiting for PostgreSQL to be ready...
:wait_pg
docker exec runbook_postgres pg_isready -U runbook >nul 2>&1
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto wait_pg
)
echo [OK]  PostgreSQL ready

:: ── Run migrations ───────────────────────────────────────────
echo.
echo [6/6] Running database migrations...

call .venv\Scripts\activate.bat
alembic upgrade head
if errorlevel 1 (
    echo [ERROR] Migration failed. Check your DATABASE_URL in .env
    pause & exit /b 1
)
echo [OK]  Database migrations complete

:: ── Done ─────────────────────────────────────────────────────
echo.
echo ============================================================
echo   Installation complete!
echo ============================================================
echo.
echo Next steps:
echo   1. Start the API:    scripts\start_windows.bat api
echo   2. Start the worker: scripts\start_windows.bat worker
echo   3. Run tests:        scripts\start_windows.bat test
echo   4. Check status:     scripts\start_windows.bat status
echo.
pause
