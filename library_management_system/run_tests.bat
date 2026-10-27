@echo off
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
if not exist venv\Scripts\python.exe ( %PY% -m venv venv )
call venv\Scripts\activate.bat
pip install -q -r requirements.txt
python -m unittest discover -s tests -v
pause
