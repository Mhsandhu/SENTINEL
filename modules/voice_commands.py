"""
SENTINEL — Voice Command Module
Provides voice-based navigation and control for the SENTINEL app.
Uses speech_recognition for microphone input and pyttsx3 for text-to-speech feedback.

Supported Commands:
  Navigation: "dashboard", "vault", "logs", "settings", "gesture control"
  Actions:    "upload file", "search [query]", "lock / logout", "help"
  Vault:      "open vault", "my files"
  Control:    "start gesture", "take screenshot"
"""

import threading
import queue
import time
import os

# ── Optional imports (graceful on cloud) ──────
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False


# ═══════════════════════════════════════════════
#  COMMAND DEFINITIONS
# ═══════════════════════════════════════════════

VOICE_COMMANDS = {
    # ── Navigation ────────────────────────────
    "dashboard":        {"action": "navigate",  "target": "Dashboard",        "response": "Opening dashboard"},
    "home":             {"action": "navigate",  "target": "Dashboard",        "response": "Going home"},
    "go home":          {"action": "navigate",  "target": "Dashboard",        "response": "Going home"},

    "vault":            {"action": "navigate",  "target": "My Vault",         "response": "Opening vault"},
    "my vault":         {"action": "navigate",  "target": "My Vault",         "response": "Opening vault"},
    "open vault":       {"action": "navigate",  "target": "My Vault",         "response": "Opening vault"},
    "files":            {"action": "navigate",  "target": "My Vault",         "response": "Opening files"},
    "my files":         {"action": "navigate",  "target": "My Vault",         "response": "Opening files"},

    "logs":             {"action": "navigate",  "target": "Activity Logs",    "response": "Opening activity logs"},
    "activity":         {"action": "navigate",  "target": "Activity Logs",    "response": "Opening activity logs"},
    "activity logs":    {"action": "navigate",  "target": "Activity Logs",    "response": "Opening activity logs"},
    "history":          {"action": "navigate",  "target": "Activity Logs",    "response": "Opening history"},

    "settings":         {"action": "navigate",  "target": "Settings",         "response": "Opening settings"},
    "preferences":      {"action": "navigate",  "target": "Settings",         "response": "Opening settings"},

    "gesture":          {"action": "navigate",  "target": "Gesture Control",  "response": "Opening gesture control"},
    "gesture control":  {"action": "navigate",  "target": "Gesture Control",  "response": "Opening gesture control"},
    "gestures":         {"action": "navigate",  "target": "Gesture Control",  "response": "Opening gesture control"},

    "voice":            {"action": "navigate",  "target": "Voice Commands",   "response": "Opening voice commands"},
    "voice commands":   {"action": "navigate",  "target": "Voice Commands",   "response": "Opening voice commands"},

    # ── Actions ───────────────────────────────
    "lock":             {"action": "logout",    "target": None,               "response": "Locking system. Goodbye."},
    "logout":           {"action": "logout",    "target": None,               "response": "Logging out. Goodbye."},
    "log out":          {"action": "logout",    "target": None,               "response": "Logging out. Goodbye."},
    "sign out":         {"action": "logout",    "target": None,               "response": "Signing out. Goodbye."},

    "help":             {"action": "help",      "target": None,               "response": "Available commands: dashboard, vault, logs, settings, gesture control, voice commands, lock, and help."},
    "what can you do":  {"action": "help",      "target": None,               "response": "I can navigate pages, open your vault, show logs, and more. Say help for the full list."},

    "start gesture":    {"action": "gesture_start", "target": None,           "response": "Starting gesture control"},
    "launch gestures":  {"action": "gesture_start", "target": None,           "response": "Launching gesture control"},

    "upload":           {"action": "upload",    "target": None,               "response": "Opening upload panel"},
    "upload file":      {"action": "upload",    "target": None,               "response": "Opening file upload"},
}


# ═══════════════════════════════════════════════
#  VOICE ENGINE
# ═══════════════════════════════════════════════

