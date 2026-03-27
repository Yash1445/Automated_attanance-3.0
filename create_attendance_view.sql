-- PostgreSQL View: attendance_with_details
-- This view shows attendance records with student name and roll number
-- Created for easier admin viewing

CREATE OR REPLACE VIEW attendance_with_details AS
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

-- Query to test the view:
-- SELECT * FROM attendance_with_details;
