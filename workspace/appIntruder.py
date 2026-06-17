import cv2
import numpy as np
import pyttsx3
import time
import threading
import queue

CAM_INDEX = 0
MIN_CONTOURS_AREA = 2500
REPEAT_EVERY_SEC = 0.5


class SpeechWorker:
    def __init__(self):
        self.q = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while True:
            item = self.q.get()
            if item is None:
                break
            text, lang_hint = item
            engine = pyttsx3.init()
            engine.setProperty('rate', 170)
            engine.setProperty('volume', 1.0)
            try:
                voices = engine.getProperty('voices')
                chosen = None
                for v in voices:
                    blob = f"{getattr(v, 'name', '')} {getattr(v, 'id', '')}".lower()
                    if lang_hint == 'es' and ('spanish' in blob or 'es' in blob or 'es-' in blob):
                        chosen = v.id
                        break
                    if lang_hint == 'en' and ('english' in blob or 'en' in blob or 'en-' in blob):
                        chosen = v.id
                        break
                if chosen:
                    engine.setProperty('voice', chosen)
                engine.say(text)
                engine.runAndWait()
            finally:
                engine.stop()

    def say(self, text, lang_hint='en'):
        self.q.put((text, lang_hint))

    def close(self):
        self.q.put(None)


def main():
    speech = SpeechWorker()
    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        raise RuntimeError('Could not open webcam')

    first_frame = None
    last_spoken = 0.0
    motion_was_on = False
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
                if (not motion_was_on) or (now - last_spoken >= REPEAT_EVERY_SEC):
                    speech.say('Intruder!', 'en')
                    speech.say('¡Intruso!', 'es')
                    last_spoken = now
                motion_was_on = True
            else:
                cv2.putText(frame, 'No motion', (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                motion_was_on = False

            cv2.imshow('Intruder Alarm', frame)
            cv2.imshow('Threshold', thresh)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        speech.close()


if __name__ == '__main__':
    main()
