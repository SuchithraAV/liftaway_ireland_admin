@echo off
echo === FIXING DEPLOYMENT ===
echo.
echo Stopping containers...
docker-compose down

echo.
echo Rebuilding image...
docker-compose build --no-cache

echo.
echo Starting containers...
docker-compose up -d

echo.
echo Waiting 5 seconds...
timeout /t 5 /nobreak > nul

echo.
echo Checking logs...
docker logs admin-backend --tail 30

echo.
echo === DONE ===
pause
