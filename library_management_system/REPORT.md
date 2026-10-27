# Library Management System (Library Desk)
### Project Report

| | |
|---|---|
| Project title | Library Management System using Python Flask and local JSON storage |
| Submitted by | ______________________ (Name, Register No.) |
| Guide | ______________________ |
| Department / College | ______________________ |
| Academic year | ______________________ |

---

## Certificate and Acknowledgement
*(Insert your college certificate page and acknowledgement here.)*

---

## 1. Abstract
Libraries in small colleges still record book loans in registers or spreadsheets. This causes lost records, wrong
availability counts, and disputes about late fees. **Library Desk** is a web-based Library Management System that lets a
librarian (admin) manage books and students, issue and return books, track availability, calculate overdue fees
automatically, view history and reports, and export data as CSV files. It is built with Python Flask, HTML, CSS and
JavaScript and stores all data in local JSON files, so it needs no database server and runs on an ordinary Windows PC.
The system was verified with 38 automated tests, all of which pass.

## 2. Introduction
### 2.1 Background
A library has three kinds of records that change constantly: the book catalogue, the member list and the loans. A manual
system makes it slow to answer simple questions such as "Is this book on the shelf?" or "Who has not returned their
books?". A small software system answers these in seconds and removes calculation errors.

### 2.2 Problem statement
Manual registers and loose spreadsheets lead to (a) duplicate or inconsistent book entries, (b) no reliable count of
available copies, (c) manual and error-prone fine calculation, (d) no searchable history, and (e) no protection of data.

### 2.3 Objectives
1. Provide a secure admin login.
2. Support create, read, update and delete (CRUD) operations for books.
3. Register and maintain students.
4. Issue and return books while enforcing library rules.
5. Track the number of available copies of every book automatically.
6. Calculate overdue fees automatically.
7. Keep a complete history and generate reports.
8. Export data as CSV for Excel.
9. Offer a responsive interface for desktop, tablet and phone.
10. Use only local files for storage so deployment is trivial.

### 2.4 Scope
The system is designed for one library counter operated by administrators. Students do not log in. Online payment,
barcode scanning and e-mail notification are outside the current scope (see Future Enhancements).

## 3. System Study
### 3.1 Existing system
Paper registers or spreadsheets. Weaknesses: slow searching, no validation, no automatic fines, easy data loss.

### 3.2 Proposed system
A web application with validated forms, automatic availability and fine calculation, searchable history, reports and CSV
export, protected by an admin login.

### 3.3 Feasibility study
- **Technical:** Python, Flask and a browser are free and run on Windows. Only one dependency (Flask) is needed.
- **Economic:** No licence or hosting cost. Runs on existing hardware.
- **Operational:** Simple menus and confirmation messages; staff need no training beyond a short demo.

## 4. Requirements
### 4.1 Hardware
Any PC with 2 GB RAM and 200 MB free disk space.

### 4.2 Software
Windows 10/11, Python 3.9 or later, Flask 3.x, any modern browser (Chrome, Edge, Firefox).

### 4.3 Functional requirements
| ID | Requirement |
|---|---|
| FR1 | Admin signs in and out; unauthenticated users are redirected to the login page |
| FR2 | Admin can add, view, search, edit and delete books |
| FR3 | Admin can register, view, search, edit and remove students |
| FR4 | Admin can issue a book to a student for 1 to 60 days (default 14) |
| FR5 | Admin can return a book; the system records the return date and fine |
| FR6 | The system shows available copies for each book |
| FR7 | The system lists overdue loans and the fine accrued |
| FR8 | The system keeps a searchable loan history |
| FR9 | The system shows reports and charts |
| FR10 | Books, students, history and overdue lists can be exported to CSV |
| FR11 | Admin can change the password |

