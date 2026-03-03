"""
SENTINEL — Gesture Control Module
Detects hand gestures via webcam and maps them to system actions.
Can be launched standalone or from the Streamlit app.

Gesture → Action mapping:
  Fist           → Minimize all windows  (Win+D)
  Open Palm      → Play / Pause          (Space)
  Peace (V)      → Screenshot
  Thumbs Up      → Volume Up
  Rock On        → Volume Down
  Three fingers  → Alt+Tab
  Pinky only     → Mute / Unmute
  Pointing       → Pointer (no action)
  Gun            → Enter
  Swipe Left     → Previous  (Left arrow)
  Swipe Right    → Next      (Right arrow)
"""

import cv2
import mediapipe as mp
import numpy as np
try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
import time
import math
import os
import sys
import json
import datetime

from mediapipe.tasks.python.vision import (
    HandLandmarker,
    HandLandmarkerOptions,
    HandLandmarksConnections,
    RunningMode,
)
from mediapipe.tasks.python import BaseOptions

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(PROJECT_ROOT, "models", "hand_landmarker.task")
HAND_CONNECTIONS = HandLandmarksConnections.HAND_CONNECTIONS

# ── Gesture → Action table ────────────────────────────
GESTURE_ACTIONS = {
    "Fist": {
        "label": "Minimize All (Win+D)",
        "action": "hotkey", "keys": ["win", "d"],
        "icon": "✊", "color": (0, 0, 255),
    },
    "Open Palm": {
        "label": "Play / Pause (Space)",
        "action": "press", "keys": ["space"],
        "icon": "🖐️", "color": (0, 255, 0),
    },
    "Peace": {
        "label": "Screenshot",
        "action": "screenshot", "keys": [],
        "icon": "✌️", "color": (255, 200, 0),
    },
    "Thumbs Up": {
        "label": "Volume Up",
        "action": "press", "keys": ["volumeup"],
        "icon": "👍", "color": (0, 200, 255),
    },
    "Rock On": {
        "label": "Volume Down",
        "action": "press", "keys": ["volumedown"],
        "icon": "🤘", "color": (200, 0, 255),
    },
    "Three": {
        "label": "Alt + Tab",
        "action": "hotkey", "keys": ["alt", "tab"],
        "icon": "3️⃣", "color": (255, 128, 0),
    },
    "Pinky": {
        "label": "Mute / Unmute",
        "action": "press", "keys": ["volumemute"],
        "icon": "🤙", "color": (128, 0, 255),
    },
    "Gun": {
        "label": "Enter",
        "action": "press", "keys": ["enter"],
        "icon": "👉", "color": (200, 200, 0),
    },
    "Swipe Left": {
        "label": "Previous (←)",
        "action": "press", "keys": ["left"],
        "icon": "👈", "color": (255, 128, 128),
    },
    "Swipe Right": {
        "label": "Next (→)",
        "action": "press", "keys": ["right"],
        "icon": "👉", "color": (128, 255, 128),
    },
}


