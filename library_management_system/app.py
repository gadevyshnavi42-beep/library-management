"""Library Desk - Library Management System.

Flask application that stores everything in local JSON files (no database server).
Run with:  python app.py   ->  http://127.0.0.1:5000
"""
import csv
import hmac
import io
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
from collections import Counter
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, Response, abort, flash, redirect, render_template,
                   request, session, url_for)
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATE_FMT = "%Y-%m-%d"
CATEGORIES = ["Computer Science", "Engineering", "Mathematics", "Science", "Literature",
              "History", "Business", "Reference", "Other"]
DEPARTMENTS = ["Computer Science", "Information Technology", "Electronics", "Mechanical",
               "Civil", "Electrical", "Business Administration", "Science & Humanities"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
ISBN_RE = re.compile(r"^(\d{9}[\dX]|\d{13})$")
ROLL_RE = re.compile(r"^[A-Za-z0-9/_-]{3,20}$")
PHONE_RE = re.compile(r"^\d{10}$")


# --------------------------------------------------------------------------- helpers
def parse_date(text):
    return datetime.strptime(text, DATE_FMT).date()


def calc_overdue(due_on, returned_on=None, rate=2.0, today=None):
    """Return (days_overdue, fee). Open loans are measured up to `today`."""
    end = parse_date(returned_on) if returned_on else (today or date.today())
    days = max((end - parse_date(due_on)).days, 0)
    return days, round(days * rate, 2)


def find(items, item_id):
    return next((i for i in items if i["id"] == item_id), None)


def with_stock(books, tx):
    out = Counter(t["book_id"] for t in tx if not t.get("returned_on"))
    return [dict(b, issued=out[b["id"]], available=b["copies"] - out[b["id"]]) for b in books]


def safe_cell(value):
    """Neutralise spreadsheet formula injection in CSV exports."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


class Store:
    """Tiny JSON-file store with atomic writes and corrupt-file recovery."""
    NAMES = ("books", "students", "transactions", "admins")

    def __init__(self, directory):
        self.dir = directory
        os.makedirs(directory, exist_ok=True)
        self.lock = threading.RLock()

    def _path(self, name):
        if name not in self.NAMES:
            raise KeyError(name)
        return os.path.join(self.dir, name + ".json")

    def load(self, name):
        path = self._path(name)
        with self.lock:
            if not os.path.exists(path):
                return []
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                if not isinstance(data, list):
                    raise ValueError("expected a JSON list")
                return data
            except (ValueError, OSError):
                try:
                    shutil.copy2(path, path + ".corrupt")  # keep the damaged file
                except OSError:
                    pass
                return []

    def save(self, name, data):
        path = self._path(name)
        with self.lock:
            fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2, ensure_ascii=False)
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)

    @staticmethod
    def next_id(items):
        return max((i["id"] for i in items), default=0) + 1


# --------------------------------------------------------------------------- factory
def create_app(data_dir=None, test_config=None):
    app = Flask(__name__)
    app.config.update(
        DATA_DIR=data_dir or os.environ.get("LMS_DATA_DIR") or os.path.join(BASE_DIR, "data"),
        LOAN_DAYS=14, FINE_PER_DAY=2.0, MAX_LOANS=3, CURRENCY="₹",
        MAX_LOGIN_FAILS=5, LOCKOUT_MINUTES=5, MAX_CONTENT_LENGTH=64 * 1024,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)
    cfg = app.config.__getitem__

    store = Store(cfg("DATA_DIR"))
    app.store = store
    key_file = os.path.join(store.dir, ".secret_key")
    if not os.path.exists(key_file):
        with open(key_file, "w") as fh:
            fh.write(secrets.token_hex(32))
    with open(key_file) as fh:
        app.secret_key = os.environ.get("LMS_SECRET_KEY") or fh.read().strip()
    if not store.load("admins"):
        store.save("admins", [{"username": "admin",
                               "password_hash": generate_password_hash("admin123", method="pbkdf2:sha256")}])

    def fee_of(t, today=None):
        return calc_overdue(t["due_on"], t.get("returned_on"), cfg("FINE_PER_DAY"), today)

    def decorate(t):
        days, fee = fee_of(t)
        returned = bool(t.get("returned_on"))
        state = "Returned" if returned else ("Overdue" if days else "Issued")
        return dict(t, days=days, fee=t.get("fine", fee) if returned else fee, state=state)

    def csrf_token():
        return session.setdefault("csrf", secrets.token_hex(16))

    # ---- request hooks / template helpers
    @app.before_request
    def check_csrf():
        if request.method == "POST":
            sent = request.form.get("csrf_token", "").encode()
            if not sent or not hmac.compare_digest(sent, session.get("csrf", "").encode()):
                abort(400)

    @app.context_processor
    def inject():
        n = 0
        if session.get("admin"):
            try:  # never let the badge break a page (or the error page itself)
                n = sum(1 for t in store.load("transactions")
                        if not t.get("returned_on") and fee_of(t)[0] > 0)
            except Exception:
                n = 0
        return dict(csrf_token=csrf_token, overdue_count=n, fine_rate=cfg("FINE_PER_DAY"),
                    max_loans=cfg("MAX_LOANS"))

    @app.template_filter("bcode")
    def bcode(n):
        return f"BK{int(n):04d}"

    @app.template_filter("scode")
    def scode(n):
        return f"ST{int(n):04d}"

    @app.template_filter("money")
    def money(v):
        return f"{cfg('CURRENCY')}{float(v):,.2f}"

    @app.template_filter("dfmt")
    def dfmt(s):
        return parse_date(s).strftime("%d %b %Y") if s else "—"

    def login_required(view):
        @wraps(view)
        def wrapped(*a, **kw):
            if not session.get("admin"):
                return redirect(url_for("login", next=request.path if request.method == "GET" else None))
            return view(*a, **kw)
        return wrapped

    # ---- error handling
    MESSAGES = {400: "That request couldn't be verified. Reload the page and try again.",
                404: "We couldn't find that page.", 405: "That action isn't allowed here.",
                413: "The submitted data was too large.", 429: "Too many attempts. Please wait and retry."}

    @app.errorhandler(Exception)
    def handle_error(e):
        if isinstance(e, HTTPException):
            code = e.code or 500
        else:
            app.logger.exception("Unhandled error")
            code = 500
        msg = MESSAGES.get(code, "Something went wrong on our side. Your data was not changed.")
        return render_template("error.html", title="Error", code=code, message=msg), code

    # ---- auth
    attempts = {}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("admin"):
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            ip = request.remote_addr or "?"
            fails, until = attempts.get(ip, (0, None))
            if until and datetime.now() >= until:
                fails, until = 0, None
            if until:
                flash("Too many failed attempts. Try again in a few minutes.", "error")
                return render_template("login.html", title="Sign in"), 429
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            admin = next((a for a in store.load("admins")
                          if a["username"].lower() == username.lower()), None)
            if admin and check_password_hash(admin["password_hash"], password):
                attempts.pop(ip, None)
                session.clear()
                session["admin"] = admin["username"]
                nxt = request.args.get("next", "")
                if nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt:
                    return redirect(nxt)
                return redirect(url_for("dashboard"))
            fails += 1
            lock = datetime.now() + timedelta(minutes=cfg("LOCKOUT_MINUTES")) \
                if fails >= cfg("MAX_LOGIN_FAILS") else None
            attempts[ip] = (fails, lock)
            flash("Wrong username or password.", "error")
        return render_template("login.html", title="Sign in")

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        flash("You have been signed out.", "info")
        return redirect(url_for("login"))

    @app.route("/account", methods=["GET", "POST"])
    @login_required
    def account():
        fields = [dict(name="current", label="Current password", type="password", attrs={"required": "required"}),
                  dict(name="new", label="New password (8+ characters, letters and numbers)", type="password",
                       attrs={"required": "required", "minlength": 8}),
                  dict(name="confirm", label="Repeat new password", type="password", attrs={"required": "required"})]
        errors = {}
        if request.method == "POST":
            with store.lock:
                admins = store.load("admins")
                me = next(a for a in admins if a["username"] == session["admin"])
                cur, new, conf = (request.form.get(k, "") for k in ("current", "new", "confirm"))
                if not check_password_hash(me["password_hash"], cur):
                    errors["current"] = "Current password is wrong."
                if len(new) < 8 or not re.search(r"[A-Za-z]", new) or not re.search(r"\d", new):
                    errors["new"] = "Use at least 8 characters with letters and numbers."
                if new != conf:
                    errors["confirm"] = "The two passwords don't match."
                if not errors:
                    me["password_hash"] = generate_password_hash(new, method="pbkdf2:sha256")
                    store.save("admins", admins)
                    flash("Password updated.", "success")
                    return redirect(url_for("dashboard"))
        return render_template("form.html", title="Change password", fields=fields, values={}, errors=errors,
                               submit="Update password", cancel=url_for("dashboard")), (400 if errors else 200)

    # ---- dashboard
    @app.route("/")
    @login_required
    def dashboard():
        books, students, tx = store.load("books"), store.load("students"), store.load("transactions")
        active = [decorate(t) for t in tx if not t.get("returned_on")]
        overdue = sorted([t for t in active if t["days"] > 0], key=lambda t: -t["days"])
        copies = sum(b["copies"] for b in books)
        s = dict(titles=len(books), copies=copies, issued=len(active), available=copies - len(active),
                 students=len(students), overdue=len(overdue), outstanding=sum(t["fee"] for t in overdue),
                 pct=round(100 * len(active) / copies) if copies else 0)
        recent = [decorate(t) for t in sorted(tx, key=lambda t: -t["id"])[:6]]
        return render_template("dashboard.html", title="Dashboard", s=s, recent=recent, overdue=overdue[:5])

    # ---- books
    def book_fields():
        return [dict(name="title", label="Title", type="text", attrs={"required": "required", "maxlength": 150}),
                dict(name="author", label="Author", type="text", attrs={"required": "required", "maxlength": 100}),
                dict(name="isbn", label="ISBN (10 or 13 digits)", type="text",
                     attrs={"required": "required", "maxlength": 17}),
                dict(name="category", label="Category", type="select", options=CATEGORIES),
                dict(name="copies", label="Total copies", type="number",
                     attrs={"required": "required", "min": 1, "max": 1000})]

    def validate_book(form, books, issued=0, exclude=None):
        v = {k: form.get(k, "").strip() for k in ("title", "author", "isbn", "category", "copies")}
        e = {}
        if not v["title"] or len(v["title"]) > 150:
            e["title"] = "Enter a title (up to 150 characters)."
        if not v["author"] or len(v["author"]) > 100:
            e["author"] = "Enter an author (up to 100 characters)."
        isbn = re.sub(r"[-\s]", "", v["isbn"]).upper()
        if not ISBN_RE.match(isbn):
            e["isbn"] = "Enter a valid 10- or 13-digit ISBN."
        elif any(b["isbn"] == isbn and b["id"] != exclude for b in books):
            e["isbn"] = "A book with this ISBN already exists."
        else:
            v["isbn"] = isbn
        if v["category"] not in CATEGORIES:
            e["category"] = "Choose a category from the list."
        try:
            n = int(v["copies"])
        except ValueError:
            n = None
        if n is None or not 1 <= n <= 1000:
            e["copies"] = "Copies must be a whole number from 1 to 1000."
        elif n < issued:
            e["copies"] = f"{issued} cop{'y is' if issued == 1 else 'ies are'} on loan; the total can't be lower."
        else:
            v["copies"] = n
        return v, e

    @app.route("/books")
    @login_required
    def books_list():
        q = request.args.get("q", "").strip().lower()
        cat = request.args.get("category", "")
        rows = with_stock(store.load("books"), store.load("transactions"))
        if q:
            rows = [b for b in rows if q in f"{b['title']} {b['author']} {b['isbn']}".lower()]
        if cat:
            rows = [b for b in rows if b["category"] == cat]
        rows.sort(key=lambda b: b["title"].lower())
        return render_template("books.html", title="Books", books=rows, categories=CATEGORIES, q=q, cat=cat)

    @app.route("/books/new", methods=["GET", "POST"])
    @login_required
    def book_new():
        values, errors = {"category": CATEGORIES[0], "copies": 1}, {}
        if request.method == "POST":
            with store.lock:
                books = store.load("books")
                values, errors = validate_book(request.form, books)
                if not errors:
                    values["id"] = store.next_id(books)
                    values["added_on"] = date.today().strftime(DATE_FMT)
                    books.append(values)
                    store.save("books", books)
                    flash(f"Added “{values['title']}”.", "success")
                    return redirect(url_for("books_list"))
        return render_template("form.html", title="Add book", fields=book_fields(), values=values, errors=errors,
                               submit="Save book", cancel=url_for("books_list")), (400 if errors else 200)

    @app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
    @login_required
    def book_edit(book_id):
        with store.lock:
            books, tx = store.load("books"), store.load("transactions")
            book = find(books, book_id) or abort(404)
            issued = sum(1 for t in tx if t["book_id"] == book_id and not t.get("returned_on"))
            values, errors = dict(book), {}
            if request.method == "POST":
                values, errors = validate_book(request.form, books, issued, exclude=book_id)
                if not errors:
                    book.update(values)
                    store.save("books", books)
                    flash("Book updated.", "success")
                    return redirect(url_for("books_list"))
        return render_template("form.html", title="Edit book", fields=book_fields(), values=values, errors=errors,
                               submit="Save changes", cancel=url_for("books_list")), (400 if errors else 200)

    @app.route("/books/<int:book_id>/delete", methods=["POST"])
    @login_required
    def book_delete(book_id):
        with store.lock:
            books, tx = store.load("books"), store.load("transactions")
            book = find(books, book_id) or abort(404)
            if any(t["book_id"] == book_id and not t.get("returned_on") for t in tx):
                flash("This book has copies on loan. Return them before deleting it.", "error")
            else:
                store.save("books", [b for b in books if b["id"] != book_id])
                flash(f"Deleted “{book['title']}”. Its loan history is kept.", "success")
        return redirect(url_for("books_list"))

    # ---- students
    def student_fields():
        return [dict(name="name", label="Full name", type="text", attrs={"required": "required", "maxlength": 80}),
                dict(name="roll_no", label="Roll / register number", type="text",
                     attrs={"required": "required", "maxlength": 20}),
                dict(name="email", label="Email", type="email", attrs={"required": "required"}),
                dict(name="phone", label="Phone (10 digits)", type="tel",
                     attrs={"required": "required", "maxlength": 10, "pattern": "[0-9]{10}"}),
                dict(name="department", label="Department", type="select", options=DEPARTMENTS)]

    def validate_student(form, students, exclude=None):
        v = {k: form.get(k, "").strip() for k in ("name", "roll_no", "email", "phone", "department")}
        v["roll_no"] = v["roll_no"].upper()
        v["email"] = v["email"].lower()
        e = {}
        others = [s for s in students if s["id"] != exclude]
        if not 2 <= len(v["name"]) <= 80:
            e["name"] = "Enter a name of 2 to 80 characters."
        if not ROLL_RE.match(v["roll_no"]):
            e["roll_no"] = "Use 3-20 letters, numbers, - or /."
        elif any(s["roll_no"] == v["roll_no"] for s in others):
            e["roll_no"] = "This roll number is already registered."
        if not EMAIL_RE.match(v["email"]):
            e["email"] = "Enter a valid email address."
        elif any(s["email"] == v["email"] for s in others):
            e["email"] = "This email is already registered."
        if not PHONE_RE.match(v["phone"]):
            e["phone"] = "Enter a 10-digit phone number."
        if v["department"] not in DEPARTMENTS:
            e["department"] = "Choose a department from the list."
        return v, e

    @app.route("/students")
    @login_required
    def students_list():
        q = request.args.get("q", "").strip().lower()
        students, tx = store.load("students"), store.load("transactions")
        loans = Counter(t["student_id"] for t in tx if not t.get("returned_on"))
        rows = [dict(s, loans=loans[s["id"]]) for s in students
                if not q or q in f"{s['name']} {s['roll_no']} {s['email']}".lower()]
        rows.sort(key=lambda s: s["name"].lower())
        return render_template("students.html", title="Students", students=rows, q=q)

    @app.route("/students/new", methods=["GET", "POST"])
    @login_required
    def student_new():
        values, errors = {"department": DEPARTMENTS[0]}, {}
        if request.method == "POST":
            with store.lock:
                students = store.load("students")
                values, errors = validate_student(request.form, students)
                if not errors:
                    values["id"] = store.next_id(students)
                    values["registered_on"] = date.today().strftime(DATE_FMT)
                    students.append(values)
                    store.save("students", students)
                    flash(f"Registered {values['name']} as {scode(values['id'])}.", "success")
                    return redirect(url_for("students_list"))
        return render_template("form.html", title="Register student", fields=student_fields(), values=values,
                               errors=errors, submit="Register student",
                               cancel=url_for("students_list")), (400 if errors else 200)

    @app.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
    @login_required
    def student_edit(student_id):
        with store.lock:
            students = store.load("students")
            student = find(students, student_id) or abort(404)
            values, errors = dict(student), {}
            if request.method == "POST":
                values, errors = validate_student(request.form, students, exclude=student_id)
                if not errors:
                    student.update(values)
                    store.save("students", students)
                    flash("Student updated.", "success")
                    return redirect(url_for("students_list"))
        return render_template("form.html", title="Edit student", fields=student_fields(), values=values,
                               errors=errors, submit="Save changes",
                               cancel=url_for("students_list")), (400 if errors else 200)

    @app.route("/students/<int:student_id>/delete", methods=["POST"])
    @login_required
    def student_delete(student_id):
        with store.lock:
            students, tx = store.load("students"), store.load("transactions")
            student = find(students, student_id) or abort(404)
            if any(t["student_id"] == student_id and not t.get("returned_on") for t in tx):
                flash("This student still holds books. Return them first.", "error")
            else:
                store.save("students", [s for s in students if s["id"] != student_id])
                flash(f"Removed {student['name']}. Loan history is kept.", "success")
        return redirect(url_for("students_list"))

    # ---- issue / return
    def issue_page(selected=None, status=200):
        books, students, tx = store.load("books"), store.load("students"), store.load("transactions")
        return render_template("issue.html", title="Issue book", books=sorted(with_stock(books, tx),
                               key=lambda b: b["title"].lower()), students=sorted(students, key=lambda s: s["name"].lower()),
                               sel=selected or {}, loan_days=cfg("LOAN_DAYS")), status

    @app.route("/issue", methods=["GET", "POST"])
    @login_required
    def issue():
        if request.method == "GET":
            return issue_page()
        with store.lock:
            books, students, tx = store.load("books"), store.load("students"), store.load("transactions")
            try:
                sid, bid = int(request.form.get("student_id", "")), int(request.form.get("book_id", ""))
            except ValueError:
                sid = bid = None
            try:
                days = int(request.form.get("days") or cfg("LOAN_DAYS"))
            except ValueError:
                days = 0
            student, book = find(students, sid), find(books, bid)
            problems = []
            if not student:
                problems.append("Select a registered student.")
            if not book:
                problems.append("Select a book.")
            if not 1 <= days <= 60:
                problems.append("The loan period must be between 1 and 60 days.")
            if student and book and not problems:
                mine = [t for t in tx if t["student_id"] == sid and not t.get("returned_on")]
                if with_stock([book], tx)[0]["available"] < 1:
                    problems.append(f"No copies of “{book['title']}” are available right now.")
                if any(t["book_id"] == bid for t in mine):
                    problems.append(f"{student['name']} already has this book.")
                if len(mine) >= cfg("MAX_LOANS"):
                    problems.append(f"Limit reached: a student can hold {cfg('MAX_LOANS')} books at a time.")
                if any(fee_of(t)[0] > 0 for t in mine):
                    problems.append("This student has overdue books. Return them before borrowing more.")
            if problems:
                for p in problems:
                    flash(p, "error")
                return issue_page(dict(student_id=sid, book_id=bid, days=days), 400)
            today = date.today()
            tx.append(dict(id=store.next_id(tx), book_id=bid, student_id=sid, book_title=book["title"],
                           category=book["category"], student_name=student["name"], roll_no=student["roll_no"],
                           issued_on=today.strftime(DATE_FMT), due_on=(today + timedelta(days=days)).strftime(DATE_FMT),
                           returned_on=None, fine=0.0, overdue_days=0))
            store.save("transactions", tx)
        flash(f"Issued “{book['title']}” to {student['name']}. Due {dfmt(tx[-1]['due_on'])}.", "success")
        return redirect(url_for("issue"))

    @app.route("/return")
    @login_required
    def returns():
        rows = sorted((decorate(t) for t in store.load("transactions") if not t.get("returned_on")),
                      key=lambda t: t["due_on"])
        return render_template("returns.html", title="Return books", loans=rows)

    @app.route("/return/<int:tid>", methods=["POST"])
    @login_required
    def return_book(tid):
        with store.lock:
            tx = store.load("transactions")
            t = find(tx, tid) or abort(404)
            if t.get("returned_on"):
                flash("That loan was already returned.", "info")
                return redirect(url_for("returns"))
            days, fee = fee_of(t)
            t.update(returned_on=date.today().strftime(DATE_FMT), fine=fee, overdue_days=days)
            store.save("transactions", tx)
        msg = f"Returned “{t['book_title']}”."
        if fee:
            msg += f" Late by {days} day{'s' if days != 1 else ''}: fine {cfg('CURRENCY')}{fee:,.2f}."
        flash(msg, "success")
        return redirect(url_for("returns"))

    @app.route("/overdue")
    @login_required
    def overdue():
        phones = {s["id"]: s.get("phone", "") for s in store.load("students")}
        rows = sorted((dict(t, phone=phones.get(t["student_id"], "")) for t in map(decorate, store.load("transactions"))
                       if t["state"] == "Overdue"), key=lambda t: -t["days"])
        return render_template("overdue.html", title="Overdue", loans=rows, total=sum(t["fee"] for t in rows))

    @app.route("/history")
    @login_required
    def history():
        q = request.args.get("q", "").strip().lower()
        status = request.args.get("status", "")
        rows = [decorate(t) for t in sorted(store.load("transactions"), key=lambda t: -t["id"])]
        if q:
            rows = [t for t in rows if q in f"{t['book_title']} {t['student_name']} {t['roll_no']}".lower()]
        if status in ("Issued", "Returned", "Overdue"):
            rows = [t for t in rows if t["state"] == status]
        return render_template("history.html", title="History", rows=rows, q=q, status=status)

    # ---- reports
    @app.route("/reports")
    @login_required
    def reports():
        tx = store.load("transactions")
        rows = [decorate(t) for t in tx]
        months = []
        d = date.today().replace(day=1)
        for _ in range(6):
            months.insert(0, d.strftime("%Y-%m"))
            d = (d - timedelta(days=1)).replace(day=1)
        per_month = Counter(t["issued_on"][:7] for t in tx)
        data = dict(
            by_month=[(datetime.strptime(m, "%Y-%m").strftime("%b %Y"), per_month[m]) for m in months],
            by_cat=Counter(t.get("category", "Other") for t in tx).most_common(),
            top_books=Counter(t["book_title"] for t in tx).most_common(5),
            top_students=Counter(t["student_name"] for t in tx).most_common(5),
            collected=sum(t["fee"] for t in rows if t["state"] == "Returned"),
            outstanding=sum(t["fee"] for t in rows if t["state"] == "Overdue"),
            total=len(tx), active=sum(1 for t in rows if t["state"] != "Returned"),
            late_returns=sum(1 for t in rows if t["state"] == "Returned" and t["fee"] > 0))
        return render_template("reports.html", title="Reports", r=data)

    # ---- CSV export
    def export_rows(kind):
        books, students, tx = store.load("books"), store.load("students"), store.load("transactions")
        if kind == "books":
            return (["Book ID", "ISBN", "Title", "Author", "Category", "Total copies", "On loan", "Available"],
                    [[bcode(b["id"]), b["isbn"], b["title"], b["author"], b["category"], b["copies"],
                      b["issued"], b["available"]] for b in with_stock(books, tx)])
        if kind == "students":
            loans = Counter(t["student_id"] for t in tx if not t.get("returned_on"))
            return (["Student ID", "Name", "Roll no", "Email", "Phone", "Department", "Registered", "Books held"],
                    [[scode(s["id"]), s["name"], s["roll_no"], s["email"], s["phone"], s["department"],
                      s.get("registered_on", ""), loans[s["id"]]] for s in students])
        if kind in ("history", "overdue"):
            rows = [decorate(t) for t in tx]
            if kind == "overdue":
                rows = [t for t in rows if t["state"] == "Overdue"]
            return (["Loan ID", "Book", "Student", "Roll no", "Issued", "Due", "Returned", "Days late",
                     "Fine", "Status"],
                    [[t["id"], t["book_title"], t["student_name"], t["roll_no"], t["issued_on"], t["due_on"],
                      t.get("returned_on") or "", t["days"], f"{t['fee']:.2f}", t["state"]] for t in rows])
        abort(404)

    @app.route("/export/<kind>.csv")
    @login_required
    def export(kind):
        header, rows = export_rows(kind)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(header)
        writer.writerows([[safe_cell(c) for c in r] for r in rows])
        name = f"library_{kind}_{date.today():%Y%m%d}.csv"
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={name}"})

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