### 4.4 Non-functional requirements
- **Usability:** responsive layout, clear error messages, confirmation before destructive actions.
- **Reliability:** atomic file writes, recovery from a corrupted data file.
- **Security:** hashed passwords, CSRF tokens, escaped output, login lock-out, CSV formula-injection protection.
- **Portability:** no external database; the `data/` folder can be copied or backed up as is.
- **Maintainability:** one `app.py`, separate templates, CSS and JavaScript, automated tests.

## 5. System Design
### 5.1 Architecture
```
Browser (HTML, CSS, JavaScript)
        |  HTTP (forms, CSV downloads)
Flask application (routes, validation, business rules)
        |  Store class (lock + atomic write)
JSON files: books.json, students.json, transactions.json, admins.json
```
The design follows a simple three-layer pattern: presentation (Jinja2 templates, CSS, JS), logic (Flask routes and
helper functions) and data (JSON store).

### 5.2 Data design
Each file holds a JSON list of objects. `id` values are auto-incremented integers.

**books.json**
| Field | Type | Notes |
|---|---|---|
| id | int | primary key, displayed as BK0001 |
| title, author | string | required |
| isbn | string | 10 or 13 characters, unique |
| category | string | one of a fixed list |
| copies | int | total copies owned (1 to 1000) |
| added_on | date | YYYY-MM-DD |

**students.json**
| Field | Type | Notes |
|---|---|---|
| id | int | displayed as ST0001 |
| name | string | 2 to 80 characters |
| roll_no | string | unique, upper-case |
| email | string | unique, lower-case |
| phone | string | 10 digits |
| department | string | one of a fixed list |
| registered_on | date | |

**transactions.json**
| Field | Type | Notes |
|---|---|---|
| id | int | |
| book_id, student_id | int | references |
| book_title, category, student_name, roll_no | string | snapshot so history survives deletions |
| issued_on, due_on | date | |
| returned_on | date or null | null means the book is still out |
| fine, overdue_days | number | stored when the book is returned |

**admins.json** – `username` and a salted PBKDF2-SHA256 `password_hash`.

### 5.3 Entity relationship
```
 STUDENT 1 ----< TRANSACTION >---- 1 BOOK
```
One student can have many loans; one book can appear in many loans. *Available copies* is not stored; it is derived as
`copies - number of transactions for that book with returned_on = null`, so it can never go out of sync.

### 5.4 Data flow (issue a book)
1. Admin selects student, book and loan days.
2. System validates the inputs and checks the rules in section 6.
3. If valid, a transaction with `due_on = today + days` is appended and saved; availability drops by one.
4. If invalid, the form is shown again with all reasons.

### 5.5 User interface design
A dark-green sidebar holds the navigation (it becomes a slide-in menu below 860 px width). The dashboard opens with
five summary tiles, a shelf-use meter showing the share of copies on loan, shortcuts for common actions, the most
overdue loans and recent activity. Tables hide secondary columns on small screens. Status badges use colour and text
(Issued, Overdue, Returned) so they are readable without colour.

## 6. Modules and Business Rules
### 6.1 Authentication
Passwords are hashed with PBKDF2-SHA256. After five wrong attempts from one address, login is blocked for five minutes.
Every POST form carries a CSRF token. The `next` redirect parameter only accepts local paths.

### 6.2 Book management
Validation: title and author required, ISBN of 10 digits (last may be X) or 13 digits, duplicate ISBN rejected, category
from the list, copies from 1 to 1000. A book cannot be deleted while any copy is on loan, and its total cannot be set
below the number currently on loan.

### 6.3 Student management
Validation: name 2 to 80 characters, roll number 3 to 20 letters, digits, `-` or `/`, valid e-mail, 10-digit phone,
department from the list; roll number and e-mail must be unique. A student with unreturned books cannot be removed.

### 6.4 Issue rules
A loan is refused when: the student or book does not exist; the loan period is outside 1 to 60 days; no copy is
available; the student already holds the same title; the student already holds 3 books; or the student has an overdue
book.

