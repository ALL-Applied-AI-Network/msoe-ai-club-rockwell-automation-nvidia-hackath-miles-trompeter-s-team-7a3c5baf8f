"""Watch a camera with a trained YOLO26 model and alert when a tank is low.

The camera sees several large tanks at once. The model labels each one
tank_good or tank_low. On startup the script waits for a frame where it can
see all the tanks and remembers where each one sits in the picture, so every
tank gets its own name, its own smoothing, and its own alert cooldown.

Alerts can show a pop-up window on this Windows computer, send an email,
or both (see ALERT_POPUP and ALERT_EMAIL below).

For email with Gmail you need an "app password" (a separate 16-character
password made in your Google account security settings, which requires
2-step verification). Never use your normal email password here.

Usage:
    1. Edit the settings in the EDIT THESE SETTINGS block below.
    2. Point the camera at all the tanks and run: python monitor_yolo.py
    3. Do not move the camera while it runs. If it gets moved, restart the script.
"""
import ctypes
import math
import smtplib
import sys
import threading
import time
from collections import deque
from email.message import EmailMessage

import cv2
from ultralytics import YOLO

# ======================= EDIT THESE SETTINGS =======================
CAMERA_SOURCE = "0"  # REPLACE WITH YOUR CAMERA: 0 FOR A USB WEBCAM, OR YOUR STREAM URL IN QUOTES (EXAMPLE: "rtsp://USER:PASSWORD@CAMERA_IP:554/stream1")
MODEL_PATH = "runs/detect/train/weights/best.pt"  # REPLACE WITH THE PATH TO YOUR TRAINED WEIGHTS FILE (OR YOUR TEAM'S SHARED MODEL)
NUMBER_OF_TANKS = 4  # REPLACE ONLY IF THE NUMBER OF TANKS IN THE CAMERA VIEW IS NOT 4
TANK_NAMES = ["Tank 1", "Tank 2", "Tank 3", "Tank 4"]  # REPLACE WITH YOUR REAL TANK NAMES, LISTED LEFT TO RIGHT AS THEY APPEAR IN THE CAMERA VIEW (MUST HAVE ONE NAME PER TANK)
LOW_CLASS = "tank_low"  # REPLACE WITH THE EXACT CLASS NAME YOUR MODEL USES FOR A LOW TANK
GOOD_CLASS = "tank_good"  # REPLACE WITH THE EXACT CLASS NAME YOUR MODEL USES FOR A TANK THAT IS GOOD
ALERT_POPUP = True  # REPLACE WITH False IF YOU DON'T WANT A POP-UP WINDOW ON THIS COMPUTER (WINDOWS ONLY)
ALERT_EMAIL = False  # REPLACE WITH True TO ALSO SEND EMAIL ALERTS (THEN FILL IN THE EMAIL_ SETTINGS BELOW)
EMAIL_SENDER = "your.sender@gmail.com"  # REPLACE WITH THE EMAIL ADDRESS THAT WILL SEND THE ALERTS
EMAIL_APP_PASSWORD = "CHANGE-ME"  # REPLACE WITH THE SENDER ACCOUNT'S APP PASSWORD (NOT YOUR NORMAL PASSWORD). DO NOT SHARE THIS FILE OR UPLOAD IT TO GITHUB WITH THE PASSWORD IN IT
EMAIL_RECIPIENT = "person.monitoring@example.com"  # REPLACE WITH THE EMAIL ADDRESS THAT SHOULD RECEIVE THE ALERTS (CAN BE THE SAME AS THE SENDER, OR SEPARATE ADDRESSES WITH COMMAS)
SMTP_SERVER = "smtp.gmail.com"  # REPLACE ONLY IF YOUR SENDER IS NOT GMAIL (EXAMPLE: "smtp.office365.com" FOR OUTLOOK, BUT CHECK YOUR PROVIDER'S SETTINGS)
SMTP_PORT = 465  # REPLACE ONLY IF YOUR PROVIDER USES A DIFFERENT SSL PORT
CHECK_INTERVAL_SECONDS = 5.0  # OPTIONAL: CHANGE HOW OFTEN (IN SECONDS) IT CHECKS THE CAMERA
ALERT_COOLDOWN_SECONDS = 1800  # OPTIONAL: CHANGE HOW LONG (IN SECONDS) IT WAITS BEFORE ALERTING AGAIN ABOUT THE SAME TANK
MIN_CONFIDENCE = 0.5  # OPTIONAL: RAISE (UP TO 1.0) FOR FEWER FALSE ALARMS, LOWER IF IT MISSES LOW TANKS
# ===================================================================

WINDOW = 6          # recent checks kept per tank
NEEDED = 5          # how many of those must say "low" before alerting about a tank
MISSING_LIMIT = 10  # checks in a row without seeing a tank before warning about it


# ----------------------------- alerts ------------------------------
def _show_popup(message):
    # 0x30 = warning icon, 0x40000 = always on top, 0x10000 = bring to front
    ctypes.windll.user32.MessageBoxW(0, message, "Tank Alert", 0x30 | 0x40000 | 0x10000)


def send_popup(message):
    if sys.platform != "win32":
        print("popup alerts only work on Windows; printed instead")
        return
    # Separate thread: the popup waits for someone to click OK, and the
    # monitoring loop must not freeze until they do.
    threading.Thread(target=_show_popup, args=(message,), daemon=True).start()


