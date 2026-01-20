start cmd /k run.bat
TIMEOUT /t 3
start cmd /k "cd /d %~dp0\test && uvicorn test_stream:app --port 10003"
start cmd /k python -m worker.main --target-hostname http://localhost:10003