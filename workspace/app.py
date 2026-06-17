import cv2
import time
import mediapipe as mp

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
if not cap.isOpened():
    cap = cv2.VideoCapture(0)

with mp_pose.Pose(
    static_image_mode=False,
    model_complexity=1,
    smooth_landmarks=True,
    enable_segmentation=False,
    smooth_segmentation=False,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
) as pose:
    fps_t = time.time()
    fps = 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            print('Failed to read from webcam.')
            break

        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb)

        if results.pose_landmarks:
            mp_drawing.draw_landmarks(
                frame,
                results.pose_landmarks,
                mp_pose.POSE_CONNECTIONS,
                mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
                mp_drawing.DrawingSpec(color=(255, 0, 0), thickness=2),
            )

            lms = results.pose_world_landmarks.landmark if results.pose_world_landmarks else results.pose_landmarks.landmark
            points = {
                'Nose': mp_pose.PoseLandmark.NOSE.value,
                'LShoulder': mp_pose.PoseLandmark.LEFT_SHOULDER.value,
                'RShoulder': mp_pose.PoseLandmark.RIGHT_SHOULDER.value,
                'LHip': mp_pose.PoseLandmark.LEFT_HIP.value,
                'RHip': mp_pose.PoseLandmark.RIGHT_HIP.value,
            }
            y = 30
            for name, idx in points.items():
                lm = lms[idx]
                cv2.putText(frame, f'{name}: x={lm.x:+.2f} y={lm.y:+.2f} z={lm.z:+.2f}', (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
                y += 25

        now = time.time()
        dt = now - fps_t
        fps_t = now
        if dt > 0:
            fps = 0.9 * fps + 0.1 * (1.0 / dt)
        cv2.putText(frame, f'FPS: {fps:.1f}', (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.putText(frame, 'Press Q to quit', (w - 180, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.imshow('3D Body Tracker (MediaPipe + OpenCV)', frame)
        if (cv2.waitKey(1) & 0xFF) in (ord('q'), ord('Q')):
            break

cap.release()
cv2.destroyAllWindows()
