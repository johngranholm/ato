import cv2
import numpy as np
import pyttsx3
import time
import threading
import tkinter as tk

CAM_INDEX = 0
MIN_CONTOURS_AREA = 2500
REPEAT_EVERY_SEC = 0.6


def speak_intruder():
    engine = pyttsx3.init()
    engine.setProperty('rate', 170)
    engine.setProperty('volume', 1.0)
    engine.say('intruder!')
    engine.runAndWait()
    engine.stop()


class IntruderApp:
    def __init__(self):
        self.cap = cv2.VideoCapture(CAM_INDEX)
        if not self.cap.isOpened():
            raise RuntimeError('Could not open webcam')

        self.first_frame = None
        self.last_spoken = 0.0
        self.running = True

        self.root = tk.Tk()
        self.root.title('Intruder Control')
        self.root.geometry('260x160')

        label = tk.Label(self.root, text='Manual intruder trigger', font=('Segoe UI', 12))
        label.pack(pady=15)

        btn = tk.Button(self.root, text='Say Intruder', font=('Segoe UI', 14, 'bold'), bg='red', fg='white', command=self.manual_trigger)
        btn.pack(pady=10, ipadx=10, ipady=8)

        self.root.protocol('WM_DELETE_WINDOW', self.close)
        threading.Thread(target=self.video_loop, daemon=True).start()

    def manual_trigger(self):
        threading.Thread(target=speak_intruder, daemon=True).start()

    def video_loop(self):
        cv2.namedWindow('Intruder Alarm', cv2.WINDOW_NORMAL)
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            if self.first_frame is None:
                self.first_frame = gray.copy().astype('float')
                cv2.putText(frame, 'Calibrating background...', (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                cv2.imshow('Intruder Alarm', frame)
                cv2.waitKey(1)
                continue

            cv2.accumulateWeighted(gray, self.first_frame, 0.02)
            frame_delta = cv2.absdiff(gray, cv2.convertScaleAbs(self.first_frame))
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
                if now - self.last_spoken >= REPEAT_EVERY_SEC:
                    threading.Thread(target=speak_intruder, daemon=True).start()
                    self.last_spoken = now
            else:
                cv2.putText(frame, 'No motion', (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

            cv2.imshow('Intruder Alarm', frame)
            cv2.imshow('Threshold', thresh)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.close()
                break

        self.close()

    def close(self):
        if not self.running:
            return
        self.running = False
        try:
            self.cap.release()
        except Exception:
            pass
        cv2.destroyAllWindows()
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    IntruderApp().run()
