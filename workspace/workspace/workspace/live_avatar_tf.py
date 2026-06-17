import os
import cv2
import numpy as np
import mediapipe as mp

GLB_PATH = r"C:\mita_miside_free.glb"
mp_pose = mp.solutions.pose


def pose_tracker():
    if not hasattr(pose_tracker, 'pose'):
        pose_tracker.pose = mp_pose.Pose(
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
    return pose_tracker.pose


def extract_landmarks(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res = pose_tracker().process(rgb)
    return res.pose_landmarks, res.pose_world_landmarks


def draw_banner(frame, text, color):
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 90), color, -1)
    cv2.putText(frame, text, (20, 38), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3, cv2.LINE_AA)


def main():
    asset_ok = os.path.exists(GLB_PATH)
    print(f"Loaded avatar model reference: {GLB_PATH}" if asset_ok else f"Warning: avatar model missing: {GLB_PATH}")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError('Could not open webcam')

    cv2.namedWindow('Body Tracking Status', cv2.WINDOW_NORMAL)
    lost_frames = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame = cv2.flip(frame, 1)
        pose_lms, world_lms = extract_landmarks(frame)

        if pose_lms is None:
            lost_frames += 1
            draw_banner(frame, 'I CANNOT SEE YOU', (0, 0, 255))
            cv2.putText(frame, 'Move into view and face the camera', (20, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, f'Asset: {"FOUND" if asset_ok else "MISSING"}', (20, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2, cv2.LINE_AA)
        else:
            lost_frames = 0
            h, w = frame.shape[:2]
            lm = pose_lms.landmark
            L = mp_pose.PoseLandmark
            pts = {}
            for name in ['LEFT_SHOULDER','RIGHT_SHOULDER','LEFT_HIP','RIGHT_HIP','LEFT_ELBOW','RIGHT_ELBOW','LEFT_WRIST','RIGHT_WRIST','LEFT_KNEE','RIGHT_KNEE','LEFT_ANKLE','RIGHT_ANKLE']:
                idx = getattr(L, name).value
                pts[name] = np.array([lm[idx].x * w, lm[idx].y * h], dtype=np.float32)

            # Draw body tracking so it is obvious that the pose is being detected.
            pairs = [('LEFT_SHOULDER','RIGHT_SHOULDER'),('LEFT_SHOULDER','LEFT_ELBOW'),('LEFT_ELBOW','LEFT_WRIST'),('RIGHT_SHOULDER','RIGHT_ELBOW'),('RIGHT_ELBOW','RIGHT_WRIST'),('LEFT_SHOULDER','LEFT_HIP'),('RIGHT_SHOULDER','RIGHT_HIP'),('LEFT_HIP','RIGHT_HIP'),('LEFT_HIP','LEFT_KNEE'),('LEFT_KNEE','LEFT_ANKLE'),('RIGHT_HIP','RIGHT_KNEE'),('RIGHT_KNEE','RIGHT_ANKLE')]
            for a, b in pairs:
                p1 = tuple(np.round(pts[a]).astype(int))
                p2 = tuple(np.round(pts[b]).astype(int))
                cv2.line(frame, p1, p2, (0, 255, 0), 3, cv2.LINE_AA)
            for p in pts.values():
                cv2.circle(frame, tuple(np.round(p).astype(int)), 5, (0, 0, 255), -1, cv2.LINE_AA)

            # 3D info text from world landmarks if available.
            if world_lms is not None:
                draw_banner(frame, 'POSE TRACKING ON', (0, 140, 0))
                cv2.putText(frame, '3D landmarks available', (20, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
            else:
                draw_banner(frame, '2D POSE TRACKING ON', (0, 140, 0))

        cv2.imshow('Body Tracking Status', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