def send_email(message):
    msg = EmailMessage()
    msg["Subject"] = "Tank level alert"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECIPIENT
    msg.set_content(message)
    try:
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=20)
        else:  # e.g. port 587 uses STARTTLS
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20)
            server.starttls()
        with server:
            server.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
            server.send_message(msg)
        print("alert email sent")
    except (smtplib.SMTPException, OSError) as e:
        print("alert failed:", e)


def send_alert(message):
    print(f"ALERT: {message}")
    if ALERT_POPUP:
        send_popup(message)
    if ALERT_EMAIL:
        send_email(message)


# --------------------------- detection -----------------------------
def grab_frame(source):
    cap = cv2.VideoCapture(source)
    ok, frame = cap.read()
    cap.release()  # reopen each time so we get a fresh frame, not a buffered one
    return frame if ok else None


def detect_tanks(model, frame):
    """Return a list of detected tanks: center position, confidence, and low flag."""
    result = model(frame, conf=MIN_CONFIDENCE, verbose=False)[0]
    tanks = []
    for box in result.boxes:
        name = result.names[int(box.cls[0])]
        if name not in (LOW_CLASS, GOOD_CLASS):
            continue
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        tanks.append({
            "cx": (x1 + x2) / 2,
            "cy": (y1 + y2) / 2,
            "conf": float(box.conf[0]),
            "low": name == LOW_CLASS,
        })
    return tanks


def calibrate(model, source):
    """Wait for a frame showing every tank, and remember where each one sits."""
    print(f"Calibrating: waiting to see all {NUMBER_OF_TANKS} tanks...")
    while True:
        frame = grab_frame(source)
        if frame is None:
            print("calibration: camera read failed")
        else:
            tanks = detect_tanks(model, frame)
            if len(tanks) == NUMBER_OF_TANKS:
                tanks.sort(key=lambda t: t["cx"])  # left to right
                slots = [(t["cx"], t["cy"]) for t in tanks]
                print("Calibrated. Tank positions (left to right):",
                      ", ".join(f"{TANK_NAMES[i]}=({x:.0f},{y:.0f})" for i, (x, y) in enumerate(slots)))
                return slots
            print(f"calibration: saw {len(tanks)} tanks, need {NUMBER_OF_TANKS}")
        time.sleep(CHECK_INTERVAL_SECONDS)


def match_to_slots(tanks, slots, max_dist):
    """Assign each detection to the nearest remembered tank position."""
    found = {}
    for t in tanks:
        dists = [math.hypot(t["cx"] - sx, t["cy"] - sy) for sx, sy in slots]
        i = min(range(len(slots)), key=dists.__getitem__)
        if dists[i] <= max_dist and (i not in found or t["conf"] > found[i]["conf"]):
            found[i] = t
    return found


# ------------------------------ main -------------------------------
def main():
    if len(TANK_NAMES) != NUMBER_OF_TANKS:
        raise SystemExit("TANK_NAMES must have exactly NUMBER_OF_TANKS names.")
    if ALERT_EMAIL and EMAIL_APP_PASSWORD == "CHANGE-ME":
        raise SystemExit("Set the EMAIL_ settings at the top of monitor_yolo.py before running.")
    if not ALERT_POPUP and not ALERT_EMAIL:
        raise SystemExit("Turn on ALERT_POPUP or ALERT_EMAIL at the top of monitor_yolo.py.")

    model = YOLO(MODEL_PATH)
    source = int(CAMERA_SOURCE) if CAMERA_SOURCE.isdigit() else CAMERA_SOURCE

    slots = calibrate(model, source)
    # A detection only counts for a tank if it is closer than half the gap
    # between the two closest tanks, so tanks can never be mixed up.
    min_gap = min(
        math.hypot(a[0] - b[0], a[1] - b[1])
        for i, a in enumerate(slots) for b in slots[i + 1:]
    )
    max_dist = min_gap / 2

    histories = [deque(maxlen=WINDOW) for _ in range(NUMBER_OF_TANKS)]
    last_alert = [0.0] * NUMBER_OF_TANKS
    missing = [0] * NUMBER_OF_TANKS
    cam_failures = 0

    while True:
        frame = grab_frame(source)
        if frame is None:
            cam_failures += 1
            print(f"camera read failed ({cam_failures})")
            if cam_failures == 10:
                send_alert("Camera is not responding.")
            time.sleep(CHECK_INTERVAL_SECONDS)
            continue
        cam_failures = 0

        found = match_to_slots(detect_tanks(model, frame), slots, max_dist)
        messages = []
        status = []

        for i in range(NUMBER_OF_TANKS):
            if i in found:
                missing[i] = 0
                histories[i].append(found[i]["low"])
                status.append(f"{TANK_NAMES[i]}: {'LOW' if found[i]['low'] else 'good'}")
            else:
                # Can't see this tank right now. Don't guess "good" or "low".
                missing[i] += 1
                status.append(f"{TANK_NAMES[i]}: ?")
                if missing[i] == MISSING_LIMIT:
                    messages.append(f"{TANK_NAMES[i]} is not visible in the camera view. Camera may have moved.")

        now = time.time()
        low_names = []
        for i in range(NUMBER_OF_TANKS):
            h = histories[i]
            if len(h) == WINDOW and sum(h) >= NEEDED and now - last_alert[i] > ALERT_COOLDOWN_SECONDS:
                low_names.append(TANK_NAMES[i])
                last_alert[i] = now
        if low_names:
            messages.insert(0, "LOW: " + ", ".join(low_names) + ". Please check.")

        print(f"{time.strftime('%H:%M:%S')}  " + "  |  ".join(status))
        if messages:
            send_alert("\n".join(messages))

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
