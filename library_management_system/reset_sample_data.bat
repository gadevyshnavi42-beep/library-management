@echo off
REM Replaces books, students and loans with fresh demo data (dates relative to today).
cd /d "%~dp0"
if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat
python generate_sample_data.py --reset
pause
