# 🎓 Automated Face Recognition Attendance System

An AI-powered attendance system that automatically marks student attendance using **Facial Recognition**.

This project eliminates manual attendance systems and prevents proxy attendance by verifying each student’s face in real time.

---

## 🚀 Features

- 👤 Face Recognition based attendance
- 📷 Real-time webcam detection
- 🧠 AI-based face matching using face encodings
- 📊 Dashboard for attendance monitoring
- 🗄 PostgreSQL database storage
- 🧑‍💼 Admin dashboard for managing users
- 📋 Attendance logs and reports
- 🔐 Secure admin login system

---

## 🧠 Technologies Used

### Backend
- Python
- Flask
- OpenCV
- face_recognition (dlib)

### Frontend
- HTML
- CSS
- Bootstrap
- JavaScript

### Database
- PostgreSQL

---

## ⚙️ How the System Works

1. The camera captures the user's face.
2. OpenCV detects the face in the video frame.
3. The face is converted into a numerical encoding.
4. The encoding is compared with registered users.
5. If a match is found, attendance is automatically recorded.
6. The data is stored in the PostgreSQL database.
7. The dashboard updates the attendance log.

---

## 🗄 Database Structure

### Students Table

| Column | Description |
|------|-------------|
| id | Student ID |
| name | Student name |
| student_id | Unique student number |

### Attendance Table

| Column | Description |
|------|-------------|
| id | Attendance record ID |
| student_id | Linked student |
| date | Attendance date |
| time | Attendance time |
| status | Present/Absent |

---

## 🖥 System Dashboard

The web dashboard provides:

- Total registered users
- Today's attendance
- Absent students
- Attendance logs
- User management

---

## 📂 Project Structure
