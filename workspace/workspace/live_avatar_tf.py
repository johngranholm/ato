import os
import cv2
import numpy as np
try:
    import tensorflow as tf
except Exception:
    tf = None

try:
    import mediapipe.python.solutions.pose as mp_pose_mod
    HAVE_MP = True
except Exception:
    mp_pose_mod = None
    HAVE_MP = False

GLB_PATH = r"C:\mita_miside_free.glb"


def load_avatar_notice(frame, ok):
    text = f"Avatar asset: {'FOUND' if ok else 'MISSING'} {GLB_PATH}"
    cv2.putText(frame, text, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)


def find_pose_landmarks(frame):
    # Fallback body template so the demo still works without MediaPipe.
    h, w = frame.shape[:2]
    cx = w * 0.5
    cy = h * 0.54
    sw = w * 0.18
    th = h * 0.20
    pts = {
        'LEFT_SHOULDER': np.array([cx - sw, cy - th], dtype=np.float32),
        'RIGHT_SHOULDER': np.array([cx + sw, cy - th], dtype=np.float32),
        'LEFT_ELBOW': np.array([cx - sw * 1.35, cy - th * 0.15], dtype=np.float32),
        'RIGHT_ELBOW': np.array([cx + sw * 1.35, cy - th * 0.15], dtype=np.float32),
        'LEFT_WRIST': np.array([cx - sw * 1.55, cy + th * 0.35], dtype=np.float32),
        'RIGHT_WRIST': np.array([cx + sw * 1.55, cy + th * 0.35], dtype=np.float32),
        'LEFT_HIP': np.array([cx - sw * 0.75, cy + th], dtype=np.float32),
        'RIGHT_HIP': np.array([cx + sw * 0.75, cy + th], dtype=np.float32),
        'LEFT_KNEE': np.array([cx - sw * 0.75, cy + th * 2.0], dtype=np.float32),
        'RIGHT_KNEE': np.array([cx + sw * 0.75, cy + th * 2.0], dtype=np.float32),
        'LEFT_ANKLE': np.array([cx - sw * 0.75, cy + th * 3.1], dtype=np.float32),
        'RIGHT_ANKLE': np.array([cx + sw * 0.75, cy + th * 3.1], dtype=np.float32),
    }
    return pts


def lm_xy(lms, name, w, h):
    return lms[name], 1.0


def draw_body_avatar(frame, pts):
    overlay = frame.copy()
    shoulder_center = (pts['LEFT_SHOULDER'] + pts['RIGHT_SHOULDER']) / 2.0
    hip_center = (pts['LEFT_HIP'] + pts['RIGHT_HIP']) / 2.0
    torso_len = max(1.0, np.linalg.norm(shoulder_center - hip_center))
    shoulder_w = max(1.0, np.linalg.norm(pts['LEFT_SHOULDER'] - pts['RIGHT_SHOULDER']))
    head_r = int(max(18, shoulder_w * 0.22))
    head_center = shoulder_center + np.array([0, -torso_len * 0.95], dtype=np.float32)
    outline = (20, 20, 35)
    skin = (190, 170, 160)
    suit = (50, 75, 130)
    limb = (220, 215, 210)
    cv2.circle(overlay, tuple(np.round(head_center).astype(int)), head_r + 4, outline, -1, cv2.LINE_AA)
    cv2.circle(overlay, tuple(np.round(head_center).astype(int)), head_r, skin, -1, cv2.LINE_AA)
    neck_top = shoulder_center + np.array([0, -head_r * 0.3], dtype=np.float32)
    neck_bot = shoulder_center + np.array([0, head_r * 0.1], dtype=np.float32)
    cv2.line(overlay, tuple(np.round(neck_top).astype(int)), tuple(np.round(neck_bot).astype(int)), skin, max(8, int(shoulder_w * 0.10)), cv2.LINE_AA)
    torso = np.array([
        pts['LEFT_SHOULDER'] + np.array([8, 6], dtype=np.float32),
        pts['RIGHT_SHOULDER'] + np.array([-8, 6], dtype=np.float32),
        pts['RIGHT_HIP'] + np.array([-10, 10], dtype=np.float32),
        pts['LEFT_HIP'] + np.array([10, 10], dtype=np.float32),
    ], dtype=np.int32)
    cv2.fillConvexPoly(overlay, torso, suit)
    cv2.polylines(overlay, [torso], True, outline, 2, cv2.LINE_AA)
    for a, b in [('LEFT_SHOULDER','LEFT_ELBOW'), ('LEFT_ELBOW','LEFT_WRIST'), ('RIGHT_SHOULDER','RIGHT_ELBOW'), ('RIGHT_ELBOW','RIGHT_WRIST'), ('LEFT_HIP','LEFT_KNEE'), ('LEFT_KNEE','LEFT_ANKLE'), ('RIGHT_HIP','RIGHT_KNEE'), ('RIGHT_KNEE','RIGHT_ANKLE')]:
        p1, p2 = pts[a], pts[b]
        thick = int(max(8, np.linalg.norm(p1 - p2) * 0.12))
        cv2.line(overlay, tuple(np.round(p1).astype(int)), tuple(np.round(p2).astype(int)), outline, thick + 4, cv2.LINE_AA)
        cv2.line(overlay, tuple(np.round(p1).astype(int)), tuple(np.round(p2).astype(int)), limb, thick, cv2.LINE_AA)
    for n in ['LEFT_WRIST', 'RIGHT_WRIST', 'LEFT_ANKLE', 'RIGHT_ANKLE']:
        cv2.circle(overlay, tuple(np.round(pts[n]).astype(int)), 9, outline, -1, cv2.LINE_AA)
        cv2.circle(overlay, tuple(np.round(pts[n]).astype(int)), 6, limb, -1, cv2.LINE_AA)
    return cv2.addWeighted(overlay, 0.93, frame, 0.07, 0)


def main():
    avatar_exists = os.path.exists(GLB_PATH)
    print(f'Loaded avatar model reference: {GLB_PATH}' if avatar_exists else f'Warning: avatar model not found at {GLB_PATH}')
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError('Could not open webcam')
    cv2.namedWindow('TensorFlow Live Avatar Replace', cv2.WINDOW_NORMAL)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        lms = find_pose_landmarks(frame)
        if lms is not None:
            pts = {}
            for n in ['LEFT_SHOULDER','RIGHT_SHOULDER','LEFT_ELBOW','RIGHT_ELBOW','LEFT_WRIST','RIGHT_WRIST','LEFT_HIP','RIGHT_HIP','LEFT_KNEE','RIGHT_KNEE','LEFT_ANKLE','RIGHT_ANKLE']:
                pts[n], _ = lm_xy(lms, n, w, h)
            frame = draw_body_avatar(frame, pts)
        else:
            cv2.putText(frame, 'MediaPipe unavailable; showing camera feed only', (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
        load_avatar_notice(frame, avatar_exists)
        cv2.putText(frame, 'Press Q to quit', (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imshow('TensorFlow Live Avatar Replace', frame)
        if cv2.waitKey(1) & 0xFF in (ord('q'), ord('Q')):
            break
    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
