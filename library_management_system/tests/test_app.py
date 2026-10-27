"""Automated tests. Run with:  python -m unittest discover -s tests -v"""
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from werkzeug.security import generate_password_hash  # noqa: E402
from app import DATE_FMT, calc_overdue, create_app  # noqa: E402

BOOK = dict(title="Clean Code", author="Robert Martin", isbn="978-0-13-235088-4",
            category="Computer Science", copies="2")
STUDENT = dict(name="Asha Rao", roll_no="cs21b100", email="Asha@College.edu", phone="9876543210",
               department="Computer Science")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # cheap hash keeps the test-suite fast; production uses the default work factor
        with open(os.path.join(self.tmp, "admins.json"), "w") as fh:
            json.dump([{"username": "admin",
                        "password_hash": generate_password_hash("admin123", method="pbkdf2:sha256:1000")}], fh)
        self.app = create_app(self.tmp, {"TESTING": True})
        self.store = self.app.store
        self.c = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def post(self, url, data=None, **kw):
        with self.c.session_transaction() as s:
            token = s.setdefault("csrf", "test-token")
        return self.c.post(url, data=dict(data or {}, csrf_token=token), **kw)

    def login(self, user="admin", pw="admin123"):
        return self.post("/login", dict(username=user, password=pw))

    def add_book(self, **over):
        return self.post("/books/new", dict(BOOK, **over))

    def add_student(self, **over):
        return self.post("/students/new", dict(STUDENT, **over))

    def seed(self, copies="2"):
        self.login()
        self.add_book(copies=copies)
        self.add_student()

    def issue(self, sid=1, bid=1, days="14"):
        return self.post("/issue", dict(student_id=sid, book_id=bid, days=days))


class TestHelpers(unittest.TestCase):
    def test_no_fee_when_on_time(self):
        d = date(2026, 1, 10).strftime(DATE_FMT)
        self.assertEqual(calc_overdue(d, "2026-01-10", 2.0), (0, 0.0))
        self.assertEqual(calc_overdue(d, "2026-01-05", 2.0), (0, 0.0))

    def test_fee_per_late_day(self):
        self.assertEqual(calc_overdue("2026-01-10", "2026-01-15", 2.5), (5, 12.5))

    def test_open_loan_uses_today(self):
        due = (date.today() - timedelta(days=3)).strftime(DATE_FMT)
        self.assertEqual(calc_overdue(due, None, 2.0), (3, 6.0))


class TestAuth(Base):
    def test_requires_login(self):
        for url in ("/", "/books", "/students", "/issue", "/reports", "/export/books.csv"):
            r = self.c.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/login", r.headers["Location"])

    def test_login_logout(self):
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.c.get("/").status_code, 200)
        self.post("/logout")
        self.assertEqual(self.c.get("/").status_code, 302)

    def test_bad_password(self):
        r = self.login(pw="nope")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Wrong username or password", r.data)

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.login(pw="bad")
        self.assertEqual(self.login().status_code, 429)

    def test_csrf_rejected(self):
        r = self.c.post("/login", data=dict(username="admin", password="admin123"))
        self.assertEqual(r.status_code, 400)

    def test_open_redirect_blocked(self):
        r = self.post("/login?next=//evil.example", dict(username="admin", password="admin123"))
        self.assertNotIn("evil.example", r.headers["Location"])

    def test_change_password(self):
        self.login()
        r = self.post("/account", dict(current="wrong", new="abc12345", confirm="abc12345"))
        self.assertEqual(r.status_code, 400)
        r = self.post("/account", dict(current="admin123", new="short", confirm="short"))
        self.assertEqual(r.status_code, 400)
        r = self.post("/account", dict(current="admin123", new="newpass99", confirm="newpass99"))
        self.assertEqual(r.status_code, 302)
        self.post("/logout")
        self.assertEqual(self.login(pw="admin123").status_code, 200)
        self.assertEqual(self.login(pw="newpass99").status_code, 302)


