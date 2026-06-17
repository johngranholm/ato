import os
import math
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from pygltflib import GLTF2
from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *

GLB_PATH = r"C:\brunette.glb"
MODEL_PATH = r"C:\ato\workspace\workspace\bodyTracker\pose_landmarker.task"

L = {
    'LEFT_SHOULDER': 11, 'RIGHT_SHOULDER': 12,
    'LEFT_ELBOW': 13, 'RIGHT_ELBOW': 14,
    'LEFT_WRIST': 15, 'RIGHT_WRIST': 16,
    'LEFT_HIP': 23, 'RIGHT_HIP': 24,
    'LEFT_KNEE': 25, 'RIGHT_KNEE': 26,
    'LEFT_ANKLE': 27, 'RIGHT_ANKLE': 28,
}


def create_landmarker():
    base = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.PoseLandmarkerOptions(base_options=base, running_mode=vision.RunningMode.VIDEO)
    return vision.PoseLandmarker.create_from_options(options)


def read_accessor(gltf, idx):
    acc = gltf.accessors[idx]
    bv = gltf.bufferViews[acc.bufferView]
    blob = gltf.binary_blob()
    offset = (bv.byteOffset or 0) + (acc.byteOffset or 0)
    dtype = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}.get(acc.componentType, np.float32)
    shape = {'MAT4': (acc.count, 4, 4), 'VEC4': (acc.count, 4), 'VEC3': (acc.count, 3)}.get(acc.type, (acc.count,))
    return np.frombuffer(blob, dtype=dtype, count=int(np.prod(shape)), offset=offset).reshape(shape).copy()


def vec3(lms, name, w, h):
    p = lms[L[name]]
    return np.array([p.x * w, p.y * h, p.z], dtype=np.float32)


def skin_transform(a, b):
    d = b - a
    ln = max(1e-6, float(np.linalg.norm(d)))
    y = np.array([0, 1, 0], dtype=np.float32)
    dn = d / ln
    axis = np.cross(y, dn)
    c = float(np.clip(np.dot(y, dn), -1.0, 1.0))
    if c > 0.9999:
        R = np.eye(3, dtype=np.float32)
    elif c < -0.9999:
        R = np.array([[1,0,0],[0,-1,0],[0,0,-1]], dtype=np.float32)
    else:
        axis = axis / (np.linalg.norm(axis) + 1e-6)
        ang = math.acos(c)
        x, y2, z = axis
        ca, sa = math.cos(ang), math.sin(ang)
        t = 1 - ca
        R = np.array([[t*x*x+ca, t*x*y2-sa*z, t*x*z+sa*y2], [t*x*y2+sa*z, t*y2*y2+ca, t*y2*z-sa*x], [t*x*z-sa*y2, t*y2*z+sa*x, t*z*z+ca]], dtype=np.float32)
    M = np.eye(4, dtype=np.float32)
    M[:3, :3] = R * ln
    M[:3, 3] = a
    return M


def main():
    gltf = GLTF2().load(GLB_PATH)
    prim = gltf.meshes[0].primitives[0]
    skin = gltf.skins[0]
    positions = read_accessor(gltf, prim.attributes.POSITION).astype(np.float32)
    indices = read_accessor(gltf, prim.indices).astype(np.int32).reshape(-1, 3)
    weights = read_accessor(gltf, prim.attributes.WEIGHTS_0).astype(np.float32)
    joints = read_accessor(gltf, prim.attributes.JOINTS_0).astype(np.int32)
    ibm = read_accessor(gltf, skin.inverseBindMatrices).astype(np.float32)
    joint_names = [gltf.nodes[j].name for j in skin.joints]
    joint_index = {n: i for i, n in enumerate(joint_names) if n}
    print('Loaded GLB:', GLB_PATH)

    pose = create_landmarker()
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError('Could not open webcam')

    state = {'pose': None, 'w': 0, 'h': 0, 'frame_index': 0}

    def tick_pose():
        ok, frame = cap.read()
        if not ok:
            return False
        frame = cv2.flip(frame, 1)
        state['w'], state['h'] = frame.shape[1], frame.shape[0]
        res = pose.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), state['frame_index'])
        state['frame_index'] += 1
        state['pose'] = res.pose_landmarks[0] if res.pose_landmarks else None
        return True

    def display():
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        gluLookAt(0, 1.2, 5.0, 0, 1.0, 0, 0, 1, 0)
        glColor3f(1.0, 0.86, 0.95)
        if state['pose'] is not None:
            lms = state['pose']
            pts = {k: vec3(lms, k.upper(), state['w'], state['h']) for k in ['left_shoulder','right_shoulder','left_hip','right_hip','left_elbow','right_elbow','left_wrist','right_wrist','left_knee','right_knee','left_ankle','right_ankle']}
            joint_mats = [np.eye(4, dtype=np.float32) for _ in skin.joints]
            for nm, a, b in [('LeftArm', pts['left_shoulder'], pts['left_elbow']), ('LeftForeArm', pts['left_elbow'], pts['left_wrist']), ('RightArm', pts['right_shoulder'], pts['right_elbow']), ('RightForeArm', pts['right_elbow'], pts['right_wrist']), ('LeftUpLeg', pts['left_hip'], pts['left_knee']), ('LeftLeg', pts['left_knee'], pts['left_ankle']), ('RightUpLeg', pts['right_hip'], pts['right_knee']), ('RightLeg', pts['right_knee'], pts['right_ankle'])]:
                if nm in joint_index:
                    i = joint_index[nm]
                    joint_mats[i] = skin_transform(a / 250.0, b / 250.0) @ ibm[i]
            deformed = np.zeros_like(positions)
            for vi in range(len(positions)):
                p = np.append(positions[vi], 1.0)
                acc = np.zeros(4, dtype=np.float32)
                for k in range(4):
                    w = float(weights[vi, k])
                    j = int(joints[vi, k])
                    if w > 0 and 0 <= j < len(joint_mats):
                        acc += w * (joint_mats[j] @ p)
                deformed[vi] = acc[:3]
            deformed -= np.mean(deformed, axis=0)
            deformed *= 1.8
            glBegin(GL_TRIANGLES)
            for tri in indices:
                for idx in tri:
                    v = deformed[idx]
                    glVertex3f(float(v[0]), float(v[1]), float(v[2]))
            glEnd()
        glutSwapBuffers()

    def idle():
        if tick_pose():
            glutPostRedisplay()

    glutInit()
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH)
    glutInitWindowSize(1280, 720)
    glutCreateWindow(b'Brunette GLB 3D Scene')
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_CULL_FACE)
    glClearColor(0.08, 0.08, 0.12, 1.0)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(45, 1280 / 720, 0.1, 100.0)
    glMatrixMode(GL_MODELVIEW)
    glutDisplayFunc(display)
    glutIdleFunc(idle)
    glutMainLoop()


if __name__ == '__main__':
    main()
