# autotyper-pkl

A human-like automatic typer configured through a [Pkl](https://pkl-lang.org/) file.  
It simulates realistic human typing including variable speed, nearby-key typos,
self-correction, and natural pauses between paragraphs.

---

## Features

| Feature | Detail |
|---|---|
| **Variable speed** | Per-keystroke delay sampled randomly from a configurable WPM range, with extra pauses after punctuation |
| **Realistic typos** | Wrong keys are always neighbours of the intended key on a QWERTY layout |
| **Self-correction** | Typos are corrected either immediately or after typing a few more characters (configurable ratio) |
| **Paragraph pauses** | Configurable pause inserted between double-newline-separated paragraphs |
| **Toggle hotkey** | Start and stop typing at any time with a user-defined hotkey (default **Ctrl + \`**) |
| **Pkl configuration** | All parameters live in `autotyper.pkl`; the Python script reads them via `pkl eval` at runtime |

---

## Requirements

- Python 3.10+
- [pynput](https://pynput.readthedocs.io/) (`pip install pynput`)
- *(optional)* [Pkl CLI](https://pkl-lang.org/main/current/pkl-cli/index.html) to read `autotyper.pkl` at runtime; built-in defaults are used when the CLI is not available

Install Python dependencies:

```bash
pip install -r requirements.txt
```

---

## Quick Start

1. *(optional)* Edit `autotyper.pkl` to customise typing behaviour.
2. Run the script:

   ```bash
   python autotyper.py
   ```

3. Paste / type the text you want to auto-type when prompted, then finish with:
   - a line containing only `done`, **or**
   - two consecutive blank lines.

4. Click into the target application window.

5. Press **Ctrl + \`** (or your configured hotkey) to start typing.  
   Press it again to stop early.

6. Press **Ctrl+C** in the terminal to quit.

---

## Configuration (`autotyper.pkl`)

```pkl
module AutoTyper

/// Text to type (leave empty to be prompted at runtime)
text: String = ""

/// Typing speed range in words per minute
minWpm: Int = 40
maxWpm: Int = 80

/// Probability of a typo per keystroke (0.0 – 1.0)
errorRate: Float = 0.05

/// Fraction of typos corrected immediately (vs. a few characters later)
immediateCorrectRate: Float = 0.70

/// Pause between paragraphs in seconds
paragraphPause: Float = 1.5

/// Hotkey to start / stop  (default: ctrl + `)
hotkeyModifier: String = "ctrl"   // "ctrl" | "alt" | "shift" | "cmd"
hotkeyKey:      String = "`"
```

All fields have sensible defaults; you only need to change what you care about.

---

## Notes

- On **Linux (Wayland)**, `pynput` may require running the script as root or
  with appropriate `uinput` permissions for global hotkey detection.
- On **macOS**, grant the Terminal (or your IDE) *Accessibility* permissions in
  *System Settings → Privacy & Security → Accessibility*.
- On **Windows**, no special permissions are needed.
