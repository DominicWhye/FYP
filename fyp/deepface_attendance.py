import os
import cv2
import sqlite3
from datetime import datetime
from deepface import DeepFace


# =========================
# CONFIG
# =========================
STUDENT_IMAGES_DIR = "student_images"
DB_FILE = "attendance.db"
FRAME_SKIP = 20   # process every N frames to reduce lag
FACE_DETECTOR_BACKEND = "opencv"   # can try 'retinaface' later if installed
RETINA_FACE_BACKEND = "retinaface" 
MTCNN_FACE_BACKEND = "mtcnn"
MEDIAPIPE_FACE_BACKEND = "mediapipe"
MODEL_NAME = "Facenet512"
DISTANCE_METRIC = "cosine"
THRESHOLD = 0.35   # lower = stricter matching
CAMERA_IDS = [0, 1] # multi camera support (as of now we are testing 2 cams) # can add more cams in the future

# =========================
# DATABASE SETUP
# =========================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            student_name TEXT NOT NULL,
            image_path TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def load_students_into_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    if not os.path.exists(STUDENT_IMAGES_DIR):
        os.makedirs(STUDENT_IMAGES_DIR)
        print(f"Created folder: {STUDENT_IMAGES_DIR}")
        print("Put student images inside and run again.")
        conn.close()
        return

    files = os.listdir(STUDENT_IMAGES_DIR)

    for filename in files:
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            continue

        name_without_ext = os.path.splitext(filename)[0]
        parts = name_without_ext.split("_", 1)

        if len(parts) != 2:
            print(f"[SKIP] Invalid filename format: {filename}")
            print("Use format: studentid_name.jpg")
            continue

        student_id, student_name = parts[0], parts[1]
        image_path = os.path.join(STUDENT_IMAGES_DIR, filename)

        cursor.execute("""
            INSERT OR REPLACE INTO students (student_id, student_name, image_path)
            VALUES (?, ?, ?)
        """, (student_id, student_name, image_path))

    conn.commit()
    conn.close()


