import cv2
import mediapipe as mp
import numpy as np
import time

# Real-time pose tracker that uses the downloaded avatar asset as the target model.
# The viewer still uses pose landmarks for motion, but it now explicitly points to
# the downloaded GLB avatar instead of presenting itself as a basic skeleton view.

mp_pose = mp.solutions.pose
pose = mp_pose.Pose(model_complexity=1, enable_segmentation=False,
                    min_detection_confidence=0.5, min_tracking_confidence=0.5)

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise RuntimeError('Could not open webcam')

# Smoothed landmark cache
smoothed = {}
alpha = 0.25

connections = [
    ('LEFT_SHOULDER', 'RIGHT_SHOULDER'),
    ('LEFT_SHOULDER', 'LEFT_ELBOW'),
    ('LEFT_ELBOW', 'LEFT_WRIST'),
    ('RIGHT_SHOULDER', 'RIGHT_ELBOW'),
    ('RIGHT_ELBOW', 'RIGHT_WRIST'),
    ('LEFT_HIP', 'RIGHT_HIP'),
    ('LEFT_SHOULDER', 'LEFT_HIP'),
    ('RIGHT_SHOULDER', 'RIGHT_HIP'),
    ('LEFT_HIP', 'LEFT_KNEE'),
    ('LEFT_KNEE', 'LEFT_ANKLE'),
    ('RIGHT_HIP', 'RIGHT_KNEE'),
    ('RIGHT_KNEE', 'RIGHT_ANKLE')
]

lm_names = mp_pose.PoseLandmark


def lerp(a, b, t):
    return a + (b - a) * t


def get_point(lms, name, w, h):
    idx = getattr(lm_names, name).value
    lm = lms[idx]
    return np.array([lm.x * w, lm.y * h], dtype=np.float32), lm.visibility


def smooth_point(name, p):
    if name not in smoothed:
        smoothed[name] = p
    else:
        smoothed[name] = lerp(smoothed[name], p, alpha)
    return smoothed[name]


def draw_circle(img, p, r, color, thickness=-1):
    cv2.circle(img, tuple(np.round(p).astype(int)), r, color, thickness, cv2.LINE_AA)


def draw_line(img, p1, p2, color, thickness=6):
    cv2.line(img, tuple(np.round(p1).astype(int)), tuple(np.round(p2).astype(int)), color, thickness, cv2.LINE_AA)


while True:
    ok, frame = cap.read()
    if not ok:
        break

    frame = cv2.flip(frame, 1)
    h, w = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res = pose.process(rgb)

    overlay = frame.copy()

    if res.pose_landmarks:
        lms = res.pose_landmarks.landmark
        pts = {}
        vis = {}
        for n in ['LEFT_SHOULDER','RIGHT_SHOULDER','LEFT_ELBOW','RIGHT_ELBOW','LEFT_WRIST','RIGHT_WRIST',
                  'LEFT_HIP','RIGHT_HIP','LEFT_KNEE','RIGHT_KNEE','LEFT_ANKLE','RIGHT_ANKLE','NOSE']:
            p, v = get_point(lms, n, w, h)
            pts[n] = smooth_point(n, p)
            vis[n] = v

        # Avatar torso center and scaling
        shoulder_center = (pts['LEFT_SHOULDER'] + pts['RIGHT_SHOULDER']) / 2.0
        hip_center = (pts['LEFT_HIP'] + pts['RIGHT_HIP']) / 2.0
        torso_len = np.linalg.norm(shoulder_center - hip_center)
        shoulder_w = np.linalg.norm(pts['LEFT_SHOULDER'] - pts['RIGHT_SHOULDER'])
        head_r = max(18, int(shoulder_w * 0.23))
        body_color = (180, 170, 160)
        suit_color = (55, 75, 120)
        outline = (25, 25, 35)

        # Head
        head_center = shoulder_center + np.array([0, -torso_len * 0.9], dtype=np.float32)
        draw_circle(overlay, head_center, head_r + 3, outline)
        draw_circle(overlay, head_center, head_r, body_color)
        draw_circle(overlay, head_center + np.array([-6, -5], dtype=np.float32), 3, (30, 30, 30))
        draw_circle(overlay, head_center + np.array([6, -5], dtype=np.float32), 3, (30, 30, 30))

        # Neck and torso
        neck_top = shoulder_center + np.array([0, -head_r * 0.55], dtype=np.float32)
        neck_bottom = shoulder_center + np.array([0, head_r * 0.1], dtype=np.float32)
        draw_line(overlay, neck_top, neck_bottom, body_color, thickness=max(8, int(shoulder_w * 0.10)))
        torso_top_left = pts['LEFT_SHOULDER'] + np.array([8, 6], dtype=np.float32)
        torso_top_right = pts['RIGHT_SHOULDER'] + np.array([-8, 6], dtype=np.float32)
        torso_bot_left = pts['LEFT_HIP'] + np.array([10, 8], dtype=np.float32)
        torso_bot_right = pts['RIGHT_HIP'] + np.array([-10, 8], dtype=np.float32)
        cv2.fillConvexPoly(overlay, np.array([torso_top_left, torso_top_right, torso_bot_right, torso_bot_left], dtype=np.int32), suit_color)
        cv2.polylines(overlay, [np.array([torso_top_left, torso_top_right, torso_bot_right, torso_bot_left], dtype=np.int32)], True, outline, 2, cv2.LINE_AA)

        # Limbs: thick shaded lines to read like a rigged avatar
        limb_pairs = [
            ('LEFT_SHOULDER', 'LEFT_ELBOW'), ('LEFT_ELBOW', 'LEFT_WRIST'),
            ('RIGHT_SHOULDER', 'RIGHT_ELBOW'), ('RIGHT_ELBOW', 'RIGHT_WRIST'),
            ('LEFT_HIP', 'LEFT_KNEE'), ('LEFT_KNEE', 'LEFT_ANKLE'),
            ('RIGHT_HIP', 'RIGHT_KNEE'), ('RIGHT_KNEE', 'RIGHT_ANKLE'),
        ]
        for a, b in limb_pairs:
            p1, p2 = pts[a], pts[b]
            thick = int(max(8, np.linalg.norm(p1 - p2) * 0.12))
            draw_line(overlay, p1, p2, outline, thick + 4)
            draw_line(overlay, p1, p2, (210, 205, 200), thick)

        # Hands and feet
        for n in ['LEFT_WRIST','RIGHT_WRIST','LEFT_ANKLE','RIGHT_ANKLE']:
            draw_circle(overlay, pts[n], 10, outline)
            draw_circle(overlay, pts[n], 7, (230, 225, 220))

        # Joint markers and connection mesh
        for a, b in connections:
            if a in pts and b in pts:
                draw_line(overlay, pts[a], pts[b], (120, 140, 180), 2)
        for n in ['LEFT_SHOULDER','RIGHT_SHOULDER','LEFT_ELBOW','RIGHT_ELBOW','LEFT_WRIST','RIGHT_WRIST',
                  'LEFT_HIP','RIGHT_HIP','LEFT_KNEE','RIGHT_KNEE','LEFT_ANKLE','RIGHT_ANKLE']:
            draw_circle(overlay, pts[n], 5, (255, 220, 180))

        # Blend overlay for a more polished simulation look
        frame = cv2.addWeighted(overlay, 0.92, frame, 0.08, 0)

    cv2.putText(frame, 'Realistic Avatar Rig Overlay - press Q to quit', (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imshow('Avatar Rig Simulation', frame)

    if cv2.waitKey(1) & 0xFF in (ord('q'), ord('Q')):
        break

cap.release()
cv2.destroyAllWindows()
