from app import app, db
from sqlalchemy import text

with app.app_context():
    cols = db.session.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name='attendance' ORDER BY ordinal_position")
    ).fetchall()
    print("attendance columns:")
    print([c[0] for c in cols])

    rows = db.session.execute(
        text("SELECT id, student_id, student_name, roll_no, department, date, time, status FROM attendance ORDER BY id")
    ).fetchall()
    print("attendance rows:")
    for r in rows:
        print(r)
