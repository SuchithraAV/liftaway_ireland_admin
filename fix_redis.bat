@echo off
echo Fixing Redis MISCONF error...
echo.

redis-cli CONFIG SET stop-writes-on-bgsave-error no
if %ERRORLEVEL% EQU 0 (
    echo SUCCESS: Redis fixed!
    echo.
    redis-cli CONFIG REWRITE
    echo Configuration saved.
    echo.
    echo You can now start your application.
) else (
    echo FAILED: Could not connect to Redis
    echo.
    echo Make sure Redis is running:
    echo   redis-server
    echo.
    echo Or check if Redis service is running
)

pause