class TestBooks(Base):
    def test_crud(self):
        self.login()
        r = self.add_book()
        self.assertEqual(r.status_code, 302)
        book = self.store.load("books")[0]
        self.assertEqual((book["isbn"], book["copies"]), ("9780132350884", 2))
        self.assertIn(b"Clean Code", self.c.get("/books").data)
        r = self.post("/books/1/edit", dict(BOOK, title="Clean Code 2e", copies="5"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.store.load("books")[0]["title"], "Clean Code 2e")
        self.post("/books/1/delete")
        self.assertEqual(self.store.load("books"), [])

    def test_validation(self):
        self.login()
        r = self.add_book(title="", isbn="123", copies="0", category="Nope")
        self.assertEqual(r.status_code, 400)
        for msg in (b"Enter a title", b"valid 10- or 13-digit ISBN", b"1 to 1000", b"Choose a category"):
            self.assertIn(msg, r.data)
        self.assertEqual(self.store.load("books"), [])
        self.assertEqual(self.add_book(copies="abc").status_code, 400)

    def test_duplicate_isbn(self):
        self.login()
        self.add_book()
        r = self.add_book(isbn="9780132350884")
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"already exists", r.data)

    def test_html_is_escaped(self):
        self.login()
        self.add_book(title="<script>alert(1)</script>")
        self.assertNotIn(b"<script>alert(1)", self.c.get("/books").data)

    def test_cannot_delete_or_shrink_issued_book(self):
        self.seed()
        self.issue()
        self.post("/books/1/delete")
        self.assertEqual(len(self.store.load("books")), 1)  # delete refused while on loan
        r = self.post("/books/1/edit", dict(BOOK, copies="1"))  # exactly the number on loan is allowed
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.store.load("books")[0]["copies"], 1)

    def test_cannot_reduce_below_issued(self):
        self.seed(copies="3")
        self.add_student(roll_no="CS21B101", email="b@college.edu")
        self.issue(1, 1)
        self.issue(2, 1)
        r = self.post("/books/1/edit", dict(BOOK, copies="1"))
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"on loan", r.data)

    def test_missing_book_404(self):
        self.login()
        self.assertEqual(self.c.get("/books/99/edit").status_code, 404)


class TestStudents(Base):
    def test_register_and_normalise(self):
        self.login()
        self.assertEqual(self.add_student().status_code, 302)
        s = self.store.load("students")[0]
        self.assertEqual((s["roll_no"], s["email"]), ("CS21B100", "asha@college.edu"))

    def test_validation_and_duplicates(self):
        self.login()
        r = self.add_student(name="A", roll_no="!!", email="bad", phone="123")
        self.assertEqual(r.status_code, 400)
        self.add_student()
        r = self.add_student(email="other@college.edu")
        self.assertIn(b"roll number is already registered", r.data)
        r = self.add_student(roll_no="CS21B777")
        self.assertIn(b"email is already registered", r.data)

    def test_edit_and_delete(self):
        self.login()
        self.add_student()
        self.post("/students/1/edit", dict(STUDENT, name="Asha R"))
        self.assertEqual(self.store.load("students")[0]["name"], "Asha R")
        self.post("/students/1/delete")
        self.assertEqual(self.store.load("students"), [])

    def test_cannot_delete_student_with_loan(self):
        self.seed()
        self.issue()
        self.post("/students/1/delete")
        self.assertEqual(len(self.store.load("students")), 1)