class VoiceEngine:
    """
    Background voice command listener.
    Puts recognized commands into a queue that the Streamlit app polls.
    """

    def __init__(self):
        self.command_queue = queue.Queue()
        self.status_queue = queue.Queue()
        self.is_listening = False
        self._thread = None
        self._stop_event = threading.Event()

        # TTS engine (optional)
        self._tts = None
        if TTS_AVAILABLE:
            try:
                self._tts = pyttsx3.init()
                self._tts.setProperty('rate', 170)
                self._tts.setProperty('volume', 0.85)
                voices = self._tts.getProperty('voices')
                # Use a female voice if available
                for v in voices:
                    if 'female' in v.name.lower() or 'zira' in v.name.lower():
                        self._tts.setProperty('voice', v.id)
                        break
            except Exception:
                self._tts = None

    def speak(self, text):
        """Text-to-speech output."""
        if self._tts:
            try:
                self._tts.say(text)
                self._tts.runAndWait()
            except Exception:
                pass

    def _match_command(self, text):
        """
        Match spoken text against known commands.
        Returns (command_key, command_info) or (None, None).
        """
        text = text.lower().strip()

        # Direct match
        if text in VOICE_COMMANDS:
            return text, VOICE_COMMANDS[text]

        # Partial / fuzzy match — check if any command key is IN the spoken text
        best_match = None
        best_len = 0
        for key, info in VOICE_COMMANDS.items():
            if key in text and len(key) > best_len:
                best_match = key
                best_len = len(key)

        if best_match:
            return best_match, VOICE_COMMANDS[best_match]

        # Search command: "search <query>"
        if text.startswith("search "):
            query = text[7:].strip()
            if query:
                return "search", {
                    "action": "search",
                    "target": query,
                    "response": f"Searching for {query}",
                }

        return None, None

    def _listen_loop(self):
        """Background thread: continuously listen for voice commands."""
        if not SR_AVAILABLE:
            self.status_queue.put({"status": "error", "message": "speech_recognition not installed"})
            return

        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.8

        try:
            mic = sr.Microphone()
        except Exception as e:
            self.status_queue.put({"status": "error", "message": f"No microphone: {e}"})
            return

        self.status_queue.put({"status": "ready", "message": "Calibrating microphone..."})

        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=1.5)

        self.status_queue.put({"status": "listening", "message": "Listening for commands..."})

        while not self._stop_event.is_set():
            try:
                with mic as source:
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=4)

                self.status_queue.put({"status": "processing", "message": "Processing..."})

                # Use Google's free speech recognition
                try:
                    text = recognizer.recognize_google(audio)
                except sr.UnknownValueError:
                    self.status_queue.put({"status": "listening", "message": "Listening..."})
                    continue
                except sr.RequestError:
                    self.status_queue.put({"status": "error", "message": "Speech API error"})
                    time.sleep(2)
                    continue

                # Match command
                cmd_key, cmd_info = self._match_command(text)

                if cmd_info:
                    self.command_queue.put({
                        "key": cmd_key,
                        "action": cmd_info["action"],
                        "target": cmd_info["target"],
                        "response": cmd_info["response"],
                        "raw_text": text,
                        "timestamp": time.time(),
                    })
                    self.status_queue.put({
                        "status": "recognized",
                        "message": f'"{text}" → {cmd_info["response"]}',
                    })
                    # Speak response
                    self.speak(cmd_info["response"])
                else:
                    self.status_queue.put({
                        "status": "unrecognized",
                        "message": f'Heard: "{text}" (no matching command)',
                    })

                self.status_queue.put({"status": "listening", "message": "Listening..."})

            except sr.WaitTimeoutError:
                # No speech detected in timeout — keep listening
                continue
            except Exception as e:
                self.status_queue.put({"status": "error", "message": str(e)})
                time.sleep(1)

        self.status_queue.put({"status": "stopped", "message": "Voice control stopped"})

    def start(self):
        """Start background listening."""
        if self.is_listening:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        self.is_listening = True

    def stop(self):
        """Stop background listening."""
        self._stop_event.set()
        self.is_listening = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def get_command(self):
        """Non-blocking: get next command or None."""
        try:
            return self.command_queue.get_nowait()
        except queue.Empty:
            return None

    def get_status(self):
        """Non-blocking: get latest status or None."""
        latest = None
        try:
            while True:
                latest = self.status_queue.get_nowait()
        except queue.Empty:
            pass
        return latest

    def get_all_commands(self):
        """List all supported commands grouped by category."""
        groups = {
            "Navigation": [],
            "Actions": [],
        }
        seen = set()
        for key, info in VOICE_COMMANDS.items():
            if info["response"] not in seen:
                seen.add(info["response"])
                cat = "Navigation" if info["action"] == "navigate" else "Actions"
                groups[cat].append({
                    "command": key,
                    "action": info["action"],
                    "response": info["response"],
                })
        return groups


# ═══════════════════════════════════════════════
#  MODULE-LEVEL CHECKS
# ═══════════════════════════════════════════════

def is_available():
    """Check if voice commands can work on this system."""
    return SR_AVAILABLE


def get_missing_packages():
    """Return list of packages that need to be installed."""
    missing = []
    if not SR_AVAILABLE:
        missing.append("SpeechRecognition")
    if not TTS_AVAILABLE:
        missing.append("pyttsx3")
    return missing
