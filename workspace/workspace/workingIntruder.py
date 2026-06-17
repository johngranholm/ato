import cv2
import numpy as np
import time
import threading
import winsound

CAM_INDEX = 0
MIN_CONTOURS_AREA = 2500
REPEAT_EVERY_SEC = 0.6


def trigger_alarm():
    winsound.Beep(1200, 180)
    winsound.Beep(900, 180)
    winsound.Beep(1200, 180)


def main():
    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        raise RuntimeError('Could not open webcam')

    first_frame = None
    last_spoken = 0.0
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
            for c in contours:
                if cv2.contourArea(c) < MIN_CONTOURS_AREA:
                    continue
                motion_detected = True
                x, y, w, h = cv2.boundingRect(c)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)

            now = time.time()
            if motion_detected:
                cv2.putText(frame, 'INTRUDER!', (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 4)
                cv2.putText(frame, 'Motion detected', (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                if now - last_spoken >= REPEAT_EVERY_SEC:
                    threading.Thread(target=trigger_alarm, daemon=True).start()
                    last_spoken = now
            else:
                cv2.putText(frame, 'No motion', (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

            cv2.imshow('Intruder Alarm', frame)
            cv2.imshow('Threshold', thresh)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
