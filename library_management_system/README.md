# Library Desk – Library Management System

A complete library management web app built with **Python Flask, HTML, CSS and JavaScript**.
All data is stored in local **JSON files** (`data/`). No database server and no cloud service is needed.

## Features
- Admin login (hashed password, CSRF protection, lock-out after 5 failed attempts, change-password page)
- Book CRUD with ISBN validation, duplicate detection and live availability (`available = copies - on loan`)
- Student registration, editing and removal with duplicate roll number / email checks
- Issue and return with rules: no copy available, duplicate loan, 3-book limit, overdue student blocked
- Overdue fee calculation: `days late x fine per day` (default 2.00/day, 14-day loans)
- Overdue list, full loan history with search and status filter
- Reports: loans per month, by category, top books, top students, fines collected / outstanding
- CSV export (books, students, history, overdue) that opens cleanly in Excel
- Responsive dashboard (sidebar collapses to a menu on phones)
- Friendly error pages, corrupt-JSON recovery, atomic file writes

## Run on Windows
1. Install Python 3.9+ from python.org (tick **Add Python to PATH**).
2. Double-click **`run.bat`**. It creates a virtual environment, installs Flask and opens http://127.0.0.1:5000.
3. Sign in with **admin / admin123** and change the password under *Account*.

Manual alternative (Command Prompt):
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
macOS / Linux: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && python app.py`

## Tests
Double-click `run_tests.bat` or run `python -m unittest discover -s tests -v` (38 tests: fee maths, auth, CRUD,
validation, issue/return rules, reports, CSV, error handling).

## Sample data
`data/` ships with 12 books, 6 students and 12 loans (2 overdue). Run `reset_sample_data.bat`
(or `python generate_sample_data.py --reset`) to regenerate it with dates relative to today.
To start empty, delete `books.json`, `students.json` and `transactions.json` from `data/`.

## Settings
Edit the defaults in `create_app()` in `app.py`: `LOAN_DAYS`, `FINE_PER_DAY`, `MAX_LOANS`, `CURRENCY`.
Environment variables: `PORT`, `LMS_DATA_DIR`, `LMS_SECRET_KEY`.

## Project layout
```
app.py                    Flask app, routes, validation, JSON store
generate_sample_data.py   Demo data generator
templates/                Jinja2 pages (base, form, dashboard, books, students, issue, ...)
static/css/style.css      Responsive styling
static/js/app.js          Menu, live search, confirmations, due-date preview
tests/test_app.py         Automated tests
data/                     JSON database files
REPORT.md                 College project report
```

## Notes
- Built for a single library desk running locally. It serialises writes with a lock, but it is not meant for many
  simultaneous servers. Use `python app.py` (Flask's built-in server) on one machine.
- Back up the `data/` folder to back up the system.
