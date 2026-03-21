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
        # Human-factor parameters (timing values in milliseconds)
        self.word_pause: int = 80
        self.word_pause_std_dev: int = 20
        self.punctuation_pause: int = 200
        self.punctuation_pause_std_dev: int = 50
        self.transposition_probability: float = 0.05
        self.longer_pause_probability: float = 0.02
        self.longer_pause_duration: int = 1500
        self.longer_pause_duration_std_dev: int = 500
        self.capitalization_delay: int = 30
        self.capitalization_delay_std_dev: int = 10

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
        if "wordPause" in data:
            self.word_pause = int(data["wordPause"])
        if "wordPauseStdDev" in data:
            self.word_pause_std_dev = int(data["wordPauseStdDev"])
        if "punctuationPause" in data:
            self.punctuation_pause = int(data["punctuationPause"])
        if "punctuationPauseStdDev" in data:
            self.punctuation_pause_std_dev = int(data["punctuationPauseStdDev"])
        if "transpositionProbability" in data:
            self.transposition_probability = float(data["transpositionProbability"])
        if "longerPauseProbability" in data:
            self.longer_pause_probability = float(data["longerPauseProbability"])
        if "longerPauseDuration" in data:
            self.longer_pause_duration = int(data["longerPauseDuration"])
        if "longerPauseDurationStdDev" in data:
            self.longer_pause_duration_std_dev = int(data["longerPauseDurationStdDev"])
        if "capitalizationDelay" in data:
            self.capitalization_delay = int(data["capitalizationDelay"])
        if "capitalizationDelayStdDev" in data:
            self.capitalization_delay_std_dev = int(data["capitalizationDelayStdDev"])


# ---------------------------------------------------------------------------
# PKL config loader
# ---------------------------------------------------------------------------

