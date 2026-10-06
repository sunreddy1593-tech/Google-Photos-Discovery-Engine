@echo off
cd /d "C:\Users\sunayana\Downloads\Google Photos discovery engine"
"C:\Users\sunayana\Downloads\Google Photos discovery engine\.venv\Scripts\python.exe" "C:\Users\sunayana\Downloads\Google Photos discovery engine\main.py" schedule
set "DISCOVERY_RUN_EXIT=%ERRORLEVEL%"
if not "%DISCOVERY_RUN_EXIT%"=="0" exit /b %DISCOVERY_RUN_EXIT%
"C:\Users\sunayana\Downloads\Google Photos discovery engine\.venv\Scripts\python.exe" "C:\Users\sunayana\Downloads\Google Photos discovery engine\scripts\publish_cloud_snapshots.py"
rem Publication failure must not restart or fail the completed research run.
exit /b %DISCOVERY_RUN_EXIT%
