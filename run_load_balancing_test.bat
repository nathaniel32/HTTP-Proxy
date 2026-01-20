start cmd /k run.bat
TIMEOUT /t 3
start cmd /k python -m http.server 10001 --directory test/1
start cmd /k python -m http.server 10002 --directory test/2
start cmd /k python -m worker.main --target-hostname http://localhost:10001/
start cmd /k python -m worker.main --target-hostname http://localhost:10002/