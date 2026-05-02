@echo off
:: ============================================================
:: AI Network Runbook Platform — Windows Manager
:: Equivalent of manage.sh for Windows
::
:: Usage:
::   scripts\start_windows.bat status
::   scripts\start_windows.bat start api
::   scripts\start_windows.bat start worker
::   scripts\start_windows.bat start all
::   scripts\start_windows.bat stop api
::   scripts\start_windows.bat stop all
::   scripts\start_windows.bat test
::   scripts\start_windows.bat logs api
:: ============================================================

setlocal EnableDelayedExpansion
title AI Runbook Platform

set CMD=%1
set MOD=%2

if "%CMD%"=="" goto usage
if "%CMD%"=="status"  goto status
if "%CMD%"=="start"   goto start
if "%CMD%"=="stop"    goto stop
if "%CMD%"=="test"    goto test
if "%CMD%"=="logs"    goto logs
if "%CMD%"=="reset"   goto reset
goto usage

:: ── STATUS ───────────────────────────────────────────────────
:status
echo.
echo ============================================================
echo   AI Runbook Platform — Status
echo ============================================================

:: Docker services
for %%s in (runbook_postgres runbook_redis runbook_chroma) do (
    docker inspect --format="{{.State.Status}}" %%s >nul 2>&1
    if errorlevel 1 (
        echo [STOP] %%s — not found
    ) else (
        for /f %%i in ('docker inspect --format={{.State.Status}} %%s 2^>nul') do (
            if "%%i"=="running" (
                echo [OK]   %%s — running
            ) else (
                echo [STOP] %%s — %%i
            )
        )
    )
)

:: API
curl -s --max-time 2 http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo [STOP] API — not responding on :8000
) else (
    echo [OK]   API — http://localhost:8000
)

:: Worker — check via Redis queue
docker exec runbook_redis redis-cli PING >nul 2>&1
if not errorlevel 1 (
    for /f %%q in ('docker exec runbook_redis redis-cli LLEN celery 2^>nul') do (
        echo [INFO] Celery queue depth: %%q
    )
)

echo.
echo Swagger UI:  http://localhost:8000/docs
echo Health:      http://localhost:8000/health
echo Flower:      http://localhost:5555
echo.
goto end

:: ── START ────────────────────────────────────────────────────
:start
if "%MOD%"=="all"     goto start_all
if "%MOD%"=="infra"   goto start_infra
if "%MOD%"=="api"     goto start_api
if "%MOD%"=="worker"  goto start_worker
if "%MOD%"=="test"    goto test
echo [ERROR] Unknown module: %MOD%
goto usage

:start_all
call scripts\start_windows.bat start infra
timeout /t 3 /nobreak >nul
start "Runbook API" cmd /k "scripts\start_windows.bat start api"
timeout /t 3 /nobreak >nul
start "Runbook Worker" cmd /k "scripts\start_windows.bat start worker"
echo [OK] All services started in separate windows
goto end

:start_infra
echo Starting Docker infrastructure...
docker compose -f docker/docker-compose.yml up -d postgres redis chromadb
echo Waiting for PostgreSQL...
:wait_pg2
docker exec runbook_postgres pg_isready -U runbook >nul 2>&1
if errorlevel 1 ( timeout /t 2 /nobreak >nul & goto wait_pg2 )
echo [OK] Infrastructure ready
goto end

:start_api
echo Starting FastAPI...
call .venv\Scripts\activate.bat
:: Clear corporate proxy
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
goto end

:start_worker
echo Starting Celery worker...
call .venv\Scripts\activate.bat
:: Clear corporate proxy (breaks pip install in worker tasks)
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
:: --pool=solo is REQUIRED on Windows
celery -A backend.tasks.celery_worker worker --loglevel=info --pool=solo
goto end

:: ── STOP ─────────────────────────────────────────────────────
:stop
if "%MOD%"=="all" (
    echo Stopping all services...
    docker compose -f docker/docker-compose.yml down
    taskkill /f /im uvicorn.exe >nul 2>&1
    taskkill /f /fi "WINDOWTITLE eq Runbook API" >nul 2>&1
    taskkill /f /fi "WINDOWTITLE eq Runbook Worker" >nul 2>&1
    echo [OK] All stopped
    goto end
)
if "%MOD%"=="api" (
    taskkill /f /im uvicorn.exe >nul 2>&1
    echo [OK] API stopped
    goto end
)
if "%MOD%"=="infra" (
    docker compose -f docker/docker-compose.yml down
    echo [OK] Infrastructure stopped
    goto end
)
echo [ERROR] Unknown module: %MOD%
goto usage

:: ── TEST ─────────────────────────────────────────────────────
:test
echo Running test suite...
call .venv\Scripts\activate.bat
python -m pytest tests/ -v
goto end

:: ── LOGS ─────────────────────────────────────────────────────
:logs
if "%MOD%"=="postgres" ( docker logs -f runbook_postgres & goto end )
if "%MOD%"=="redis"    ( docker logs -f runbook_redis    & goto end )
if "%MOD%"=="chromadb" ( docker logs -f runbook_chroma   & goto end )
echo [ERROR] For API/worker logs, check the terminal window they are running in.
goto end

:: ── RESET INCIDENT ───────────────────────────────────────────
:reset
if "%MOD%"=="" ( echo Usage: start_windows.bat reset ^<incident_number^> & goto end )
docker exec runbook_postgres psql -U runbook -d runbook_db -c "UPDATE incidents SET status='open', ai_report=NULL WHERE incident_number=%MOD%;"
echo [OK] Incident %MOD% reset to open
goto end

:: ── USAGE ────────────────────────────────────────────────────
:usage
echo.
echo Usage: scripts\start_windows.bat ^<command^> [module]
echo.
echo Commands:
echo   status              — show status of all services
echo   start all           — start everything (opens separate windows)
echo   start infra         — start postgres + redis + chromadb
echo   start api           — start FastAPI (run in its own window)
echo   start worker        — start Celery worker (run in its own window)
echo   stop  all           — stop everything
echo   stop  api           — stop API
echo   stop  infra         — stop Docker services
echo   test                — run 49-test suite
echo   logs  postgres      — tail postgres logs
echo   logs  redis         — tail redis logs
echo   reset ^<number^>      — reset stuck incident back to open
echo.

:end
endlocal
