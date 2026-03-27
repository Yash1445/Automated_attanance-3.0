#!/usr/bin/env python3
"""
Test script to verify attendance storage in PostgreSQL database
"""

import sys
import os
from datetime import date
from app import app, db
from models import Student, Attendance, Admin

def check_database():
    """Check database connectivity and current records"""
    with app.app_context():
        try:
            # Test connection
            result = db.session.execute(db.text("SELECT 1"))
            print("✓ Database connection successful!")
            
            # Check admins table
            admins_count = Admin.query.count()
            print(f"✓ Admins in database: {admins_count}")
            
            # Check students table
            students = Student.query.all()
            print(f"✓ Students in database: {len(students)}")
            if students:
                for student in students:
                    print(f"  - ID: {student.id}, Name: {student.name}, Roll: {student.roll_no}")
            
            # Check today's attendance
            today = date.today()
            today_attendance = Attendance.query.filter_by(date=today).all()
            print(f"\n✓ Attendance records for today ({today}):")
            if today_attendance:
                for record in today_attendance:
                    student = Student.query.get(record.student_id)
                    print(f"  - ID: {record.id}, Student: {student.name} ({student.roll_no}), Time: {record.time}, Status: {record.status}")
            else:
                print("  (No records found)")
            
            # Check all attendance records
            all_attendance = Attendance.query.count()
            print(f"\n✓ Total attendance records in database: {all_attendance}")
            
            return True
            
        except Exception as e:
            print(f"✗ Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    check_database()
