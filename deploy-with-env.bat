@echo off
echo ========================================
echo   DEPLOYING WITH .ENV FILE IN IMAGE
echo ========================================
echo.

echo [1/4] Stopping existing containers...
docker-compose down

echo.
echo [2/4] Rebuilding image (with .env file)...
docker-compose build --no-cache

echo.
echo [3/4] Starting containers...
docker-compose up -d

echo.
echo [4/4] Waiting for startup...
timeout /t 5 /nobreak > nul

echo.
echo ========================================
echo   CHECKING DEPLOYMENT STATUS
echo ========================================
docker logs admin-backend --tail 50

echo.
echo ========================================
echo   DEPLOYMENT COMPLETE
echo ========================================
echo.
echo To monitor logs: docker logs admin-backend -f
echo To check status: docker ps
echo.
pause