_PKL_PATTERNS: dict[str, str] = {
    "text":                       r'text\s*=\s*"((?:[^"\\]|\\.)*)"',
    "minWpm":                     r"minWpm\s*=\s*(\d+)",
    "maxWpm":                     r"maxWpm\s*=\s*(\d+)",
    "errorRate":                  r"errorRate\s*=\s*([\d.]+)",
    "immediateCorrectRate":       r"immediateCorrectRate\s*=\s*([\d.]+)",
    "paragraphPause":             r"paragraphPause\s*=\s*([\d.]+)",
    "hotkeyModifier":             r'hotkeyModifier\s*=\s*"([^"]*)"',
    "hotkeyKey":                  r'hotkeyKey\s*=\s*"([^"]*)"',
    "wordPause":                  r"wordPause\s*=\s*(\d+)",
    "wordPauseStdDev":            r"wordPauseStdDev\s*=\s*(\d+)",
    "punctuationPause":           r"punctuationPause\s*=\s*(\d+)",
    "punctuationPauseStdDev":     r"punctuationPauseStdDev\s*=\s*(\d+)",
    "transpositionProbability":   r"transpositionProbability\s*=\s*([\d.]+)",
    "longerPauseProbability":     r"longerPauseProbability\s*=\s*([\d.]+)",
    "longerPauseDuration":        r"longerPauseDuration\s*=\s*(\d+)",
    "longerPauseDurationStdDev":  r"longerPauseDurationStdDev\s*=\s*(\d+)",
    "capitalizationDelay":        r"capitalizationDelay\s*=\s*(\d+)",
    "capitalizationDelayStdDev":  r"capitalizationDelayStdDev\s*=\s*(\d+)",
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
        """Normal-distribution per-keystroke delay derived from the configured WPM range."""
        mean_wpm = (self.cfg.min_wpm + self.cfg.max_wpm) / 2.0
        std_wpm = max((self.cfg.max_wpm - self.cfg.min_wpm) / 4.0, mean_wpm * 0.05)
        wpm = max(self.cfg.min_wpm, min(self.cfg.max_wpm, random.gauss(mean_wpm, std_wpm)))
        # Average English word ≈ 5 chars; convert WPM → seconds-per-char
        return max(0.01, 60.0 / (wpm * 5.0))

    def _normal_delay_s(self, mean_ms: int, std_ms: int, min_s: float = 0.0) -> float:
        """Sample a delay (seconds) from Normal(mean_ms, std_ms), clamped to *min_s*."""
        s = random.gauss(mean_ms / 1000.0, std_ms / 1000.0)
        return max(min_s, s)

    def _word_pause(self) -> None:
        """Tiny pause at word boundaries to simulate inter-word hesitation."""
        if self.cfg.word_pause > 0:
            time.sleep(self._normal_delay_s(self.cfg.word_pause, self.cfg.word_pause_std_dev))

    def _punctuation_pause(self) -> None:
        """Extra pause after punctuation characters."""
        if self.cfg.punctuation_pause > 0:
            time.sleep(self._normal_delay_s(
                self.cfg.punctuation_pause, self.cfg.punctuation_pause_std_dev
            ))

    def _capitalization_delay(self) -> None:
        """Tiny delay before pressing Shift for a capital letter."""
        if self.cfg.capitalization_delay > 0:
            time.sleep(self._normal_delay_s(
                self.cfg.capitalization_delay, self.cfg.capitalization_delay_std_dev
            ))

    def _maybe_longer_pause(self) -> None:
        """Occasionally insert a longer distraction pause after a word."""
        if self.cfg.longer_pause_probability > 0 and random.random() < self.cfg.longer_pause_probability:
            time.sleep(self._normal_delay_s(
                self.cfg.longer_pause_duration,
                self.cfg.longer_pause_duration_std_dev,
                min_s=0.1,
            ))

    # ------------------------------------------------------------------
    # Low-level key helpers
    # ------------------------------------------------------------------

    def _press(self, ch: str) -> None:
        """Press and release a single character key."""
        if ch == "\n":
            self._kb.press(Key.enter)
            self._kb.release(Key.enter)
        else:
            if ch.isupper():
                self._capitalization_delay()
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

    def _type_word_transposition(self, word: str) -> None:
        """Type *word* with a random character-transposition error, then correct it.

        Simulates a human swapping two adjacent characters (e.g. "the" → "teh"),
        typing a few more characters before noticing, then backspacing and
        retyping from the transposition point onward.
        """
        swap_pos = random.randint(0, len(word) - 2)
        chars = list(word)
        chars[swap_pos], chars[swap_pos + 1] = chars[swap_pos + 1], chars[swap_pos]
        wrong_word = "".join(chars)

        # Type the incorrectly-ordered chars up to some point past the swap
        notice_after = random.randint(swap_pos + 2, len(wrong_word))
        for c in wrong_word[:notice_after]:
            if self._stop.is_set():
                return
            self._press(c)

        # Pause – noticing the mistake
        time.sleep(random.uniform(0.15, 0.45))

        # Backspace back to the transposition point and retype correctly
        self._backspace(notice_after - swap_pos)
        for c in word[swap_pos:]:
            if self._stop.is_set():
                return
            self._press(c)

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

            if ch == " ":
                # Type the space then add a word-boundary pause
                self._press(" ")
                self._word_pause()
                # Occasionally insert a longer distraction pause after a word
                self._maybe_longer_pause()
                i += 1
                continue

            # Start of an alphabetic word – check for transposition error
            if ch.isalpha():
                j = i + 1
                while j < len(para) and para[j].isalpha():
                    j += 1
                word = para[i:j]
                if len(word) >= 2 and random.random() < self.cfg.transposition_probability:
                    self._type_word_transposition(word)
                    i = j
                    continue
                # No transposition – fall through to char-by-char typing below

            consumed = self._type_char_with_possible_error(ch, para[i + 1:])
            i += 1 + consumed
            # Extra pause after punctuation characters
            if ch in _SLOW_CHARS:
                self._punctuation_pause()

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
    print(f"  Word pause   : {cfg.word_pause}ms (±{cfg.word_pause_std_dev}ms)")
    print(f"  Punct pause  : {cfg.punctuation_pause}ms (±{cfg.punctuation_pause_std_dev}ms)")
    print(f"  Transposition: {cfg.transposition_probability * 100:.1f}% of words")
    print(f"  Longer pause : {cfg.longer_pause_probability * 100:.1f}% chance, {cfg.longer_pause_duration}ms")
    print(f"  Cap delay    : {cfg.capitalization_delay}ms (±{cfg.capitalization_delay_std_dev}ms)")
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
