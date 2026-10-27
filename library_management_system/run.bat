@echo off
REM Starts Library Desk on Windows. First run creates a virtual environment.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
if not exist venv\Scripts\python.exe (
  echo Creating virtual environment...
  %PY% -m venv venv || goto :fail
)
call venv\Scripts\activate.bat
pip install -q -r requirements.txt || goto :fail
echo.
echo Library Desk is starting at http://127.0.0.1:5000  (login: admin / admin123)
echo Press Ctrl+C to stop.
start "" http://127.0.0.1:5000
python app.py
goto :eof
:fail
echo.
echo Setup failed. Make sure Python 3.9+ is installed and "Add Python to PATH" was ticked.
pause
