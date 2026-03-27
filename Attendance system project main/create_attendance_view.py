#!/usr/bin/env python3
"""
Create PostgreSQL VIEW for attendance with student details
This creates attendance_with_details view so admins can see names and roll numbers
"""

from app import app, db
from sqlalchemy import text

def create_attendance_view():
    """Create a PostgreSQL view to show attendance with student details"""
    
    sql_view = """
    DROP VIEW IF EXISTS attendance_with_details CASCADE;
    
    CREATE VIEW attendance_with_details AS
    SELECT 
        a.id as attendance_id,
        s.id as student_id,
        s.name as student_name,
        s.roll_no as roll_number,
        s.department,
        a.date as attendance_date,
        a.time as attendance_time,
        a.status
    FROM attendance a
    INNER JOIN students s ON a.student_id = s.id
    ORDER BY a.date DESC, a.time DESC;
    """
    
    try:
        with app.app_context():
            # Execute the SQL
            db.session.execute(text(sql_view))
            db.session.commit()
            print("✓ View 'attendance_with_details' created successfully!")
            print("\nNow in pgAdmin:")
            print("  1. Go to Schemas > public > Views")
            print("  2. You'll see 'attendance_with_details'")
            print("  3. Right-click > View/Edit Data > All Rows")
            print("\nYou'll see:")
            print("  - attendance_id")
            print("  - student_id")
            print("  - student_name ← NAME")
            print("  - roll_number ← ROLL NUMBER")
            print("  - department")
            print("  - attendance_date")
            print("  - attendance_time")
            print("  - status")
            return True
    except Exception as e:
        print(f"✗ Error creating view: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Creating PostgreSQL View for Attendance Details...")
    print("=" * 60)
    create_attendance_view()
