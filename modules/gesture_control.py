"""
SENTINEL — Gesture Control Module (Mouse Controller)
Controls the mouse cursor and system with hand gestures.

Gestures:
  INDEX FINGER ONLY  -> Move mouse cursor (finger position maps to screen)
  THUMB + INDEX PINCH -> Left click (bring thumb & index together)
  TWO FINGERS (V)    -> Scroll (move hand up/down with peace sign)
  FIST (closed hand) -> Pause / Stop tracking (neutral mode)
  OPEN PALM (5)      -> Right click
  THREE FINGERS      -> Double click
  THUMBS UP          -> Volume Up
  ROCK ON            -> Volume Down

Design:
  - Actions only fire ONCE per gesture transition (not continuously)
  - Mouse movement is smoothed with exponential moving average
  - Click requires pinch distance < threshold, fires once on pinch-close
  - Scroll only activates with 2-finger V sign and Y movement
  - Fist = safe neutral state, nothing happens
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


# ── Gesture definitions (for UI display) ──────────
GESTURE_INFO = {
    "Move": {
        "label": "Mouse Move",
        "desc": "Point index finger to move cursor",
        "symbol": "[->]",
        "color": (0, 255, 128),
    },
    "Click": {
        "label": "Left Click",
        "desc": "Pinch thumb + index together",
        "symbol": "[*]",
        "color": (0, 200, 255),
    },
    "Scroll": {
        "label": "Scroll",
        "desc": "V sign (2 fingers) + move up/down",
        "symbol": "[||]",
        "color": (255, 200, 0),
    },
    "Pause": {
        "label": "Pause (Fist)",
        "desc": "Close fist to stop tracking",
        "symbol": "[X]",
        "color": (0, 0, 255),
    },
    "Right Click": {
        "label": "Right Click",
        "desc": "Open palm (all 5 fingers)",
        "symbol": "[**]",
        "color": (0, 255, 0),
    },
    "Double Click": {
        "label": "Double Click",
        "desc": "Three fingers up",
        "symbol": "[**!]",
        "color": (255, 128, 0),
    },
    "Vol Up": {
        "label": "Volume Up",
        "desc": "Thumbs up",
        "symbol": "[+]",
        "color": (0, 200, 255),
    },
    "Vol Down": {
        "label": "Volume Down",
        "desc": "Rock on sign",
        "symbol": "[-]",
        "color": (200, 0, 255),
    },
}


class GestureController:
    """Mouse-control gesture system using MediaPipe hand tracking."""

    DETECT_W = 640
    DETECT_H = 480

    def __init__(self, sensitivity=5, user_id=None, db_logging=True):
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Hand model not found: {MODEL_PATH}")

        self._latest_result = None
        self.user_id = user_id
        self.db_logging = db_logging
        self.sensitivity = sensitivity

        # ── MediaPipe HandLandmarker ──
        def _on_result(result, output_image, timestamp_ms):
            self._latest_result = result

        conf = max(0.40, 0.50 + (sensitivity - 5) * 0.03)
        track_conf = max(0.35, 0.45 + (sensitivity - 5) * 0.03)
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

        # ── Screen size ──
        if PYAUTOGUI_AVAILABLE:
            self.screen_w, self.screen_h = pyautogui.size()
        else:
            self.screen_w, self.screen_h = 1920, 1080

        # ── Mouse smoothing ──
        self._smooth_x = self.screen_w / 2
        self._smooth_y = self.screen_h / 2
        self._smoothing = max(0.15, 0.50 - sensitivity * 0.035)  # Lower = smoother

        # ── Gesture state tracking (prevents repeated firing) ──
        self._prev_gesture = ""
        self._pinch_was_closed = False
        self._palm_was_open = False
        self._three_was_shown = False

        # ── Click cooldown ──
        self._last_click_time = 0.0
        self._click_cooldown = max(0.25, 0.5 - sensitivity * 0.025)

        # ── Scroll state ──
        self._scroll_base_y = None
        self._scroll_active = False
        self._last_scroll_time = 0.0
        self._scroll_cooldown = 0.05  # Fast scrolling allowed

        # ── Action cooldowns for keyboard actions ──
        self._action_cooldowns = {}
        self._action_cooldown_duration = max(0.5, 1.0 - sensitivity * 0.05)

        # ── Pinch threshold (normalized distance) ──
        self._pinch_threshold = max(0.03, 0.055 - sensitivity * 0.002)

        # ── FPS ──
        self._fps_ema = 0.0
        self._prev_time = time.perf_counter()

        # ── HUD ──
        self._last_action = ""
        self._last_action_time = 0.0
        self._current_mode = "Waiting..."

        # ── Stats ──
        self.gesture_counts = {}

        # ── DB cache ──
        self._db = None
        self._db_loaded = False

        # ── Camera mapping region (center 60% of camera frame) ──
        self._map_margin = 0.20  # 20% margin on each side

    # ── Lazy DB ──
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

    # ── Hand detection properties ──
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

    # ── Finger state detection ──
    def get_finger_states(self, hand_index=0):
        """Returns [thumb, index, middle, ring, pinky] as 0/1 list."""
        lms = self.hand_landmarks
        if hand_index >= len(lms) or len(lms[hand_index]) < 21:
            return []

        landmarks = lms[hand_index]
        fingers = []

        # Determine handedness
        handedness = "Right"
        hl = self.handedness_list
        if hand_index < len(hl):
            handedness = hl[hand_index][0].category_name

        # Thumb: compare tip.x vs IP.x (depends on hand side)
        if handedness == "Right":
            fingers.append(1 if landmarks[4].x < landmarks[3].x else 0)
        else:
            fingers.append(1 if landmarks[4].x > landmarks[3].x else 0)

        # Index, Middle, Ring, Pinky: tip.y < PIP.y means finger is up
        for tip_id in [8, 12, 16, 20]:
            fingers.append(1 if landmarks[tip_id].y < landmarks[tip_id - 2].y else 0)

        return fingers

    def get_pinch_distance(self, hand_index=0):
        """Normalized distance between thumb tip (4) and index tip (8)."""
        lms = self.hand_landmarks
        if hand_index >= len(lms):
            return 1.0
        landmarks = lms[hand_index]
        dx = landmarks[4].x - landmarks[8].x
        dy = landmarks[4].y - landmarks[8].y
        return math.sqrt(dx * dx + dy * dy)

    def get_index_tip_pos(self, hand_index=0):
        """Return (normalized_x, normalized_y) of index fingertip."""
        lms = self.hand_landmarks
        if hand_index >= len(lms):
            return None
        return (lms[hand_index][8].x, lms[hand_index][8].y)

    def get_middle_tip_y(self, hand_index=0):
        """Return normalized Y of middle fingertip (for scroll)."""
        lms = self.hand_landmarks
        if hand_index >= len(lms):
            return None
        # Average of index and middle for stable scroll position
        return (lms[hand_index][8].y + lms[hand_index][12].y) / 2.0

    # ── Gesture recognition ──
    def recognize_gesture(self):
        """Identify current gesture from finger states."""
        fingers = self.get_finger_states()
        if not fingers:
            return "None"

        total = sum(fingers)
        thumb, index, middle, ring, pinky = fingers

        # Fist: all closed
        if total == 0:
            return "Pause"

        # Open Palm: all open
        if total == 5:
            return "Right Click"

        # Index only: mouse move
        if index and not middle and not ring and not pinky and not thumb:
            return "Move"

        # Thumb + Index only → check pinch distance for click
        if thumb and index and not middle and not ring and not pinky:
            dist = self.get_pinch_distance()
            if dist < self._pinch_threshold:
                return "Click"
            else:
                return "Move"  # Thumb+Index apart = still move mode

        # V sign (index + middle): scroll
        if index and middle and not ring and not pinky:
            return "Scroll"

        # Three fingers (index + middle + ring)
        if index and middle and ring and not pinky:
            return "Double Click"

        # Thumbs up
        if thumb and not index and not middle and not ring and not pinky:
            return "Vol Up"

        # Rock on (thumb + pinky)
        if thumb and pinky and not index and not middle and not ring:
            return "Vol Down"

        # Index only pointing (for move) - catch any remaining single finger
        if total == 1 and index:
            return "Move"

        return "Idle"

    # ── Mouse movement (smoothed) ──
    def move_mouse(self):
        """Map index fingertip position to screen coordinates with EMA smoothing."""
        if not PYAUTOGUI_AVAILABLE:
            return

        tip = self.get_index_tip_pos()
        if tip is None:
            return

        raw_x, raw_y = tip

        # Map camera region to full screen (with margins)
        margin = self._map_margin
        mapped_x = (raw_x - margin) / (1.0 - 2 * margin)
        mapped_y = (raw_y - margin) / (1.0 - 2 * margin)

        # Clamp
        mapped_x = max(0.0, min(1.0, mapped_x))
        mapped_y = max(0.0, min(1.0, mapped_y))

        # Convert to screen pixels
        target_x = mapped_x * self.screen_w
        target_y = mapped_y * self.screen_h

        # Exponential moving average smoothing
        self._smooth_x += (target_x - self._smooth_x) * self._smoothing
        self._smooth_y += (target_y - self._smooth_y) * self._smoothing

        # Move cursor
        try:
            pyautogui.moveTo(int(self._smooth_x), int(self._smooth_y), _pause=False)
        except Exception:
            pass

    # ── Click (fires once on pinch) ──
    def try_click(self):
        """Left click — fires once when pinch first detected, not continuously."""
        if not PYAUTOGUI_AVAILABLE:
            return

        now = time.perf_counter()
        if now - self._last_click_time < self._click_cooldown:
            return

        dist = self.get_pinch_distance()
        is_pinched = dist < self._pinch_threshold

        # Fire only on transition: open -> closed
        if is_pinched and not self._pinch_was_closed:
            try:
                pyautogui.click(_pause=False)
                self._last_click_time = now
                self._last_action = "Left Click"
                self._last_action_time = now
                self._count("Click")
                self._log_gesture("Click -> Left Click")
            except Exception:
                pass

        self._pinch_was_closed = is_pinched

    # ── Right click (fires once on palm open transition) ──
    def try_right_click(self):
        if not PYAUTOGUI_AVAILABLE:
            return

        now = time.perf_counter()
        if now - self._last_click_time < self._click_cooldown:
            return

        # Fire only on transition: not-palm -> palm
        if not self._palm_was_open:
            try:
                pyautogui.rightClick(_pause=False)
                self._last_click_time = now
                self._last_action = "Right Click"
                self._last_action_time = now
                self._count("Right Click")
                self._log_gesture("Open Palm -> Right Click")
            except Exception:
                pass

        self._palm_was_open = True

    # ── Double click ──
    def try_double_click(self):
        if not PYAUTOGUI_AVAILABLE:
            return

        now = time.perf_counter()
        if now - self._last_click_time < self._click_cooldown:
            return

        if not self._three_was_shown:
            try:
                pyautogui.doubleClick(_pause=False)
                self._last_click_time = now
                self._last_action = "Double Click"
                self._last_action_time = now
                self._count("Double Click")
                self._log_gesture("Three Fingers -> Double Click")
            except Exception:
                pass

        self._three_was_shown = True

    # ── Scroll ──
    def try_scroll(self):
        """Scroll based on hand Y movement while in V-sign pose."""
        if not PYAUTOGUI_AVAILABLE:
            return

        now = time.perf_counter()
        if now - self._last_scroll_time < self._scroll_cooldown:
            return

        mid_y = self.get_middle_tip_y()
        if mid_y is None:
            return

        if self._scroll_base_y is None:
            self._scroll_base_y = mid_y
            return

        # Calculate delta Y (positive = hand moved down = scroll down)
        dy = mid_y - self._scroll_base_y

        # Threshold for scroll trigger
        if abs(dy) > 0.02:
            scroll_amount = int(-dy * 15 * self.sensitivity)  # Negative: hand down = scroll down
            if scroll_amount != 0:
                try:
                    pyautogui.scroll(scroll_amount, _pause=False)
                    self._last_scroll_time = now
                    direction = "Up" if scroll_amount > 0 else "Down"
                    self._current_mode = f"Scroll {direction}"
                except Exception:
                    pass

            # Update base for continuous scrolling
            self._scroll_base_y = mid_y

    # ── Volume actions (fire once) ──
    def try_action(self, gesture_name, key_action):
        if not PYAUTOGUI_AVAILABLE:
            return

        now = time.perf_counter()
        if now < self._action_cooldowns.get(gesture_name, 0):
            return

        try:
            if isinstance(key_action, list):
                pyautogui.hotkey(*key_action, _pause=False)
            else:
                pyautogui.press(key_action, _pause=False)
            self._action_cooldowns[gesture_name] = now + self._action_cooldown_duration
            self._last_action = GESTURE_INFO.get(gesture_name, {}).get("label", gesture_name)
            self._last_action_time = now
            self._count(gesture_name)
            self._log_gesture(f"{gesture_name} -> {key_action}")
        except Exception:
            pass

    # ── Helpers ──
    def _count(self, name):
        self.gesture_counts[name] = self.gesture_counts.get(name, 0) + 1

    def _log_gesture(self, details):
        if self.db_logging:
            db = self._get_db()
            if db:
                try:
                    db.add_log(self.user_id, "gesture_used", details)
                except Exception:
                    pass

    # ── Drawing ──
    def draw_skeleton(self, frame, cam_w, cam_h):
        for landmarks in self.hand_landmarks:
            pts = np.array([(int(lm.x * cam_w), int(lm.y * cam_h)) for lm in landmarks], dtype=np.int32)
            for conn in HAND_CONNECTIONS:
                cv2.line(frame, tuple(pts[conn.start]), tuple(pts[conn.end]),
                         (0, 200, 100), 2, cv2.LINE_AA)
            for pt in pts:
                cv2.circle(frame, tuple(pt), 3, (0, 255, 160), cv2.FILLED)
            for tip in [4, 8, 12, 16, 20]:
                cv2.circle(frame, tuple(pts[tip]), 7, (0, 220, 255), cv2.FILLED)

            # Draw pinch indicator between thumb and index
            thumb_pt = tuple(pts[4])
            index_pt = tuple(pts[8])
            dist = self.get_pinch_distance()
            pinch_color = (0, 255, 0) if dist < self._pinch_threshold else (100, 100, 100)
            cv2.line(frame, thumb_pt, index_pt, pinch_color, 2, cv2.LINE_AA)

            # Draw mapping region
            margin = self._map_margin
            x1, y1 = int(margin * cam_w), int(margin * cam_h)
            x2, y2 = int((1 - margin) * cam_w), int((1 - margin) * cam_h)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (50, 50, 80), 1)

    def draw_hud(self, frame, gesture, fps):
        h, w = frame.shape[:2]
        now = time.perf_counter()

        # Top-left panel background
        cv2.rectangle(frame, (8, 8), (380, 170), (15, 15, 30), cv2.FILLED)
        cv2.rectangle(frame, (8, 8), (380, 170), (40, 40, 60), 1)

        cv2.putText(frame, "SENTINEL Gesture Control", (18, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 212, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f"FPS: {int(fps)}  |  Sensitivity: {self.sensitivity}", (18, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 160, 160), 1, cv2.LINE_AA)

        # Current gesture & mode
        g_info = GESTURE_INFO.get(gesture, {})
        g_color = g_info.get("color", (150, 150, 150))
        g_label = g_info.get("label", gesture)

        cv2.putText(frame, f"Gesture: {g_label}", (18, 85),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, g_color, 2, cv2.LINE_AA)
        cv2.putText(frame, f"Mode: {self._current_mode}", (18, 110),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)

        # Pinch distance indicator
        if self.hand_landmarks:
            dist = self.get_pinch_distance()
            bar_w = min(int(dist * 800), 200)
            bar_color = (0, 255, 0) if dist < self._pinch_threshold else (80, 80, 120)
            cv2.rectangle(frame, (18, 120), (18 + bar_w, 130), bar_color, cv2.FILLED)
            cv2.putText(frame, f"Pinch: {dist:.3f}", (18, 155),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120, 120, 120), 1, cv2.LINE_AA)

        # Last action flash
        dt_action = now - self._last_action_time
        if self._last_action and dt_action < 2.0:
            alpha = max(0, 1.0 - dt_action / 2.0)
            green = int(255 * alpha)
            cv2.putText(frame, f">> {self._last_action}", (18, 165),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, green, int(80 * alpha)), 2, cv2.LINE_AA)

        # Right-side gesture guide (ASCII symbols, no Unicode emojis)
        gx = w - 220
        cv2.rectangle(frame, (gx - 10, 8), (w - 8, 245), (15, 15, 30), cv2.FILLED)
        cv2.rectangle(frame, (gx - 10, 8), (w - 8, 245), (40, 40, 60), 1)

        cv2.putText(frame, "Gesture Guide", (gx, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 212, 255), 1, cv2.LINE_AA)
        y = 50
        for name, info in GESTURE_INFO.items():
            is_active = (name == gesture)
            color = info["color"] if is_active else (80, 80, 80)
            thickness = 2 if is_active else 1
            label = f"{info['symbol']} {name}"
            cv2.putText(frame, label, (gx, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, color, thickness, cv2.LINE_AA)
            y += 24

        # Bottom help bar
        cv2.putText(frame, "Point=Move | Pinch=Click | V=Scroll | Fist=Pause | Palm=RightClick | q=Quit",
                    (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (90, 90, 90), 1, cv2.LINE_AA)

    @staticmethod
    def camera_available():
        try:
            cap = cv2.VideoCapture(0)
            ok = cap.isOpened()
            cap.release()
            return ok
        except Exception:
            return False

    # ── Main loop ──
    def run(self):
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(0, backend)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            print("ERROR: Cannot open webcam. Gesture control requires a local camera.")
            return

        cam_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        cam_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print("=" * 55)
        print("  SENTINEL — Gesture Mouse Control")
        print(f"  Camera: {cam_w}x{cam_h} | Screen: {self.screen_w}x{self.screen_h}")
        print(f"  Sensitivity: {self.sensitivity}")
        print("=" * 55)
        print("  Point index finger = move cursor")
        print("  Pinch thumb+index  = left click")
        print("  V sign + move      = scroll")
        print("  Fist               = pause")
        print("  Open palm          = right click")
        print("  Press 'q' to quit")
        print()

        _t0 = time.perf_counter()

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            now = time.perf_counter()

            # Detect on downscaled frame
            if cam_w > self.DETECT_W or cam_h > self.DETECT_H:
                small = cv2.resize(frame, (self.DETECT_W, self.DETECT_H), interpolation=cv2.INTER_LINEAR)
            else:
                small = frame

            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts_ms = int((now - _t0) * 1000)
            self.landmarker.detect_async(mp_image, ts_ms)

            # ── Recognize gesture ──
            gesture = self.recognize_gesture()

            # ── Execute based on gesture (with transition-based firing) ──
            if gesture == "Move":
                self._current_mode = "Mouse Control"
                self.move_mouse()
                # Reset other states
                self._palm_was_open = False
                self._three_was_shown = False
                self._scroll_base_y = None

            elif gesture == "Click":
                self._current_mode = "Click Mode"
                self.move_mouse()  # Still track position while clicking
                self.try_click()
                self._palm_was_open = False
                self._three_was_shown = False
                self._scroll_base_y = None

            elif gesture == "Scroll":
                self._current_mode = "Scroll Mode"
                self.try_scroll()
                self._pinch_was_closed = False
                self._palm_was_open = False
                self._three_was_shown = False

            elif gesture == "Right Click":
                self._current_mode = "Right Click"
                self.try_right_click()
                self._pinch_was_closed = False
                self._three_was_shown = False
                self._scroll_base_y = None

            elif gesture == "Double Click":
                self._current_mode = "Double Click"
                self.try_double_click()
                self._pinch_was_closed = False
                self._palm_was_open = False
                self._scroll_base_y = None

            elif gesture == "Vol Up":
                self._current_mode = "Volume Up"
                self.try_action("Vol Up", "volumeup")
                self._pinch_was_closed = False
                self._palm_was_open = False
                self._three_was_shown = False
                self._scroll_base_y = None

            elif gesture == "Vol Down":
                self._current_mode = "Volume Down"
                self.try_action("Vol Down", "volumedown")
                self._pinch_was_closed = False
                self._palm_was_open = False
                self._three_was_shown = False
                self._scroll_base_y = None

            elif gesture == "Pause":
                self._current_mode = "Paused (Fist)"
                # Reset everything — nothing happens in fist mode
                self._pinch_was_closed = False
                self._palm_was_open = False
                self._three_was_shown = False
                self._scroll_base_y = None

            else:
                self._current_mode = "Waiting..."
                self._pinch_was_closed = False
                self._palm_was_open = False
                self._three_was_shown = False
                self._scroll_base_y = None

            # Reset states when hand disappears
            if gesture == "None":
                self._pinch_was_closed = False
                self._palm_was_open = False
                self._three_was_shown = False
                self._scroll_base_y = None
                self._current_mode = "No hand detected"

            self._prev_gesture = gesture

            # ── Draw ──
            self.draw_skeleton(frame, cam_w, cam_h)

            dt = now - self._prev_time
            if dt > 0:
                instant_fps = 1.0 / dt
                self._fps_ema = 0.1 * instant_fps + 0.9 * self._fps_ema
            self._prev_time = now

            self.draw_hud(frame, gesture, self._fps_ema)

            cv2.imshow("SENTINEL Gesture Control", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        # Summary
        print("\n  Session Summary:")
        for g, c in sorted(self.gesture_counts.items(), key=lambda x: -x[1]):
            print(f"    {g}: {c} times")
        print()

        self.landmarker.close()
        cap.release()
        cv2.destroyAllWindows()
        print("  Gesture Control stopped.")


# ── Standalone entry point ──
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
