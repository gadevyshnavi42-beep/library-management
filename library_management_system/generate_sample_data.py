"""Create demo data (books, students, loans) with dates relative to today.

Usage:  python generate_sample_data.py          (writes to ./data, keeps existing files)
        python generate_sample_data.py --reset  (overwrites books/students/transactions)
"""
import os
import sys
from datetime import date, timedelta

from app import DATE_FMT, Store

BOOKS = [
    ("Introduction to Algorithms", "Thomas H. Cormen", "9780262033848", "Computer Science", 4),
    ("Clean Code", "Robert C. Martin", "9780132350884", "Computer Science", 3),
    ("Fluent Python", "Luciano Ramalho", "9781492056355", "Computer Science", 2),
    ("Database System Concepts", "Abraham Silberschatz", "9780078022159", "Computer Science", 3),
    ("Computer Networks", "Andrew S. Tanenbaum", "9780132126953", "Computer Science", 2),
    ("Engineering Mechanics", "R. K. Bansal", "9788131808146", "Engineering", 5),
    ("Higher Engineering Mathematics", "B. S. Grewal", "9788174091550", "Mathematics", 6),
    ("Concepts of Physics", "H. C. Verma", "9788177091878", "Science", 4),
    ("A Brief History of Time", "Stephen Hawking", "9780553380163", "Science", 2),
    ("Wings of Fire", "A. P. J. Abdul Kalam", "9788173711466", "Literature", 3),
    ("The Discovery of India", "Jawaharlal Nehru", "9780143031031", "History", 2),
    ("Principles of Management", "Harold Koontz", "9780070620278", "Business", 3),
]
STUDENTS = [
    ("Aarav Sharma", "CS21B001", "aarav.sharma@college.edu", "9876500001", "Computer Science"),
    ("Meera Nair", "CS21B014", "meera.nair@college.edu", "9876500002", "Computer Science"),
    ("Rohan Verma", "ME21B022", "rohan.verma@college.edu", "9876500003", "Mechanical"),
    ("Sneha Iyer", "IT21B009", "sneha.iyer@college.edu", "9876500004", "Information Technology"),
    ("Karthik Raman", "EC21B031", "karthik.raman@college.edu", "9876500005", "Electronics"),
    ("Fatima Khan", "BA21B005", "fatima.khan@college.edu", "9876500006", "Business Administration"),
]
# (student index, book index, days ago issued, loan days, returned after N days or None)
LOANS = [
    (0, 0, 60, 14, 12), (1, 1, 50, 14, 20), (2, 5, 45, 14, 14), (3, 6, 40, 14, 9),
    (4, 7, 35, 14, 30), (5, 11, 30, 14, 10), (0, 2, 25, 14, 13), (1, 9, 20, 14, 15),
    (0, 3, 20, 14, None),   # overdue by 6 days
    (2, 4, 5, 14, None),    # on time
    (3, 8, 18, 14, None),   # overdue by 4 days
    (4, 1, 3, 14, None),    # on time
]


def main(reset=False):
    store = Store(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
    if not reset and (store.load("books") or store.load("students")):
        print("Data already exists. Use --reset to overwrite.")
        return
    today = date.today()
    books = [dict(id=i + 1, title=t, author=a, isbn=n, category=c, copies=k,
                  added_on=(today - timedelta(days=120)).strftime(DATE_FMT)) for i, (t, a, n, c, k) in enumerate(BOOKS)]
    students = [dict(id=i + 1, name=n, roll_no=r, email=e, phone=p, department=d,
                     registered_on=(today - timedelta(days=100)).strftime(DATE_FMT))
                for i, (n, r, e, p, d) in enumerate(STUDENTS)]
    tx = []
    for i, (si, bi, ago, loan, ret) in enumerate(LOANS, start=1):
        issued, b, s = today - timedelta(days=ago), books[bi], students[si]
        due = issued + timedelta(days=loan)
        row = dict(id=i, book_id=b["id"], student_id=s["id"], book_title=b["title"], category=b["category"],
                   student_name=s["name"], roll_no=s["roll_no"], issued_on=issued.strftime(DATE_FMT),
                   due_on=due.strftime(DATE_FMT), returned_on=None, fine=0.0, overdue_days=0)
        if ret is not None:
            back = issued + timedelta(days=ret)
            late = max((back - due).days, 0)
            row.update(returned_on=back.strftime(DATE_FMT), overdue_days=late, fine=round(late * 2.0, 2))
        tx.append(row)
    store.save("books", books)
    store.save("students", students)
    store.save("transactions", tx)
    print(f"Wrote {len(books)} books, {len(students)} students, {len(tx)} loans.")


if __name__ == "__main__":
    main("--reset" in sys.argv)
