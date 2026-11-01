@echo off
REM Stops the Pensionz Docker Compose stack. Data volumes (database, MinIO) are kept.
cd /d "%~dp0"
docker compose stop
