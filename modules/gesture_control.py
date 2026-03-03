"""
SENTINEL — Gesture Control Module (Optimized)
High-performance hand gesture controller with:
  • Real-time monotonic timestamps for accurate async detection
  • Gesture stabilization buffer (multi-frame confirmation)
  • Time-based cooldowns (consistent across all frame rates)
  • Reduced detection resolution for speed (detect at 640×480)
  • Cached database connection (init once, not per action)
  • Velocity-based swipe detection
  • Smoothed FPS counter (exponential moving average)

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
import datetime
from collections import deque

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
    """High-performance hand gesture controller using MediaPipe + PyAutoGUI."""

    # Detection resolution (lower = faster inference, display stays at capture res)
    DETECT_W = 640
    DETECT_H = 480

    def __init__(self, sensitivity=5, user_id=None, db_logging=True):
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Hand model not found: {MODEL_PATH}")

        self._latest_result = None
        self.user_id = user_id
        self.db_logging = db_logging
        self.sensitivity = sensitivity

        # ── MediaPipe landmarker (async with callback) ──
        def _on_result(result, output_image, timestamp_ms):
            self._latest_result = result

        conf = max(0.35, 0.45 + (sensitivity - 5) * 0.04)
        track_conf = max(0.30, 0.40 + (sensitivity - 5) * 0.04)
        options = HandLandmarkerOptions(
            base_options=BaseOptions(
                model_asset_path=MODEL_PATH,
                delegate=BaseOptions.Delegate.CPU,
            ),
            running_mode=RunningMode.LIVE_STREAM,
            num_hands=1,
            min_hand_detection_confidence=conf,
            min_hand_presence_confidence=conf,
            min_tracking_confidence=track_conf,
            result_callback=_on_result,
        )
        self.landmarker = HandLandmarker.create_from_options(options)

        # ── Time-based cooldowns (seconds) ──
        self._cooldown_duration = max(0.3, 0.8 - sensitivity * 0.05)  # 0.3–0.55s
        self._cooldown_until = {}  # gesture_name → timestamp when cooldown expires

        # ── Gesture stabilization buffer ──
        # Require N consecutive identical detections before triggering
        self._confirm_frames = max(2, 4 - sensitivity // 3)  # 2–4 frames
        self._gesture_buffer = deque(maxlen=self._confirm_frames)

        # ── Swipe detection ──
        self._wrist_history = deque(maxlen=20)
        self._swipe_cooldown_until = 0.0
        self._swipe_threshold = max(0.06, 0.18 - sensitivity * 0.012)
        self._swipe_min_speed = 0.3  # normalized x-units per second

        # ── FPS (exponential moving average) ──
        self._fps_ema = 0.0
        self._fps_alpha = 0.1
        self._prev_time = time.perf_counter()

        # ── HUD state ──
        self._last_action = ""
        self._last_action_time = 0.0

        # ── Session stats ──
        self.gesture_counts = {}

        # ── Cached DB module (lazy-loaded once) ──
        self._db = None
        self._db_loaded = False

    # ── Lazy DB loader ────────────────────────
    def _get_db(self):
        if not self._db_loaded:
            self._db_loaded = True
            try:
                sys.path.insert(0, PROJECT_ROOT)
                from modules import database as _db_mod
                _db_mod.init_db()
                self._db = _db_mod
            except Exception:
                self._db = None
        return self._db

    # ── Hand detection properties ─────────────
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

    def get_positions(self, width, height, hand_index=0):
        """Get pixel positions for landmarks — uses width/height directly (no frame copy)."""
        lms = self.hand_landmarks
        if hand_index < len(lms):
            return [(i, int(lm.x * width), int(lm.y * height)) for i, lm in enumerate(lms[hand_index])]
        return []

    # ── Finger counting (optimized) ──────────
    def count_fingers(self, width, height, hand_index=0):
        pos = self.get_positions(width, height, hand_index)
        if len(pos) < 21:
            return 0, []

        fingers = []
        handedness = "Right"
        hl = self.handedness_list
        if hand_index < len(hl):
            handedness = hl[hand_index][0].category_name

        # Thumb — use angle-based detection for reliability
        # Vector from MCP (2) to tip (4) vs MCP to IP (3)
        thumb_tip_x, thumb_tip_y = pos[4][1], pos[4][2]
        thumb_ip_x, thumb_ip_y = pos[3][1], pos[3][2]
        thumb_mcp_x, thumb_mcp_y = pos[2][1], pos[2][2]
        wrist_x = pos[0][1]

        if handedness == "Right":
            fingers.append(1 if thumb_tip_x < thumb_ip_x and abs(thumb_tip_x - wrist_x) > 20 else 0)
        else:
            fingers.append(1 if thumb_tip_x > thumb_ip_x and abs(thumb_tip_x - wrist_x) > 20 else 0)

        # Index, Middle, Ring, Pinky — tip vs PIP (2 joints below tip)
        for tip in [8, 12, 16, 20]:
            fingers.append(1 if pos[tip][2] < pos[tip - 2][2] else 0)

        return sum(fingers), fingers

    # ── Gesture recognition ───────────────────
    def detect_gesture(self, fingers):
        if not fingers:
            return ""
        total = sum(fingers)

        # Fast path: check total first to reduce comparisons
        if total == 0:
            return "Fist"
        if total == 5:
            return "Open Palm"
        if total == 1:
            if fingers[1]:
                return "Pointing"
            if fingers[0]:
                return "Thumbs Up"
            if fingers[4]:
                return "Pinky"
        if total == 2:
            if fingers[1] and fingers[2]:
                return "Peace"
            if fingers[0] and fingers[4]:
                return "Rock On"
            if fingers[0] and fingers[1]:
                return "Gun"
        if total == 3:
            if fingers[1] and fingers[2] and fingers[3]:
                return "Three"

        return f"{total} Fingers"

    # ── Gesture stabilization ─────────────────
    def _stabilized_gesture(self, raw_gesture):
        """Return the gesture only if it has been consistent for N frames."""
        self._gesture_buffer.append(raw_gesture)

        # All recent frames must agree
        if len(self._gesture_buffer) == self._gesture_buffer.maxlen:
            if all(g == raw_gesture for g in self._gesture_buffer):
                return raw_gesture

        return ""

    # ── Velocity-based swipe detection ────────
    def detect_swipe(self):
        lms = self.hand_landmarks
        if not lms:
            self._wrist_history.clear()
            return None

        now = time.perf_counter()
        wrist = lms[0][0]
        self._wrist_history.append((wrist.x, wrist.y, now))

        if len(self._wrist_history) < 6:
            return None

        if now < self._swipe_cooldown_until:
            return None

        # Use a sliding window: compare positions over the last ~200ms
        cutoff = now - 0.25
        old = None
        for entry in self._wrist_history:
            if entry[2] >= cutoff:
                old = entry
                break
        if old is None:
            return None

        newest = self._wrist_history[-1]
        dx = newest[0] - old[0]
        dt = newest[2] - old[2]

        if dt < 0.05:
            return None

        speed = abs(dx) / dt  # normalized units per second

        if abs(dx) > self._swipe_threshold and speed > self._swipe_min_speed:
            self._swipe_cooldown_until = now + self._cooldown_duration
            self._wrist_history.clear()
            return "Swipe Right" if dx > 0 else "Swipe Left"

        return None

    # ── Execute action (time-based cooldown) ──
    def execute_action(self, gesture_name):
        """Execute the mapped action with time-based cooldown."""
        if gesture_name not in GESTURE_ACTIONS:
            return
        if not PYAUTOGUI_AVAILABLE:
            return

        now = time.perf_counter()
        if now < self._cooldown_until.get(gesture_name, 0):
            return

        action_info = GESTURE_ACTIONS[gesture_name]
        action_type = action_info["action"]
        keys = action_info["keys"]

        try:
            if action_type == "press":
                pyautogui.press(keys[0])
            elif action_type == "hotkey":
                pyautogui.hotkey(*keys)
            elif action_type == "screenshot":
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                path = os.path.join(PROJECT_ROOT, f"screenshot_{ts}.png")
                pyautogui.screenshot(path)

            # Set time-based cooldown
            self._cooldown_until[gesture_name] = now + self._cooldown_duration

            # Update HUD
            self._last_action = f"{action_info['icon']} {action_info['label']}"
            self._last_action_time = now

            # Stats
            self.gesture_counts[gesture_name] = self.gesture_counts.get(gesture_name, 0) + 1

            # Log to DB (lazy-loaded, no repeated init)
            if self.db_logging:
                db = self._get_db()
                if db:
                    try:
                        db.add_log(self.user_id, "gesture_used",
                                   f"{gesture_name} → {action_info['label']}")
                    except Exception:
                        pass

        except Exception as e:
            self._last_action = f"Error: {e}"

    # ── Drawing helpers (optimized) ───────────
    def draw_skeleton(self, frame):
        h, w = frame.shape[:2]
        for landmarks in self.hand_landmarks:
            pts = np.array([(int(lm.x * w), int(lm.y * h)) for lm in landmarks], dtype=np.int32)
            # Draw connections in batch
            for conn in HAND_CONNECTIONS:
                cv2.line(frame, tuple(pts[conn.start]), tuple(pts[conn.end]),
                         (0, 200, 100), 2, cv2.LINE_AA)
            # Draw all joint dots
            for pt in pts:
                cv2.circle(frame, tuple(pt), 3, (0, 255, 160), cv2.FILLED)
            # Highlight fingertips with larger circles
            for tip in [4, 8, 12, 16, 20]:
                cv2.circle(frame, tuple(pts[tip]), 7, (0, 220, 255), cv2.FILLED)

    def draw_hud(self, frame, gesture, fps):
        h, w = frame.shape[:2]
        now = time.perf_counter()

        # Semi-transparent HUD panel (top-left)
        overlay = frame[10:170, 10:400].copy()
        cv2.rectangle(frame, (10, 10), (400, 170), (15, 15, 30), cv2.FILLED)
        cv2.addWeighted(frame[10:170, 10:400], 0.75, overlay, 0.25, 0, frame[10:170, 10:400])

        cv2.putText(frame, "SENTINEL Gesture Control", (20, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 212, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f"FPS: {int(fps)}  |  Sensitivity: {self.sensitivity}", (20, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)

        # Current gesture
        if gesture and gesture in GESTURE_ACTIONS:
            info = GESTURE_ACTIONS[gesture]
            cv2.putText(frame, f"Gesture: {gesture}", (20, 95),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, info["color"], 2, cv2.LINE_AA)
            cv2.putText(frame, f"Action: {info['label']}", (20, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 200), 1, cv2.LINE_AA)
        elif gesture:
            cv2.putText(frame, f"Gesture: {gesture}", (20, 95),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 150, 150), 1, cv2.LINE_AA)

        # Last action flash (fades over 1.5 seconds)
        dt_action = now - self._last_action_time
        if self._last_action and dt_action < 1.5:
            alpha = max(0, 1.0 - dt_action / 1.5)
            green = int(255 * alpha)
            cv2.putText(frame, self._last_action, (20, 150),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, green, int(100 * alpha)), 2, cv2.LINE_AA)

        # Compact help bar at bottom
        cv2.putText(frame, "Fist=Min | Palm=Play | Peace=SS | ThumbUp=Vol+ | RockOn=Vol- | q=Quit",
                    (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (100, 100, 100), 1, cv2.LINE_AA)

        # Right-side gesture guide (smaller overlay)
        gx = w - 200
        overlay2 = frame[10:260, gx - 10:w - 10].copy()
        cv2.rectangle(frame, (gx - 10, 10), (w - 10, 260), (15, 15, 30), cv2.FILLED)
        cv2.addWeighted(frame[10:260, gx - 10:w - 10], 0.75, overlay2, 0.25, 0,
                        frame[10:260, gx - 10:w - 10])

        cv2.putText(frame, "Gesture Guide", (gx, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 212, 255), 1, cv2.LINE_AA)
        y = 55
        for name, info in list(GESTURE_ACTIONS.items())[:8]:
            color = info["color"] if name == gesture else (90, 90, 90)
            cv2.putText(frame, f"{info['icon']} {name[:12]}", (gx, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, color, 1, cv2.LINE_AA)
            y += 26

    @staticmethod
    def camera_available():
        """Check if a webcam is accessible."""
        try:
            cap = cv2.VideoCapture(0)
            ok = cap.isOpened()
            cap.release()
            return ok
        except Exception:
            return False

    # ── Main loop (optimized) ─────────────────
    def run(self):
        """Open webcam and start the optimized gesture control loop."""

        # Use DirectShow on Windows for faster capture
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(0, backend)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize capture latency

        if not cap.isOpened():
            print("ERROR: Cannot open webcam. Gesture control requires a local camera.")
            print("This feature does not work on cloud servers (e.g., Streamlit Cloud).")
            return

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print("=" * 55)
        print("  SENTINEL — Gesture Control Active (Optimized)")
        print(f"  Capture: {actual_w}×{actual_h}  |  Detection: {self.DETECT_W}×{self.DETECT_H}")
        print(f"  Sensitivity: {self.sensitivity}  |  Confirm frames: {self._confirm_frames}")
        print("=" * 55)
        print("  Press 'q' to quit")
        print()

        # Use monotonic time for MediaPipe timestamps (must be strictly increasing)
        _t0 = time.perf_counter()

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            now = time.perf_counter()

            # ── Run detection on downscaled frame for speed ──
            if actual_w > self.DETECT_W or actual_h > self.DETECT_H:
                small = cv2.resize(frame, (self.DETECT_W, self.DETECT_H), interpolation=cv2.INTER_LINEAR)
            else:
                small = frame

            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            # Monotonic timestamp in milliseconds (strictly increasing, integer)
            ts_ms = int((now - _t0) * 1000)
            self.landmarker.detect_async(mp_image, ts_ms)

            # ── Gesture recognition with stabilization ──
            gesture = ""
            if self.hand_landmarks:
                _, fingers = self.count_fingers(actual_w, actual_h)
                raw_gesture = self.detect_gesture(fingers)

                # Check swipe first (bypasses stabilization — swipes are transient)
                swipe = self.detect_swipe()
                if swipe:
                    gesture = swipe
                    self.execute_action(swipe)
                else:
                    # Apply stabilization buffer
                    stable = self._stabilized_gesture(raw_gesture)
                    if stable:
                        gesture = stable
                        if gesture in GESTURE_ACTIONS and gesture != "Pointing":
                            self.execute_action(gesture)
                    else:
                        gesture = raw_gesture  # Show raw on HUD but don't trigger
            else:
                self._wrist_history.clear()
                self._gesture_buffer.clear()

            # ── Draw overlays ──
            self.draw_skeleton(frame)

            # ── FPS with EMA smoothing ──
            dt = now - self._prev_time
            if dt > 0:
                instant_fps = 1.0 / dt
                self._fps_ema = self._fps_alpha * instant_fps + (1 - self._fps_alpha) * self._fps_ema
            self._prev_time = now

            self.draw_hud(frame, gesture, self._fps_ema)

            cv2.imshow("SENTINEL Gesture Control", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        # ── Session summary ──
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