class TestCirculation(Base):
    def test_issue_and_return_updates_availability(self):
        self.seed()
        self.assertEqual(self.issue().status_code, 302)
        self.assertIn(b"1 / 2", self.c.get("/books").data)
        tx = self.store.load("transactions")[0]
        self.assertEqual(tx["due_on"], (date.today() + timedelta(days=14)).strftime(DATE_FMT))
        self.assertEqual(self.post("/return/1").status_code, 302)
        self.assertIn(b"2 / 2", self.c.get("/books").data)
        self.assertEqual(self.store.load("transactions")[0]["fine"], 0)

    def test_no_copies_left(self):
        self.seed(copies="1")
        self.add_student(roll_no="CS21B101", email="b@college.edu")
        self.issue(1, 1)
        r = self.issue(2, 1)
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"No copies", r.data)
        self.assertEqual(len(self.store.load("transactions")), 1)

    def test_duplicate_loan_blocked(self):
        self.seed()
        self.issue()
        r = self.issue()
        self.assertIn(b"already has this book", r.data)

    def test_loan_limit(self):
        self.seed()
        for n, isbn in enumerate(("9780000000011", "9780000000028", "9780000000035"), start=2):
            self.add_book(title=f"Book {n}", isbn=isbn)
        books = self.store.load("books")
        self.assertEqual(len(books), 4)
        for b in books[:3]:
            self.assertEqual(self.issue(1, b["id"]).status_code, 302)
        r = self.issue(1, books[3]["id"])
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"Limit reached", r.data)

    def test_invalid_issue_inputs(self):
        self.seed()
        self.assertEqual(self.issue(99, 1).status_code, 400)
        self.assertEqual(self.issue(1, 99).status_code, 400)
        self.assertEqual(self.issue(1, 1, days="0").status_code, 400)
        self.assertEqual(self.issue("x", "y").status_code, 400)

    def test_overdue_fee_on_return(self):
        self.seed()
        self.issue()
        tx = self.store.load("transactions")
        tx[0]["issued_on"] = (date.today() - timedelta(days=20)).strftime(DATE_FMT)
        tx[0]["due_on"] = (date.today() - timedelta(days=5)).strftime(DATE_FMT)
        self.store.save("transactions", tx)
        self.assertIn(b"Overdue", self.c.get("/overdue").data)
        r = self.c.get("/overdue")
        self.assertIn("₹10.00".encode(), r.data)
        self.post("/return/1")
        t = self.store.load("transactions")[0]
        self.assertEqual((t["overdue_days"], t["fine"]), (5, 10.0))
        self.assertIn(b"No overdue books", self.c.get("/overdue").data)

    def test_overdue_blocks_new_issue(self):
        self.seed(copies="2")
        self.add_book(title="Other", isbn="9780000000001")
        self.issue(1, 1)
        tx = self.store.load("transactions")
        tx[0]["due_on"] = (date.today() - timedelta(days=2)).strftime(DATE_FMT)
        self.store.save("transactions", tx)
        r = self.issue(1, 2)
        self.assertIn(b"overdue", r.data)

    def test_double_return(self):
        self.seed()
        self.issue()
        self.post("/return/1")
        r = self.post("/return/1", follow_redirects=True)
        self.assertIn(b"already returned", r.data)
        self.assertEqual(self.post("/return/55").status_code, 404)

    def test_history_filters(self):
        self.seed()
        self.issue()
        self.assertIn(b"Clean Code", self.c.get("/history?q=cs21b100").data)
        self.assertNotIn(b"Clean Code", self.c.get("/history?q=zzz").data)
        self.assertNotIn(b"Clean Code", self.c.get("/history?status=Returned").data)
        self.post("/return/1")
        self.assertIn(b"Clean Code", self.c.get("/history?status=Returned").data)


class TestReportsAndExport(Base):
    def test_pages_render_empty_and_full(self):
        self.login()
        for url in ("/", "/reports", "/history", "/overdue", "/return", "/issue", "/books", "/students"):
            self.assertEqual(self.c.get(url).status_code, 200, url)
        self.seed()
        self.issue()
        for url in ("/", "/reports", "/history", "/overdue", "/return", "/issue"):
            self.assertEqual(self.c.get(url).status_code, 200, url)
        self.assertIn(b"Clean Code", self.c.get("/reports").data)

    def test_csv_exports(self):
        self.seed()
        self.issue()
        for kind in ("books", "students", "history", "overdue"):
            r = self.c.get(f"/export/{kind}.csv")
            self.assertEqual(r.status_code, 200)
            self.assertIn("text/csv", r.content_type)
            self.assertIn("attachment", r.headers["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(self.c.get("/export/books.csv").data.decode("utf-8-sig"))))
        self.assertEqual(rows[0][2], "Title")
        self.assertEqual((rows[1][2], rows[1][6], rows[1][7]), ("Clean Code", "1", "1"))
        self.assertEqual(self.c.get("/export/secrets.csv").status_code, 404)

    def test_csv_formula_injection_neutralised(self):
        self.login()
        self.add_book(title="=HYPERLINK(\"http://x\")")
        body = self.c.get("/export/books.csv").data.decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", body)


class TestRobustness(Base):
    def test_404_page(self):
        self.login()
        r = self.c.get("/nope")
        self.assertEqual(r.status_code, 404)
        self.assertIn(b"couldn", r.data)

    def test_wrong_method(self):
        self.login()
        self.assertEqual(self.c.get("/books/1/delete").status_code, 405)

    def test_corrupt_json_recovers(self):
        self.login()
        with open(os.path.join(self.tmp, "books.json"), "w") as fh:
            fh.write("{ not json")
        self.assertEqual(self.c.get("/books").status_code, 200)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "books.json.corrupt")))
        self.assertEqual(self.add_book().status_code, 302)

    def test_unexpected_error_shows_friendly_page(self):
        self.login()

        def boom(*a, **k):
            raise RuntimeError("boom")
        self.store.load = boom
        r = self.c.get("/books")
        self.assertEqual(r.status_code, 500)
        self.assertIn(b"went wrong", r.data)
        self.assertNotIn(b"Traceback", r.data)

    def test_atomic_save_leaves_no_temp_files(self):
        self.login()
        self.add_book()
        self.assertFalse([f for f in os.listdir(self.tmp) if f.endswith(".tmp")])


if __name__ == "__main__":
    unittest.main()
