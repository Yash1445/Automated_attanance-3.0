import os
import numpy as np
import cv2  # type: ignore
from datetime import datetime
from database import db
from models import Student, Attendance


def _build_face_encoding_from_folder(folder_path: str):
    if not os.path.isdir(folder_path):
        return None

    encodings = []
    for img_name in os.listdir(folder_path):
        if not img_name.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        img = cv2.imread(os.path.join(folder_path, img_name))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        gray = cv2.resize(gray, (50, 50))
        vec = gray.astype("float32").ravel() / 255.0
        encodings.append(vec)

    if not encodings:
        return None

    avg_encoding = np.mean(np.array(encodings, dtype=np.float32), axis=0)
    return avg_encoding.tobytes()


def save_student_with_encoding(roll_no, name, department="General", folder_path=None):
    student = Student.query.filter_by(roll_no=str(roll_no)).first()
    if student is None:
        student = Student(roll_no=str(roll_no), name=name, department=department)
        db.session.add(student)
    else:
        student.name = name
        student.department = department

    if folder_path:
        binary_encoding = _build_face_encoding_from_folder(folder_path)
        if binary_encoding is not None:
            student.face_encoding = binary_encoding

    db.session.commit()
    return student


def mark_attendance(student_id, status="Present"):
    today = datetime.now().date()
    existing = Attendance.query.filter_by(student_id=student_id, date=today).first()
    if existing:
        return existing, False

    record = Attendance(
        student_id=student_id,
        date=today,
        time=datetime.now().time(),
        status=status,
    )
    db.session.add(record)
    db.session.commit()
    return record, True