class GestureController:
    """Real-time hand gesture controller using MediaPipe + PyAutoGUI."""

    def __init__(self, sensitivity=5, user_id=None, db_logging=True):
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Hand model not found: {MODEL_PATH}")

        self._latest_result = None
        self.user_id = user_id
        self.db_logging = db_logging

        def _cb(result, output_image, timestamp_ms):
            self._latest_result = result

        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=RunningMode.LIVE_STREAM,
            num_hands=1,
            min_hand_detection_confidence=max(0.3, 0.4 + (sensitivity - 5) * 0.05),
            min_hand_presence_confidence=max(0.3, 0.4 + (sensitivity - 5) * 0.05),
            min_tracking_confidence=max(0.3, 0.4 + (sensitivity - 5) * 0.05),
            result_callback=_cb,
        )
        self.landmarker = HandLandmarker.create_from_options(options)

        # Pyautogui settings
        if PYAUTOGUI_AVAILABLE:
            pyautogui.FAILSAFE = False
            pyautogui.PAUSE = 0

        # Cooldowns (in frames)
        self.cooldown = {}
        self.default_cooldown = max(10, 20 - sensitivity)
        self.sensitivity = sensitivity

        # Swipe detection
        self.wrist_history = []
        self.swipe_cooldown = 0
        self.swipe_threshold = max(0.08, 0.20 - sensitivity * 0.012)

        # FPS
        self.prev_time = 0

        # Action log for HUD
        self.last_action = ""
        self.last_action_time = 0

        # Stats
        self.gesture_counts = {}

    # ── Hand detection ────────────────────────
    @property
    def hand_landmarks(self):
        if self._latest_result and self._latest_result.hand_landmarks:
            return self._latest_result.hand_landmarks
        return []

    @property
    def handedness_list(self):
        if self._latest_result and self._latest_result.handedness:
            return self._latest_result.handedness
        return []

    def get_positions(self, frame, hand_index=0):
        lms = self.hand_landmarks
        if hand_index < len(lms):
            h, w, _ = frame.shape
            return [(i, int(lm.x * w), int(lm.y * h)) for i, lm in enumerate(lms[hand_index])]
        return []

    # ── Finger counting ───────────────────────
    def count_fingers(self, frame, hand_index=0):
        pos = self.get_positions(frame, hand_index)
        if not pos:
            return 0, []

        fingers = []
        handedness = "Right"
        hl = self.handedness_list
        if hand_index < len(hl):
            handedness = hl[hand_index][0].category_name

        # Thumb
        if handedness == "Right":
            fingers.append(1 if pos[4][1] < pos[3][1] else 0)
        else:
            fingers.append(1 if pos[4][1] > pos[3][1] else 0)

        # Other fingers
        for tip in [8, 12, 16, 20]:
            fingers.append(1 if pos[tip][2] < pos[tip - 2][2] else 0)

        return sum(fingers), fingers

    # ── Gesture recognition ───────────────────
    def detect_gesture(self, fingers):
        if not fingers:
            return ""
        total = sum(fingers)
        if total == 0: return "Fist"
        if total == 5: return "Open Palm"
        if fingers == [0, 1, 0, 0, 0]: return "Pointing"
        if fingers == [0, 1, 1, 0, 0]: return "Peace"
        if fingers == [1, 0, 0, 0, 1]: return "Rock On"
        if fingers == [1, 1, 0, 0, 0]: return "Gun"
        if fingers == [1, 0, 0, 0, 0]: return "Thumbs Up"
        if fingers == [0, 1, 1, 1, 0]: return "Three"
        if fingers == [0, 0, 0, 0, 1]: return "Pinky"
        return f"{total} Fingers"

    # ── Swipe detection ───────────────────────
    def detect_swipe(self, frame):
        lms = self.hand_landmarks
        if not lms:
            self.wrist_history.clear()
            return None

        wrist = lms[0][0]  # landmark 0 = wrist
        self.wrist_history.append((wrist.x, time.time()))

        # Keep last 15 frames
        if len(self.wrist_history) > 15:
            self.wrist_history.pop(0)

        if len(self.wrist_history) < 8:
            return None

        if self.swipe_cooldown > 0:
            self.swipe_cooldown -= 1
            return None

        # Compare oldest vs newest
        old_x = self.wrist_history[0][0]
        new_x = self.wrist_history[-1][0]
        dx = new_x - old_x

        if abs(dx) > self.swipe_threshold:
            self.swipe_cooldown = self.default_cooldown
            self.wrist_history.clear()
            return "Swipe Right" if dx > 0 else "Swipe Left"

        return None

    # ── Execute action ────────────────────────
    def execute_action(self, gesture_name):
        """Execute the mapped action for a gesture."""
        if gesture_name not in GESTURE_ACTIONS:
            return

        # Check cooldown
        if gesture_name in self.cooldown and self.cooldown[gesture_name] > 0:
            return

        action_info = GESTURE_ACTIONS[gesture_name]
        action = action_info["action"]
        keys = action_info["keys"]

        try:
            if not PYAUTOGUI_AVAILABLE:
                return
            if action == "press":
                pyautogui.press(keys[0])
            elif action == "hotkey":
                pyautogui.hotkey(*keys)
            elif action == "screenshot":
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                path = os.path.join(PROJECT_ROOT, f"screenshot_{ts}.png")
                pyautogui.screenshot(path)

            # Set cooldown
            self.cooldown[gesture_name] = self.default_cooldown

            # Track
            self.last_action = f"{action_info['icon']} {action_info['label']}"
            self.last_action_time = time.time()
            self.gesture_counts[gesture_name] = self.gesture_counts.get(gesture_name, 0) + 1

            # Log to DB
            if self.db_logging:
                try:
                    sys.path.insert(0, PROJECT_ROOT)
                    from modules import database as db
                    db.init_db()
                    db.add_log(self.user_id, "gesture_used",
                               f"{gesture_name} → {action_info['label']}")
                except Exception:
                    pass

        except Exception as e:
            self.last_action = f"Error: {e}"

    # ── Drawing helpers ───────────────────────
    def draw_skeleton(self, frame):
        h, w, _ = frame.shape
        for idx, landmarks in enumerate(self.hand_landmarks):
            pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
            for conn in HAND_CONNECTIONS:
                cv2.line(frame, pts[conn.start], pts[conn.end], (0, 180, 0), 2, cv2.LINE_AA)
            for pt in pts:
                cv2.circle(frame, pt, 4, (0, 255, 128), cv2.FILLED)
            # Highlight fingertips
            for tip in [4, 8, 12, 16, 20]:
                cv2.circle(frame, pts[tip], 8, (0, 200, 255), cv2.FILLED)

    def draw_hud(self, frame, gesture, fps):
        h, w, _ = frame.shape

        # Background panel
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (420, 180), (15, 15, 30), cv2.FILLED)
        cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)

        cv2.putText(frame, "SENTINEL Gesture Control", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 212, 255), 2)
        cv2.putText(frame, f"FPS: {int(fps)}  |  Sensitivity: {self.sensitivity}", (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

        # Current gesture
        if gesture and gesture in GESTURE_ACTIONS:
            info = GESTURE_ACTIONS[gesture]
            cv2.putText(frame, f"Gesture: {gesture}", (20, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, info["color"], 2)
            cv2.putText(frame, f"Action: {info['label']}", (20, 130),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 200), 1)
        elif gesture:
            cv2.putText(frame, f"Gesture: {gesture}", (20, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)

        # Last action flash
        if self.last_action and (time.time() - self.last_action_time) < 2.0:
            cv2.putText(frame, self.last_action, (20, 160),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 100), 2)

        # Help bar at bottom
        help_text = "Fist=Min | Palm=Play | Peace=SS | ThumbUp=Vol+ | RockOn=Vol- | q=Quit"
        cv2.putText(frame, help_text, (10, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 120, 120), 1)

        # Gesture guide on right side
        guide_x = w - 220
        cv2.rectangle(frame, (guide_x - 10, 10), (w - 10, 280), (15, 15, 30), cv2.FILLED)
        cv2.putText(frame, "Gesture Guide", (guide_x, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 212, 255), 1)
        y = 60
        for name, info in list(GESTURE_ACTIONS.items())[:8]:
            color = info["color"] if name == gesture else (100, 100, 100)
            cv2.putText(frame, f"{info['icon']} {name[:12]}", (guide_x, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1)
            y += 28

    @staticmethod
    def camera_available():
        """Check if a webcam is accessible (returns True/False without holding the device)."""
        try:
            cap = cv2.VideoCapture(0)
            ok = cap.isOpened()
            cap.release()
            return ok
        except Exception:
            return False

    # ── Main loop ─────────────────────────────
    def run(self):
        """Open webcam and start gesture control loop."""
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        if not cap.isOpened():
            print("ERROR: Cannot open webcam. Gesture control requires a local camera.")
            print("This feature does not work on cloud servers (e.g., Streamlit Cloud).")
            return

        print("=" * 55)
        print("  SENTINEL — Gesture Control Active")
        print("=" * 55)
        print("  Press 'q' to quit")
        print()

        frame_ts = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)

            # Detect
            frame_ts += 33
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            self.landmarker.detect_async(mp_image, frame_ts)

            # Decrement cooldowns
            for k in list(self.cooldown.keys()):
                if self.cooldown[k] > 0:
                    self.cooldown[k] -= 1

            # Recognize gesture
            gesture = ""
            if self.hand_landmarks:
                _, fingers = self.count_fingers(frame)
                gesture = self.detect_gesture(fingers)

                # Check for swipe first
                swipe = self.detect_swipe(frame)
                if swipe:
                    gesture = swipe
                    self.execute_action(swipe)
                elif gesture in GESTURE_ACTIONS and gesture != "Pointing":
                    self.execute_action(gesture)
            else:
                self.wrist_history.clear()

            # Draw
            self.draw_skeleton(frame)

            # FPS
            ct = time.time()
            fps = 1 / (ct - self.prev_time) if self.prev_time else 0
            self.prev_time = ct

            self.draw_hud(frame, gesture, fps)

            cv2.imshow("SENTINEL Gesture Control", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        # Print session summary
        print("\n  Session Summary:")
        for g, c in sorted(self.gesture_counts.items(), key=lambda x: -x[1]):
            print(f"    {g}: {c} times")
        print()

        self.landmarker.close()
        cap.release()
        cv2.destroyAllWindows()
        print("  Gesture Control stopped.")


# ── Standalone entry point ────────────────────
if __name__ == "__main__":
    # Accept optional args: sensitivity, user_id
    sensitivity = 5
    user_id = None
    if len(sys.argv) > 1:
        try:
            sensitivity = int(sys.argv[1])
        except ValueError:
            pass
    if len(sys.argv) > 2:
        try:
            user_id = int(sys.argv[2])
        except ValueError:
            pass

    controller = GestureController(sensitivity=sensitivity, user_id=user_id)
    controller.run()