### 6.5 Return and overdue fee
```
days_late = max( (return_date - due_date).days , 0 )
fee       = days_late x FINE_PER_DAY            (default 2.00 per day)
```
For an open loan, the current date is used, so the overdue page always shows the fee accrued so far. When the book is
returned the final days and fee are stored, so later changes to the rate do not alter past records.

### 6.6 History and reports
History can be searched by book, student or roll number and filtered by status. Reports show loans per month (last six
months), loans by category, most borrowed books, most active students, fines collected and fines outstanding.

### 6.7 CSV export
Four exports are provided. Files are UTF-8 with a byte-order mark so Excel opens currency symbols and accents correctly.
Cells beginning with `=`, `+`, `-` or `@` are prefixed with an apostrophe to prevent spreadsheet formula injection.

### 6.8 Error handling
Form errors appear beside the field. Rule violations appear as flash messages. Unknown pages return a friendly 404 page,
and unexpected failures return a 500 page without exposing a stack trace. A damaged JSON file is copied to
`*.json.corrupt` and the app continues with an empty list instead of crashing. Saves are written to a temporary file and
then swapped in, so a crash during saving cannot leave half a file.

## 7. Implementation
| Component | File | Role |
|---|---|---|
| Application | `app.py` | routes, validation, JSON store, fee calculation |
| Templates | `templates/*.html` | pages built with Jinja2 inheritance (`base.html`, shared `form.html`) |
| Styles | `static/css/style.css` | responsive layout, colour tokens |
| Scripts | `static/js/app.js` | menu toggle, live table filter, confirmations, availability and due-date preview, double-submit guard |
| Sample data | `generate_sample_data.py` | demo books, students and loans |
| Tests | `tests/test_app.py` | automated test suite |
| Windows launchers | `run.bat`, `run_tests.bat`, `reset_sample_data.bat` | one-click start, test and reset |

Technology choices: Flask keeps the code small and readable; JSON files satisfy the "no database application"
requirement and are easy to inspect and back up; the store class is the only code that touches files, so it could be
swapped for SQLite later without changing the routes.

## 8. Testing
### 8.1 Strategy
Unit tests cover the fee function. Integration tests drive the real Flask routes with a test client against a temporary
data folder, so the real data is never touched. Every test creates a fresh folder.

### 8.2 Test cases
| Area | Case | Expected result | Result |
|---|---|---|---|
| Fee | on time, early, 5 days late, open loan | 0, 0, 5 x rate, uses today | Pass |
| Auth | pages without login | redirect to login | Pass |
| Auth | wrong password; 5 wrong attempts | message; HTTP 429 lock-out | Pass |
| Auth | POST without CSRF token | HTTP 400 | Pass |
| Auth | `next=//evil.example` | not followed | Pass |
| Auth | change password rules | weak/wrong rejected, new one works | Pass |
| Books | add, edit, delete, search | saved and listed | Pass |
| Books | empty title, bad ISBN, 0 copies, bad category | 4 field errors, nothing saved | Pass |
| Books | duplicate ISBN | rejected | Pass |
| Books | `<script>` in title | escaped in HTML | Pass |
| Books | delete / reduce copies while on loan | refused | Pass |
| Students | register, normalise roll no. and e-mail | stored upper / lower case | Pass |
| Students | bad inputs; duplicate roll no. / e-mail | rejected | Pass |
| Students | delete with active loan | refused | Pass |
| Issue | issue then return | availability 1/2 then 2/2 | Pass |
| Issue | no copies left | refused, no record | Pass |
| Issue | same book twice; 4th book; bad ids; 0 days | refused | Pass |
| Issue | student with overdue book | refused | Pass |
| Return | 5 days late, rate 2.00 | fine 10.00, days 5 | Pass |
| Return | return twice; unknown loan | message; 404 | Pass |
| History | filter by text and status | correct rows | Pass |
| Reports | all pages render empty and with data | HTTP 200 | Pass |
| CSV | four exports; unknown kind | CSV headers, correct counts; 404 | Pass |
| CSV | title `=HYPERLINK(...)` | prefixed with `'` | Pass |
| Robustness | unknown URL; wrong method | 404 page; 405 | Pass |
| Robustness | corrupted JSON | recovers, `.corrupt` copy kept | Pass |
| Robustness | unexpected exception | friendly 500 page, no traceback | Pass |
| Robustness | saving | no leftover temp files | Pass |