def get_all_students():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT student_id, student_name, image_path
        FROM students
        ORDER BY student_id
    """)

    rows = cursor.fetchall()
    conn.close()
    return rows


def mark_attendance(student_id, student_name, status="Present"):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT 1
        FROM attendance
        WHERE student_id = ?
          AND status = ?
          AND DATE(timestamp) = ?
    """, (student_id, status, today))

    already_marked = cursor.fetchone()

    if already_marked:
        conn.close()
        return False

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO attendance (student_id, student_name, timestamp, status)
        VALUES (?, ?, ?, ?)
    """, (student_id, student_name, now, status))

    conn.commit()
    conn.close()
    return True


def show_attendance_logs():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT student_id, student_name, timestamp, status
        FROM attendance
        ORDER BY timestamp DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No attendance records found.")
        return

    print("\nAttendance Logs:")
    print("-" * 80)
    for row in rows:
        print(f"Student ID: {row[0]} | Name: {row[1]} | Time: {row[2]} | Status: {row[3]}")
    print("-" * 80)


# =========================
# FACE MATCHING
# =========================
def verify_against_students(temp_capture_path, students):
    """
    Compare the captured face image against all registered students.
    Returns:
        (student_id, student_name, distance) if matched
        (None, None, None) otherwise
    """
    best_match = None
    best_distance = float("inf")

    for student_id, student_name, image_path in students:
        try:
            result = DeepFace.verify(
                img1_path=temp_capture_path,
                img2_path=image_path,
                model_name=MODEL_NAME,
                detector_backend=MTCNN_FACE_BACKEND,
                distance_metric=DISTANCE_METRIC,
                enforce_detection=True,
                silent=True
            )

            distance = result.get("distance", 999)

            if result.get("verified") and distance < best_distance and distance <= THRESHOLD:
                best_distance = distance
                best_match = (student_id, student_name, distance)

        except Exception:
            # ignore failed comparisons, e.g. no face found in one frame
            continue

    return best_match if best_match else (None, None, None)


# =========================
# WEBCAM SCANNER
# =========================
def run_attendance_scanner():
    students = get_all_students()

    if not students:
        print("No students found in database.")
        print("Please put images in student_images/ first.")
        return

    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)

    # Open multiple cameras
    caps = []
    for cam_id in CAMERA_IDS:
        cap = cv2.VideoCapture(cam_id)
        if cap.isOpened():
            caps.append((cam_id, cap))
        else:
            print(f"Warning: Could not open camera {cam_id}")

    if not caps:
        print("No webcams could be opened.")
        return

    print("\nStarting multi-camera DeepFace attendance scanner...")
    print("Press 'q' to quit.\n")

    frame_count = 0
    last_label = "Scanning..."
    last_color = (0, 255, 255)

    while True:
        frames = []
        display_frames = []

        # Read frames from all cameras
        for cam_id, cap in caps:
            ret, frame = cap.read()
            if not ret:
                frames.append((cam_id, None))
                display_frames.append((cam_id, None))
            else:
                frames.append((cam_id, frame))
                display_frames.append((cam_id, frame.copy()))

        frame_count += 1

        if frame_count % FRAME_SKIP == 0:
            results = []

            for cam_id, frame in frames:
                if frame is None:
                    continue

                temp_capture_path = os.path.join(temp_dir, f"current_frame_cam{cam_id}.jpg")
                cv2.imwrite(temp_capture_path, frame)

                try:
                    student_id, student_name, distance = verify_against_students(
                        temp_capture_path,
                        students
                    )

                    if student_id:
                        results.append((student_id, student_name, distance, cam_id))

                except Exception:
                    continue

            # =========================
            # VALIDATION / FUSION LOGIC
            # =========================
            if len(results) >= 2:
                ids = [r[0] for r in results]

                # all detected cameras agree on same student
                if len(set(ids)) == 1:
                    student_id, student_name, distance, _ = results[0]
                    newly_marked = mark_attendance(student_id, student_name, "Present")

                    if newly_marked:
                        print(f"[CONFIRMED BY MULTIPLE CAMERAS] {student_id} - {student_name} at {datetime.now().strftime('%H:%M:%S')}")
                    else:
                        print(f"[ALREADY MARKED TODAY] {student_id} - {student_name}")

                    last_label = f"{student_id} - {student_name} (confirmed)"
                    last_color = (0, 255, 0)

                else:
                    print("[CONFLICT] Cameras detected different students")
                    last_label = "Conflict between cameras"
                    last_color = (0, 165, 255)

            elif len(results) == 1:
                # only one camera got a match
                student_id, student_name, distance, cam_id = results[0]

                newly_marked = mark_attendance(student_id, student_name, "Present")

                if newly_marked:
                    print(f"[WEAK MATCH - CAM {cam_id}] {student_id} - {student_name} at {datetime.now().strftime('%H:%M:%S')}")
                else:
                    print(f"[ALREADY MARKED TODAY] {student_id} - {student_name}")

                last_label = f"{student_id} - {student_name} (cam {cam_id})"
                last_color = (255, 255, 0)

            else:
                last_label = "Unknown"
                last_color = (0, 0, 255)

        # Show all camera windows
        for cam_id, display_frame in display_frames:
            if display_frame is not None:
                cv2.putText(
                    display_frame,
                    last_label,
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    last_color,
                    2
                )
                cv2.imshow(f"DeepFace Attendance Prototype - Camera {cam_id}", display_frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    for _, cap in caps:
        cap.release()
    cv2.destroyAllWindows()


# =========================
# MAIN MENU
# =========================
def main():
    init_db()
    load_students_into_db()

    while True:
        print("\n=== DeepFace Facial Attendance Prototype ===")
        print("1. Start attendance scanner")
        print("2. Show attendance logs")
        print("3. Reload student images into database")
        print("4. Exit")

        choice = input("Enter choice: ").strip()

        if choice == "1":
            run_attendance_scanner()
        elif choice == "2":
            show_attendance_logs()
        elif choice == "3":
            load_students_into_db()
            print("Student database refreshed.")
        elif choice == "4":
            print("Exiting.")
            break
        else:
            print("Invalid choice. Please enter 1, 2, 3, or 4.")


if __name__ == "__main__":
    main()