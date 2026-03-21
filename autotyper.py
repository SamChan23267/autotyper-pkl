#!/usr/bin/env python3
"""
AutoTyper – Human-like typing simulator
========================================
Reads its default configuration from ``autotyper.pkl`` (when the ``pkl``
CLI is installed) and falls back to sensible built-in defaults otherwise.

Usage
-----
    python autotyper.py            # launches the GUI (default)
    python autotyper.py --no-gui   # terminal / headless CLI mode

GUI mode
--------
A settings window opens where you can configure speed, accuracy and
pausing time, enter your text, then click **Start Typing**.  The app
counts down so you can switch to the target window first.

CLI mode
--------
1. Edit ``autotyper.pkl`` to pre-set your preferred parameters.
2. Run with ``--no-gui``; you will be prompted for the text to type.
3. Press the configured hotkey (default: **Ctrl + `**) to start/stop.
"""

import os
import re
import sys
import time
import random
import threading
import subprocess

from pynput import keyboard
from pynput.keyboard import Key, Controller

# ---------------------------------------------------------------------------
# QWERTY neighbour map – used to generate realistic typos
# ---------------------------------------------------------------------------

_ROWS = [
    r"`1234567890-=",
    r"qwertyuiop[]\\",
    r"asdfghjkl;'",
    r"zxcvbnm,./",
]


def _build_neighbour_map() -> dict[str, list[str]]:
    neighbours: dict[str, list[str]] = {}
    for r, row in enumerate(_ROWS):
        for c, ch in enumerate(row):
            adj: list[str] = []
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < len(_ROWS) and 0 <= nc < len(_ROWS[nr]):
                        adj.append(_ROWS[nr][nc])
            neighbours[ch] = adj
    return neighbours


_NEIGHBOUR_MAP = _build_neighbour_map()


def nearby_key(ch: str) -> str:
    """Return a random neighbouring key for *ch* (same case), or *ch* itself."""
    lower = ch.lower()
    candidates = _NEIGHBOUR_MAP.get(lower)
    if not candidates:
        return ch
    wrong = random.choice(candidates)
    return wrong.upper() if ch.isupper() else wrong


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class AutoTyperConfig:
    """Holds all runtime parameters for the autotyper."""

    def __init__(self) -> None:
        self.text: str = ""
        self.min_wpm: int = 40
        self.max_wpm: int = 80
        self.error_rate: float = 0.05
        self.immediate_correct_rate: float = 0.70
        self.paragraph_pause: float = 1.5
        self.hotkey_modifier: str = "ctrl"
        self.hotkey_key: str = "`"

    def update(self, data: dict) -> None:
        """Overlay *data* dict (e.g. parsed from PKL output) onto defaults."""
        if "text" in data:
            self.text = data["text"]
        if "minWpm" in data:
            self.min_wpm = int(data["minWpm"])
        if "maxWpm" in data:
            self.max_wpm = int(data["maxWpm"])
        if "errorRate" in data:
            self.error_rate = float(data["errorRate"])
        if "immediateCorrectRate" in data:
            self.immediate_correct_rate = float(data["immediateCorrectRate"])
        if "paragraphPause" in data:
            self.paragraph_pause = float(data["paragraphPause"])
        if "hotkeyModifier" in data:
            self.hotkey_modifier = data["hotkeyModifier"]
        if "hotkeyKey" in data:
            self.hotkey_key = data["hotkeyKey"]


# ---------------------------------------------------------------------------
# PKL config loader
# ---------------------------------------------------------------------------

_PKL_PATTERNS: dict[str, str] = {
    "text":                 r'text\s*=\s*"((?:[^"\\]|\\.)*)"',
    "minWpm":               r"minWpm\s*=\s*(\d+)",
    "maxWpm":               r"maxWpm\s*=\s*(\d+)",
    "errorRate":            r"errorRate\s*=\s*([\d.]+)",
    "immediateCorrectRate": r"immediateCorrectRate\s*=\s*([\d.]+)",
    "paragraphPause":       r"paragraphPause\s*=\s*([\d.]+)",
    "hotkeyModifier":       r'hotkeyModifier\s*=\s*"([^"]*)"',
    "hotkeyKey":            r'hotkeyKey\s*=\s*"([^"]*)"',
}


def _parse_pkl_output(text: str) -> dict:
    result: dict = {}
    for key, pattern in _PKL_PATTERNS.items():
        m = re.search(pattern, text)
        if m:
            raw = m.group(1)
            # Unescape simple escape sequences in string values
            if key in ("text", "hotkeyModifier", "hotkeyKey"):
                raw = raw.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
            result[key] = raw
    return result


