#!/usr/bin/env python3
"""
View all attendance records in the database
"""

import sys
from datetime import date, datetime
from app import app, db
from models import Student, Attendance

def view_attendance():
    """Display all attendance records"""
    with app.app_context():
        try:
            # Get all attendance
            all_records = Attendance.query.all()
            
            print("=" * 80)
            print(f"Total Attendance Records: {len(all_records)}")
            print("=" * 80)
            
            for record in all_records:
                student = Student.query.get(record.student_id)
                print(f"ID: {record.id}")
                print(f"  Student: {student.name} (Roll: {student.roll_no})")
                print(f"  Date: {record.date}")
                print(f"  Time: {record.time}")
                print(f"  Status: {record.status}")
                print("-" * 40)
            
            # Show today's only
            today = date.today()
            today_records = Attendance.query.filter_by(date=today).all()
            print(f"\nToday's Attendance ({today}): {len(today_records)} record(s)")
            for record in today_records:
                student = Student.query.get(record.student_id)
                print(f"  - {student.name}: {record.time}")
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    view_attendance()
