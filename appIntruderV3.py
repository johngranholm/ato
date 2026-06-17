import cv2
import pyttsx3
import time
import threading
import os
from datetime import datetime

from ato.persona import persona as P

CAM_INDEX = 0
MIN_CONTOURS_AREA = 2500
MOTION_RESET_SEC = 2.5
SCREENSHOT_DIR = os.path.join(os.path.expanduser('~'), 'Desktop', 'IntruderShots')
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

last_motion_time = 0.0
speech_in_progress = False
alert_index = 0
current_ato_direction = 'left'
force_ato_direction = None
lock = threading.Lock()

ALERTS = [
    ('es-ES', '¡Intruso!'),
    ('en-US', 'Intruder!'),
    ('zh-CN', '入侵者'),
    ('ja-JP', '侵入者'),
    ('ru-RU', 'Нарушитель!'),
    ('en-GB', 'Intruder!'),
    ('es-MX', '¡Intruso!'),
    ('zh-HK', '入侵者'),
    ('zh-TW', '入侵者'),
]

VOICE_MATCHES = {
    'es-ES': ['helena'],
    'es-MX': ['sabina'],
    'en-US': ['david', 'zira'],
    'en-GB': ['hazel'],
    'zh-CN': ['huihui'],
    'zh-HK': ['tracy'],
    'zh-TW': ['hanhan'],
    'ja-JP': ['haruka'],
    'ru-RU': ['irina'],
}


def save_screenshot(frame):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    path = os.path.join(SCREENSHOT_DIR, f'intruder_{ts}.png')
    cv2.imwrite(path, frame)


def pick_voice_id(tag):
    engine = pyttsx3.init()
    try:
        for v in engine.getProperty('voices'):
            blob = f"{getattr(v, 'name', '')} {getattr(v, 'id', '')} {getattr(v, 'languages', [])}".lower()
            if any(k in blob for k in VOICE_MATCHES.get(tag, [])):
                return getattr(v, 'id', None)
        return None
    finally:
        engine.stop()


def speak_alert(tag, text):
    global speech_in_progress
    with lock:
        if speech_in_progress:
            return
        speech_in_progress = True
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 170)
        engine.setProperty('volume', 1.0)
        voice_id = pick_voice_id(tag)
        if voice_id:
            engine.setProperty('voice', voice_id)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    finally:
        with lock:
            speech_in_progress = False


def motion_direction_from_x(x, width):
    center = x / max(width, 1)
    if center < 0.33:
        return 'left'
    if center > 0.66:
        return 'right'
    return 'center'


def set_ato_gaze(direction):
    try:
        P.PERSONA['gaze_state'] = direction
    except Exception:
        pass


def update_ato_direction(new_direction):
    global current_ato_direction
    with lock:
        current_ato_direction = new_direction


def draw_ato_avatar(frame):
    with lock:
        direction = force_ato_direction or current_ato_direction

    h, w = frame.shape[:2]
    cx = w // 2
    cy = 110

    if direction == 'left':
        head_shift = -18
        eye_dx = -10
        pupil_dx = -5
    elif direction == 'right':
        head_shift = 18
        eye_dx = 10
        pupil_dx = 5
    else:
        head_shift = 0
        eye_dx = 0
        pupil_dx = 0

    # ATO head
    cv2.circle(frame, (cx + head_shift, cy), 58, (255, 220, 170), -1)
    cv2.circle(frame, (cx + head_shift, cy), 58, (50, 50, 50), 2)

    # eyes
    left_eye = (cx - 20 + head_shift + eye_dx, cy - 10)
    right_eye = (cx + 20 + head_shift + eye_dx, cy - 10)
    cv2.circle(frame, left_eye, 10, (255, 255, 255), -1)
    cv2.circle(frame, right_eye, 10, (255, 255, 255), -1)
    cv2.circle(frame, (left_eye[0] + pupil_dx, left_eye[1]), 4, (20, 20, 20), -1)
    cv2.circle(frame, (right_eye[0] + pupil_dx, right_eye[1]), 4, (20, 20, 20), -1)

    # mouth / expression
    mouth_y = cy + 24
    cv2.ellipse(frame, (cx + head_shift, mouth_y), (16, 10), 0, 0, 180, (0, 0, 200), 2)

    cv2.putText(frame, f'ATO looking: {direction.upper()}', (20, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)


def maybe_announce(frame):
    global last_motion_time, alert_index
    now = time.time()
    with lock:
        if (now - last_motion_time) < MOTION_RESET_SEC:
            return
        last_motion_time = now
        tag, text = ALERTS[alert_index]
        alert_index = (alert_index + 1) % len(ALERTS)
    save_screenshot(frame)
    threading.Thread(target=speak_alert, args=(tag, text), daemon=True).start()


def open_camera():
    for backend in [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]:
        cap = cv2.VideoCapture(CAM_INDEX, backend)
        if cap.isOpened():
            return cap
    return cv2.VideoCapture(CAM_INDEX)


def main():
    print('Starting Intruder Alarm...')
    cap = open_camera()
    print('Camera opened:', cap.isOpened())
    if not cap.isOpened():
        raise RuntimeError('Could not open webcam')

    cv2.namedWindow('Intruder Alarm', cv2.WINDOW_NORMAL)
    cv2.namedWindow('Threshold', cv2.WINDOW_NORMAL)
    print('Windows created; entering loop')

    first_frame = None
    cv2.namedWindow('Intruder Alarm', cv2.WINDOW_NORMAL)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            if first_frame is None:
                first_frame = gray.copy().astype('float')
                cv2.putText(frame, 'Calibrating background...', (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                draw_ato_avatar(frame)
                cv2.imshow('Intruder Alarm', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                continue

            cv2.accumulateWeighted(gray, first_frame, 0.02)
            frame_delta = cv2.absdiff(gray, cv2.convertScaleAbs(first_frame))
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
            thresh = cv2.dilate(thresh, None, iterations=2)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            motion_detected = False
            motion_x = None
            largest_area = 0
            current_ato_direction = 'center'
            for c in contours:
                area = cv2.contourArea(c)
                if area < MIN_CONTOURS_AREA:
                    continue
                motion_detected = True
                x, y, w, h = cv2.boundingRect(c)
                motion_x = x + (w // 2)
                current_ato_direction = motion_direction_from_x(motion_x, frame.shape[1])
                set_ato_gaze(current_ato_direction)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                if area > largest_area:
                    largest_area = area
                    motion_x = x + (w / 2)

            if motion_detected and motion_x is not None:
                direction = motion_direction_from_x(motion_x, frame.shape[1])
                update_ato_direction(direction)
                cv2.putText(frame, 'INTRUDER!', (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 4)
                cv2.putText(frame, 'Motion detected', (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                maybe_announce(frame.copy())
            else:
                cv2.putText(frame, 'No motion', (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

            draw_ato_avatar(frame)
            cv2.imshow('Intruder Alarm', frame)
            cv2.imshow('Threshold', thresh)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('l'):
                with lock:
                    force_ato_direction = 'left'
            elif key == ord('c'):
                with lock:
                    force_ato_direction = None
            elif key == ord('q'):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