def load_config() -> AutoTyperConfig:
    """
    Load configuration from ``autotyper.pkl`` via the ``pkl`` CLI.
    Falls back to built-in defaults if the CLI is unavailable or the
    file does not exist.
    """
    cfg = AutoTyperConfig()
    pkl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "autotyper.pkl")

    if not os.path.exists(pkl_path):
        return cfg

    try:
        result = subprocess.run(
            ["pkl", "eval", "-f", "pcf", pkl_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout:
            cfg.update(_parse_pkl_output(result.stdout))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # pkl CLI not installed – silently use defaults
        pass

    return cfg


# ---------------------------------------------------------------------------
# Human-like typer
# ---------------------------------------------------------------------------

# Extra pause after these characters (simulates thinking/spacing)
_SLOW_CHARS = frozenset(".!?,;:")


class HumanTyper:
    """Simulates realistic human keyboard input."""

    def __init__(self, cfg: AutoTyperConfig) -> None:
        self.cfg = cfg
        self._kb = Controller()
        self.running = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Timing helpers
    # ------------------------------------------------------------------

    def _char_delay(self, ch: str = "") -> float:
        """Random per-keystroke delay derived from the configured WPM range."""
        wpm = random.uniform(self.cfg.min_wpm, self.cfg.max_wpm)
        # Average English word ≈ 5 chars; convert WPM → seconds-per-char
        base = 60.0 / (wpm * 5.0)
        jitter = base * random.uniform(-0.30, 0.30)
        delay = max(0.02, base + jitter)
        if ch in _SLOW_CHARS:
            delay += random.uniform(0.05, 0.20)
        return delay

    # ------------------------------------------------------------------
    # Low-level key helpers
    # ------------------------------------------------------------------

    def _press(self, ch: str) -> None:
        """Press and release a single character key."""
        self._kb.press(ch)
        self._kb.release(ch)
        time.sleep(self._char_delay(ch))

    def _backspace(self, count: int = 1) -> None:
        """Press Backspace *count* times at a slightly faster pace."""
        for _ in range(count):
            if self._stop.is_set():
                return
            self._kb.press(Key.backspace)
            self._kb.release(Key.backspace)
            time.sleep(self._char_delay() * 0.75)

    # ------------------------------------------------------------------
    # Core typing logic
    # ------------------------------------------------------------------

    def _type_char_with_possible_error(self, ch: str, ahead: str) -> int:
        """
        Type *ch* with a chance of making a nearby-key typo.

        Returns the number of *ahead* characters already consumed
        (non-zero only when a delayed correction look-ahead was used).
        """
        if not ch.isalpha() or random.random() >= self.cfg.error_rate:
            self._press(ch)
            return 0

        # --- Make a typo ---
        wrong = nearby_key(ch)
        self._press(wrong)

        if random.random() < self.cfg.immediate_correct_rate:
            # Correct straight away
            time.sleep(random.uniform(0.05, 0.18))
            self._backspace()
            self._press(ch)
            return 0

        # Delayed correction: type a few characters further before noticing
        if not ahead:
            # Nothing left to type ahead – fall back to immediate correction
            time.sleep(random.uniform(0.05, 0.18))
            self._backspace()
            self._press(ch)
            return 0
        extra_count = random.randint(1, min(4, len(ahead)))
        extra_typed: list[str] = []
        for i in range(extra_count):
            if self._stop.is_set():
                break
            ec = ahead[i]
            if ec == "\n":
                break
            self._press(ec)
            extra_typed.append(ec)

        # Now realise the mistake and fix it
        time.sleep(random.uniform(0.15, 0.55))
        self._backspace(len(extra_typed) + 1)
        self._press(ch)
        for ec in extra_typed:
            if self._stop.is_set():
                return len(extra_typed)
            self._press(ec)

        return len(extra_typed)

    def _type_paragraph(self, para: str) -> None:
        """Type a single paragraph's text."""
        i = 0
        while i < len(para):
            if self._stop.is_set():
                return
            ch = para[i]
            if ch == "\n":
                self._press("\n")
                time.sleep(random.uniform(0.08, 0.25))
                i += 1
                continue
            consumed = self._type_char_with_possible_error(ch, para[i + 1:])
            i += 1 + consumed

    def _run(self, text: str) -> None:
        """Main typing loop – runs in a background thread."""
        paragraphs = text.split("\n\n")
        for idx, para in enumerate(paragraphs):
            if self._stop.is_set():
                break
            self._type_paragraph(para)
            if idx < len(paragraphs) - 1 and not self._stop.is_set():
                # End of paragraph: type the blank line separator
                self._press("\n")
                self._press("\n")
                # Human pause before starting the next paragraph
                pause = self.cfg.paragraph_pause + random.uniform(-0.3, 0.6)
                time.sleep(max(0.3, pause))
        self.running = False
        print("\n[AutoTyper] Finished typing.")

    # ------------------------------------------------------------------
    # Public control
    # ------------------------------------------------------------------

    @property
    def stopped(self) -> bool:
        """True if a stop has been *requested* via stop() (whether or not typing
        had already started).  False while typing is running normally or before
        any stop request has been made."""
        return self._stop.is_set()

    def wait_for_completion(self) -> None:
        """Block until the typing thread finishes (naturally or after stop())."""
        if self._thread is not None:
            self._thread.join()

    def _countdown_and_run(self, content: str, countdown: int) -> None:
        """Wait *countdown* seconds (honouring stop requests), then type *content*.

        Runs in a background thread so the hotkey callback returns immediately
        and further hotkey presses are not blocked during the countdown.
        """
        for _ in range(countdown):
            if self._stop.is_set():
                self.running = False
                return
            time.sleep(1)
        if not self._stop.is_set():
            self._run(content)
        else:
            self.running = False

    def start(self, text: str | None = None) -> None:
        if self.running:
            print("[AutoTyper] Already typing – press the hotkey again to stop.")
            return
        content = text or self.cfg.text
        if not content.strip():
            print("[AutoTyper] No text configured. Nothing to type.")
            return
        self.running = True
        self._stop.clear()
        print("[AutoTyper] Starting in 3 seconds – switch to target window…")
        # Run the countdown in a background thread so the hotkey callback returns
        # immediately and the listener remains responsive during the countdown.
        self._thread = threading.Thread(
            target=self._countdown_and_run, args=(content, 3), daemon=True
        )
        self._thread.start()

    def start_immediate(self, text: str | None = None) -> None:
        """Start typing immediately without any countdown delay.

        Intended for callers (e.g. the GUI) that manage their own countdown
        before invoking this method.
        """
        if self.running:
            return
        content = text or self.cfg.text
        if not content.strip():
            return
        self.running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(content,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self.running:
            self._stop.set()
            self.running = False
            print("[AutoTyper] Stopped.")
        else:
            print("[AutoTyper] Not currently typing.")


# ---------------------------------------------------------------------------
# Interactive CLI application
# ---------------------------------------------------------------------------

_MODIFIER_MAP = {
    "ctrl":    "<ctrl>",
    "control": "<ctrl>",
    "alt":     "<alt>",
    "shift":   "<shift>",
    "cmd":     "<cmd>",
    "command": "<cmd>",
    "meta":    "<cmd>",
    "super":   "<cmd>",
}


def _hotkey_string(cfg: AutoTyperConfig) -> str:
    mod = _MODIFIER_MAP.get(cfg.hotkey_modifier.lower(), f"<{cfg.hotkey_modifier}>")
    return f"{mod}+{cfg.hotkey_key}"


def _collect_text() -> str:
    """Interactive multi-line text input. Ends on a line containing only 'done'
    or on two consecutive empty lines."""
    print("Enter the text to auto-type.")
    print("Finish with a line containing only 'done', or press Enter twice on a blank line.")
    print("-" * 60)
    lines: list[str] = []
    blank_streak = 0
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().lower() == "done":
            break
        if line == "":
            blank_streak += 1
            if blank_streak >= 2:
                # Drop the trailing blank lines
                while lines and lines[-1] == "":
                    lines.pop()
                break
            lines.append(line)
        else:
            blank_streak = 0
            lines.append(line)
    return "\n".join(lines)


def run(cfg: AutoTyperConfig) -> None:
    typer = HumanTyper(cfg)

    print("=" * 60)
    print("  AutoTyper – Human-like Typing Simulator")
    print("=" * 60)

    # Collect text if not pre-configured
    if not cfg.text.strip():
        print()
        cfg.text = _collect_text()
        print()

    print(f"  Text length  : {len(cfg.text)} characters")
    print(f"  Speed range  : {cfg.min_wpm}–{cfg.max_wpm} WPM")
    print(f"  Error rate   : {cfg.error_rate * 100:.1f}%")
    print(f"  Para pause   : {cfg.paragraph_pause}s")
    hotkey = f"{cfg.hotkey_modifier}+{cfg.hotkey_key}"
    print(f"  Hotkey       : {hotkey}  (start / stop)")
    print()
    print(f"Press  {hotkey}  to start typing, then again to stop.")
    print("Press  Ctrl+C  in this terminal to quit.")
    print("=" * 60)

    combo = _hotkey_string(cfg)

    def _toggle() -> None:
        if typer.running:
            typer.stop()
        else:
            typer.start()

    try:
        with keyboard.GlobalHotKeys({combo: _toggle}) as listener:
            listener.join()
    except KeyboardInterrupt:
        print("\n[AutoTyper] Exiting.")
        typer.stop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    cfg = load_config()

    # --no-gui flag (or no display available) → fall back to terminal CLI
    force_cli = "--no-gui" in sys.argv

    if not force_cli:
        try:
            import tkinter as _tk
            # Probe for a real display before importing the full UI module
            _probe = _tk.Tk()
            _probe.withdraw()
            _probe.destroy()
            del _tk, _probe

            from autotyper_ui import AutoTyperUI
            AutoTyperUI(cfg).run()
            return
        except Exception:
            # No display / tkinter unavailable – silently fall back to CLI
            pass

    run(cfg)


if __name__ == "__main__":
    main()
