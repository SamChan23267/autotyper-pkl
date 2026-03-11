# autotyper-pkl

A human-like automatic typer configured through a [Pkl](https://pkl-lang.org/) file,
with a **graphical settings panel** built using tkinter.

![AutoTyper UI](https://github.com/user-attachments/assets/3bac17f2-d9c3-4b3e-ac65-6db72122578b)

---

## Features

| Feature | Detail |
|---|---|
| **Settings GUI** | Tkinter window with sliders + spinboxes for every parameter — no config file editing needed |
| **Variable speed** | Per-keystroke delay sampled randomly from a configurable WPM range, with extra pauses after punctuation |
| **Realistic typos** | Wrong keys are always neighbours of the intended key on a QWERTY layout |
| **Self-correction** | Typos corrected either immediately or after typing a few more characters (configurable ratio) |
| **Paragraph pauses** | Configurable pause inserted between double-newline-separated paragraphs |
| **Toggle hotkey** | Start and stop typing at any time with a user-defined hotkey (default **Ctrl + \`**) |
| **Countdown timer** | Configurable seconds before typing begins – time to switch windows |
| **Pkl configuration** | All parameter defaults live in `autotyper.pkl` and pre-populate the GUI at launch |
| **Headless / CLI mode** | Pass `--no-gui` to use the original terminal interface |

---

## Requirements

- Python 3.10+
- [pynput](https://pynput.readthedocs.io/) — keyboard control
- tkinter — GUI (included with most Python installations; on Ubuntu install with `sudo apt install python3-tk`)
- *(optional)* [Pkl CLI](https://pkl-lang.org/main/current/pkl-cli/index.html) — reads `autotyper.pkl` defaults into the UI

Install Python dependencies:

```bash
pip install -r requirements.txt
```

---

## Quick Start

### GUI mode (default)

```bash
python autotyper.py
```

1. Type or paste your text into the **Text to type** area.
2. Adjust **Min / Max speed**, **Error rate**, **Para pause**, and other settings using the sliders or spinboxes.
3. Set your preferred **hotkey** (default **Ctrl + \`**) and **countdown**.
4. Click **▶ Start Typing**, then switch to your target application before the countdown ends.
5. Click **■ Stop** (or press the hotkey again) to stop early.

### Terminal / headless mode

```bash
python autotyper.py --no-gui
```

Paste text when prompted, then use the configured hotkey to start/stop.

---

## Configuration (`autotyper.pkl`)

Edit `autotyper.pkl` to change the **default values** pre-loaded into the GUI on startup:

```pkl
module AutoTyper

/// Text to type (leave empty to enter in the GUI at runtime)
text: String = ""

/// Typing speed range in words per minute
minWpm: Int = 40
maxWpm: Int = 80   // must be >= minWpm (enforced by constraint)

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

All fields have sensible defaults — you only need to change what you care about.
Changes are reflected in the GUI the next time you launch the app.

---

## Notes

- On **Linux (Wayland)**, `pynput` may require running the script as root or
  with appropriate `uinput` permissions for global hotkey detection.
- On **macOS**, grant the Terminal (or your IDE) *Accessibility* permissions in
  *System Settings → Privacy & Security → Accessibility*.
- On **Windows**, no special permissions are needed.
- If tkinter is not available (e.g. on a minimal server), the app automatically
  falls back to CLI mode, or you can force it with `--no-gui`.
