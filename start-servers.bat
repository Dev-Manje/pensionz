@echo off
REM Starts the Pensionz stack in Docker Compose:
REM   db, minio, mailpit, backend (API), worker, frontend.
REM Usage: start-servers.bat            start (builds images only if missing)
REM        start-servers.bat --build    rebuild images first (after dependency changes)
setlocal
cd /d "%~dp0"

REM --- .env is required by the backend and worker services ---
if not exist ".env" (
    echo .env not found - copying .env.example to .env
    copy /y ".env.example" ".env" >nul || goto :fail
)

REM --- Make sure Docker is running; start Docker Desktop if it is not ---
docker info >nul 2>&1
if not errorlevel 1 goto :docker_ready
echo Docker is not running - starting Docker Desktop...
if not exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    echo Could not find Docker Desktop. Start Docker manually and re-run.
    goto :fail
)
start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
set /a tries=0
:wait_docker
timeout /t 3 /nobreak >nul
docker info >nul 2>&1
if not errorlevel 1 goto :docker_ready
set /a tries+=1
if %tries% geq 60 (
    echo Docker did not start within 3 minutes.
    goto :fail
)
goto :wait_docker
:docker_ready
echo Docker is running.

REM --- Start the containers ---
if /i "%~1"=="--build" (
    docker compose up -d --build || goto :fail
) else (
    docker compose up -d || goto :fail
)

REM --- Wait for the API, then apply database migrations ---
echo Waiting for the API on http://localhost:8002 ...
set /a tries=0
:wait_api
curl -s -o nul -f http://localhost:8002/health && goto :api_ready
set /a tries+=1
if %tries% geq 60 (
    echo API did not respond within 2 minutes. Check: docker compose logs backend
    goto :fail
)
timeout /t 2 /nobreak >nul
goto :wait_api
:api_ready

echo Applying database migrations...
docker compose exec -T backend alembic upgrade head || goto :fail

echo.
echo ============================================================
echo  Pensionz is up
echo    Frontend : http://localhost:5178
echo    API      : http://localhost:8002/api/v1   (docs: http://localhost:8002/docs)
echo    Mailpit  : http://localhost:8026
echo    MinIO    : http://localhost:9003
echo  Test logins: TEST_USERS.md
echo  Logs: docker compose logs -f backend frontend
echo  Stop: stop-servers.bat
echo ============================================================
start "" http://localhost:5178
endlocal
exit /b 0

:fail
echo.
echo Startup FAILED.
endlocal
pause
exit /b 1
