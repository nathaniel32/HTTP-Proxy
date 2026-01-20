start cmd /k run.bat
TIMEOUT /t 3
start cmd /k php -S localhost:10001 -t test\1
start cmd /k php -S localhost:10002 -t test\2
start cmd /k python -m worker.main --target-hostname http://localhost:10001/
start cmd /k python -m worker.main --target-hostname http://localhost:10002/