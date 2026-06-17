import os
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from pygltflib import GLTF2

GLB_PATH = r"C:\brunette.glb"
MODEL_PATH = os.path.join(os.path.dirname(__file__), "pose_landmarker.task")

L = {
    'LEFT_SHOULDER': 11, 'RIGHT_SHOULDER': 12,
    'LEFT_ELBOW': 13, 'RIGHT_ELBOW': 14,
    'LEFT_WRIST': 15, 'RIGHT_WRIST': 16,
    'LEFT_HIP': 23, 'RIGHT_HIP': 24,
    'LEFT_KNEE': 25, 'RIGHT_KNEE': 26,
    'LEFT_ANKLE': 27, 'RIGHT_ANKLE': 28,
}


def ensure_model():
    if os.path.exists(MODEL_PATH):
        return MODEL_PATH
    raise FileNotFoundError(f"Missing pose model file: {MODEL_PATH}")


def create_landmarker():
    base = python.BaseOptions(model_asset_path=ensure_model())
    options = vision.PoseLandmarkerOptions(base_options=base, running_mode=vision.RunningMode.VIDEO)
    return vision.PoseLandmarker.create_from_options(options)


def vec3(lms, name, w, h):
    p = lms[L[name]]
    return np.array([p.x * w, p.y * h, p.z], dtype=np.float32)


def read_accessor(gltf, idx):
    acc = gltf.accessors[idx]
    bv = gltf.bufferViews[acc.bufferView]
    blob = gltf.binary_blob()
    offset = (bv.byteOffset or 0) + (acc.byteOffset or 0)
    dtype = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}.get(acc.componentType, np.float32)
    shape = {'MAT4': (acc.count, 4, 4), 'VEC4': (acc.count, 4), 'VEC3': (acc.count, 3)}.get(acc.type, (acc.count,))
    return np.frombuffer(blob, dtype=dtype, count=int(np.prod(shape)), offset=offset).reshape(shape).copy()


def draw_skeleton(frame, lms):
    h, w = frame.shape[:2]
    pairs = [('LEFT_SHOULDER','RIGHT_SHOULDER'), ('LEFT_SHOULDER','LEFT_ELBOW'), ('LEFT_ELBOW','LEFT_WRIST'), ('RIGHT_SHOULDER','RIGHT_ELBOW'), ('RIGHT_ELBOW','RIGHT_WRIST'), ('LEFT_SHOULDER','LEFT_HIP'), ('RIGHT_SHOULDER','RIGHT_HIP'), ('LEFT_HIP','RIGHT_HIP'), ('LEFT_HIP','LEFT_KNEE'), ('LEFT_KNEE','LEFT_ANKLE'), ('RIGHT_HIP','RIGHT_KNEE'), ('RIGHT_KNEE','RIGHT_ANKLE')]
    pts = {k: (int(lms[i].x*w), int(lms[i].y*h)) for k, i in L.items()}
    for a,b in pairs:
        cv2.line(frame, pts[a], pts[b], (0,255,0), 3, cv2.LINE_AA)
    for p in pts.values():
        cv2.circle(frame, p, 5, (0,0,255), -1, cv2.LINE_AA)
    return frame


def main():
    gltf = GLTF2().load(GLB_PATH)
    prim = gltf.meshes[0].primitives[0]
    positions = read_accessor(gltf, prim.attributes.POSITION).astype(np.float32)
    indices = read_accessor(gltf, prim.indices).astype(np.int32).reshape(-1, 3)
    print(f'Loaded GLB: {GLB_PATH}')
    print('primitive vertex count', len(positions), 'face count', len(indices))

    pose = create_landmarker()
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError('Could not open webcam')

    cv2.namedWindow('Body Tracking Status', cv2.WINDOW_NORMAL)
    frame_index = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        result = pose.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), frame_index)
        frame_index += 1

        if result.pose_landmarks:
            lms = result.pose_landmarks[0]
            frame = draw_skeleton(frame, lms)
            ls, rs = vec3(lms, 'LEFT_SHOULDER', w, h), vec3(lms, 'RIGHT_SHOULDER', w, h)
            lh, rh = vec3(lms, 'LEFT_HIP', w, h), vec3(lms, 'RIGHT_HIP', w, h)
            le, re = vec3(lms, 'LEFT_ELBOW', w, h), vec3(lms, 'RIGHT_ELBOW', w, h)
            lw, rw = vec3(lms, 'LEFT_WRIST', w, h), vec3(lms, 'RIGHT_WRIST', w, h)
            lk, rk = vec3(lms, 'LEFT_KNEE', w, h), vec3(lms, 'RIGHT_KNEE', w, h)
            la, ra = vec3(lms, 'LEFT_ANKLE', w, h), vec3(lms, 'RIGHT_ANKLE', w, h)

            torso_center = (ls + rs + lh + rh) / 4.0
            shoulder_span = np.linalg.norm(ls - rs)
            hip_span = np.linalg.norm(lh - rh)
            limb_span = max(np.linalg.norm(le - ls), np.linalg.norm(re - rs), np.linalg.norm(lk - lh), np.linalg.norm(rk - rh), np.linalg.norm(lw - le), np.linalg.norm(rw - re), np.linalg.norm(la - lk), np.linalg.norm(ra - rk))
            scale = max(280.0, shoulder_span * 3.0, hip_span * 3.5, limb_span * 1.8)

            # place avatar more toward the user’s torso and enlarge it significantly
            cx = int(np.clip(torso_center[0], 0, w - 1))
            cy = int(np.clip(torso_center[1] * 0.92, 0, h - 1))

            verts = positions.copy()
            verts[:, 1] *= -1
            verts -= np.nanmean(verts, axis=0)
            verts[:, 0] = verts[:, 0] * scale + cx
            verts[:, 1] = verts[:, 1] * scale + cy
            verts[:, 2] = 0
            verts = np.nan_to_num(verts, nan=0.0, posinf=0.0, neginf=0.0)

            overlay = np.zeros_like(frame)
            for face in indices[:]:
                tri = verts[face, :2]
                tri[:, 0] = np.clip(tri[:, 0], -2000, w + 2000)
                tri[:, 1] = np.clip(tri[:, 1], -2000, h + 2000)
                pts = tri.astype(np.int32)
                if np.isfinite(pts).all():
                    cv2.fillConvexPoly(overlay, pts, (0, 255, 255), lineType=cv2.LINE_AA)
            frame = cv2.addWeighted(frame, 0.05, overlay, 0.95, 0)
            cv2.putText(frame, f'SCALE {scale:.1f}', (20, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2, cv2.LINE_AA)
            cv2.putText(frame, 'GLB ENLARGED + CENTERED ON TORSO', (20, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2, cv2.LINE_AA)
        else:
            cv2.rectangle(frame, (0, 0), (frame.shape[1], 90), (0, 0, 255), -1)
            cv2.putText(frame, 'I CANNOT SEE YOU', (20, 38), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255,255,255), 3, cv2.LINE_AA)

        cv2.imshow('Body Tracking Status', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