### 8.3 Results
`python -m unittest discover -s tests` ran **38 tests, 0 failures, 0 errors**. A second smoke test started the real
server with the sample data, signed in over HTTP and loaded every page and CSV export successfully. Two defects were
found and fixed during testing: the navigation badge could break the error page when the data store failed, and one
test asserted on text that also appeared in a flash message.

*Not covered by automation:* visual appearance on physical devices and behaviour under many simultaneous users.
Capture screenshots of each page on desktop and phone to include in your submission.

## 9. User Manual (summary)
1. **Start:** double-click `run.bat`; sign in with `admin` / `admin123`; change the password under *Account*.
2. **Add books:** Books, Add book, fill the form, Save book.
3. **Register students:** Students, Register student.
4. **Issue:** Issue a book, choose student and book, check the due date, Issue book.
5. **Return:** Return books, press Return beside the loan and confirm; any fine is shown.
6. **Check lateness:** Overdue shows days late and fines; the sidebar badge shows the count.
7. **Reports and export:** Reports shows charts; every list has an Export CSV button.

## 10. Limitations
- Single-library, admin-only system; students cannot log in or reserve books.
- JSON files are fine for thousands of records but not for very large libraries or many concurrent writers.
- Fines are calculated and recorded, but payment collection is not tracked separately.
- One default admin account; there is no role management.
- The built-in Flask server is meant for local use, not for the public internet.

## 11. Future Enhancements
Student portal and book reservation; barcode or QR scanning; e-mail / SMS due-date reminders; fine payment tracking
and receipts; renewals; multiple admin roles; PDF reports; migration of the store to SQLite for larger data; deployment
behind a production server with HTTPS.

## 12. Conclusion
Library Desk meets every stated objective: secure login, book CRUD, student registration, rule-based issue and return,
live availability, automatic overdue fees, history, reports, CSV export and a responsive interface, using only Flask and
local JSON files. The automated tests give confidence that business rules and error handling behave as specified, and
the clear separation between routes, store, templates and tests makes the system easy to extend.

## 13. References
1. Flask documentation – https://flask.palletsprojects.com/
2. Jinja2 documentation – https://jinja.palletsprojects.com/
3. Python `json`, `csv` and `unittest` modules – https://docs.python.org/3/
4. Werkzeug security helpers – https://werkzeug.palletsprojects.com/
5. OWASP Cheat Sheets (CSRF, Password Storage, CSV Injection) – https://cheatsheetseries.owasp.org/
6. MDN Web Docs, responsive design – https://developer.mozilla.org/

## Appendix A – Folder structure
```
library_management_system/
  app.py  generate_sample_data.py  requirements.txt  README.md  REPORT.md
  run.bat  run_tests.bat  reset_sample_data.bat
  templates/   base, login, error, form, dashboard, books, students, issue, returns, overdue, history, reports
  static/css/style.css   static/js/app.js
  tests/test_app.py
  data/        books.json  students.json  transactions.json   (admins.json is created on first run)
```

## Appendix B – Main routes
| URL | Method | Purpose |
|---|---|---|
| `/login`, `/logout` | GET, POST | sign in / out |
| `/` | GET | dashboard |
| `/books`, `/books/new`, `/books/<id>/edit`, `/books/<id>/delete` | GET, POST | book CRUD |
| `/students`, `/students/new`, `/students/<id>/edit`, `/students/<id>/delete` | GET, POST | student management |
| `/issue`, `/return`, `/return/<id>` | GET, POST | circulation |
| `/overdue`, `/history`, `/reports` | GET | monitoring |
| `/export/<books|students|history|overdue>.csv` | GET | CSV download |
| `/account` | GET, POST | change password |
