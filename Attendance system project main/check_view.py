#!/usr/bin/env python3
"""
Check if attendance_with_details view exists and display it
"""

from app import app, db
from sqlalchemy import text

def check_and_display_view():
    """Check if view exists and show the data"""
    
    try:
        with app.app_context():
            # Check if view exists
            check_view = """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.views 
                WHERE table_name = 'attendance_with_details'
            ) as view_exists;
            """
            
            result = db.session.execute(text(check_view)).fetchone()
            view_exists = result[0] if result else False
            
            if view_exists:
                print("✓ View 'attendance_with_details' EXISTS in database!")
                print("\n" + "="*80)
                print("ATTENDANCE WITH STUDENT DETAILS:")
                print("="*80)
                
                # Query the view
                query_result = db.session.execute(text(
                    "SELECT * FROM attendance_with_details;"
                )).fetchall()
                
                if query_result:
                    # Print header
                    print(f"{'ID':<5} {'S_ID':<5} {'NAME':<20} {'ROLL':<15} {'DEPT':<15} {'DATE':<12} {'TIME':<14} {'STATUS':<10}")
                    print("-" * 100)
                    
                    # Print rows
                    for row in query_result:
                        attendance_id, student_id, name, roll, dept, date, time, status = row
                        print(f"{attendance_id:<5} {student_id:<5} {name:<20} {roll:<15} {dept:<15} {str(date):<12} {str(time):<14} {status:<10}")
                    
                    print("-" * 100)
                    print(f"Total records: {len(query_result)}")
                else:
                    print("(No attendance records yet)")
            else:
                print("✗ View does NOT exist. This shouldn't happen...")
                print("Attempting to create it again...")
                
                # Try to create it again
                create_view = """
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
                db.session.execute(text(create_view))
                db.session.commit()
                print("✓ View created successfully!")
                
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_and_display_view()
