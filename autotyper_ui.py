"""
autotyper_ui.py – Tkinter GUI for AutoTyper
============================================
Provides a settings panel where users can interactively configure:
  • Text to type (multi-line text area)
  • Typing speed  – min / max WPM (sliders + spinboxes)
  • Accuracy      – error rate % (slider + spinbox)
  • Paragraph pause – seconds between paragraphs (slider + spinbox)
  • Immediate-correction ratio (slider + spinbox)
  • Human factors – word pause, punctuation pause, transposition probability,
                    longer pause probability / duration, capitalization delay
  • Start/stop hotkey modifier and key
  • Countdown seconds before typing begins
  • Presets – one-click configurations for common typing profiles

Start the application with:
    python autotyper.py          # launches this GUI by default
    python autotyper.py --no-gui # falls back to the terminal CLI
"""

import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk


# ─────────────────────────────────────────────────────────────────────────────
# Colour palette (light theme – looks good on all platforms without extra libs)
# ─────────────────────────────────────────────────────────────────────────────
_BG        = "#f5f5f5"
_ACCENT    = "#3a7ebf"
_BTN_FG    = "white"
_STATUS_BG = "#e8e8e8"
_MIN_WIDTH  = 560
_MIN_HEIGHT = 700


# ─────────────────────────────────────────────────────────────────────────────
# Premade typing-profile presets
# ─────────────────────────────────────────────────────────────────────────────
_PRESETS: dict[str, dict | None] = {
    "Custom": None,  # no override – keep whatever the user has set
    "Fast Typist": {
        "min_wpm": 110, "max_wpm": 150,
        "error_rate": 0.02, "immediate_correct_rate": 0.90,
        "paragraph_pause": 0.8,
        "word_pause": 40, "word_pause_std_dev": 10,
        "punctuation_pause": 100, "punctuation_pause_std_dev": 25,
        "transposition_probability": 0.03,
        "longer_pause_probability": 0.01,
        "longer_pause_duration": 800, "longer_pause_duration_std_dev": 200,
        "capitalization_delay": 15, "capitalization_delay_std_dev": 5,
    },
    "Realistic": {
        "min_wpm": 60, "max_wpm": 90,
        "error_rate": 0.05, "immediate_correct_rate": 0.70,
        "paragraph_pause": 1.5,
        "word_pause": 100, "word_pause_std_dev": 30,
        "punctuation_pause": 250, "punctuation_pause_std_dev": 60,
        "transposition_probability": 0.04,
        "longer_pause_probability": 0.03,
        "longer_pause_duration": 1800, "longer_pause_duration_std_dev": 600,
        "capitalization_delay": 40, "capitalization_delay_std_dev": 12,
    },
    "Careful Typist": {
        "min_wpm": 30, "max_wpm": 50,
        "error_rate": 0.01, "immediate_correct_rate": 0.95,
        "paragraph_pause": 2.0,
        "word_pause": 200, "word_pause_std_dev": 50,
        "punctuation_pause": 400, "punctuation_pause_std_dev": 100,
        "transposition_probability": 0.01,
        "longer_pause_probability": 0.05,
        "longer_pause_duration": 2000, "longer_pause_duration_std_dev": 800,
        "capitalization_delay": 60, "capitalization_delay_std_dev": 15,
    },
    "Beginner": {
        "min_wpm": 15, "max_wpm": 25,
        "error_rate": 0.08, "immediate_correct_rate": 0.60,
        "paragraph_pause": 3.0,
        "word_pause": 300, "word_pause_std_dev": 100,
        "punctuation_pause": 600, "punctuation_pause_std_dev": 150,
        "transposition_probability": 0.15,
        "longer_pause_probability": 0.08,
        "longer_pause_duration": 3000, "longer_pause_duration_std_dev": 1000,
        "capitalization_delay": 100, "capitalization_delay_std_dev": 30,
    },
}


class AutoTyperUI:
    """
    Graphical interface for AutoTyper.

    Parameters
    ----------
    cfg : AutoTyperConfig
        Pre-loaded configuration (from PKL or built-in defaults).
        The UI fields are pre-populated from *cfg* and write back to
        it when the user clicks **Start Typing**.
    """

    def __init__(self, cfg) -> None:
        from autotyper import HumanTyper   # local import avoids a circular dependency with autotyper.main()
        self._HumanTyper = HumanTyper
        self.cfg = cfg
        self.typer = None
        self._hotkey_listener = None   # permanent pynput GlobalHotKeys instance
        self._registered_combo = None  # the combo string currently registered
        self._manual_stop = False      # set to True when the user explicitly stops

        self.root = tk.Tk()
        self.root.title("AutoTyper – Human-like Typing Simulator")
        self.root.configure(bg=_BG)
        self.root.minsize(_MIN_WIDTH, _MIN_HEIGHT)
        self.root.resizable(True, True)

        self._build_ui()
        self._populate_from_config()

        # Register the permanent global hotkey listener now that cfg is ready.
        self._start_hotkey_listener()
        # Clean up the listener when the window is closed.
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ──────────────────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # ── outer padding frame ──────────────────────────────────────────
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Title ────────────────────────────────────────────────────────
        title_lbl = ttk.Label(
            outer,
            text="🤖  AutoTyper",
            font=("Helvetica", 16, "bold"),
        )
        title_lbl.pack(anchor="w", pady=(0, 10))

        # ── Text to type ─────────────────────────────────────────────────
        txt_frame = ttk.LabelFrame(outer, text=" Text to type ", padding=8)
        txt_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.text_area = scrolledtext.ScrolledText(
            txt_frame,
            height=8,
            wrap=tk.WORD,
            font=("Consolas", 10),
            undo=True,
        )
        self.text_area.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            txt_frame,
            text='Finish input, then press Start. Newlines are typed as-is (Enter once per line break).',
            foreground="gray",
            font=("Helvetica", 8),
        ).pack(anchor="w", pady=(4, 0))

        # ── Preset selector ──────────────────────────────────────────────
        preset_frame = ttk.LabelFrame(outer, text=" Preset ", padding=8)
        preset_frame.pack(fill=tk.X, pady=(0, 8))

        preset_inner = ttk.Frame(preset_frame)
        preset_inner.pack(fill=tk.X)
        ttk.Label(preset_inner, text="Load preset:").pack(side=tk.LEFT)
        self.preset_var = tk.StringVar(value="Custom")
        preset_combo = ttk.Combobox(
            preset_inner,
            textvariable=self.preset_var,
            values=list(_PRESETS.keys()),
            width=14,
            state="readonly",
        )
        preset_combo.pack(side=tk.LEFT, padx=(8, 0))
        preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)
        ttk.Label(
            preset_inner,
            text="  ← selecting a preset fills all settings below",
            foreground="gray",
            font=("Helvetica", 8),
        ).pack(side=tk.LEFT, padx=(8, 0))

        # ── Settings panel ───────────────────────────────────────────────
        settings = ttk.LabelFrame(outer, text=" Settings ", padding=8)
        settings.pack(fill=tk.X, pady=(0, 8))
        settings.columnconfigure(1, weight=1)

        self.min_wpm_var   = tk.IntVar(value=40)
        self.max_wpm_var   = tk.IntVar(value=80)
        self.error_var     = tk.DoubleVar(value=5.0)
        self.imm_corr_var  = tk.DoubleVar(value=70.0)
        self.pause_var     = tk.DoubleVar(value=1.5)

        self._add_int_row(settings, 0, "Min speed (WPM):",   self.min_wpm_var,  10, 300)
        self._add_int_row(settings, 1, "Max speed (WPM):",   self.max_wpm_var,  10, 300)
        self._add_float_row(settings, 2, "Error rate (%):",  self.error_var,    0.0, 50.0, 0.5)
        self._add_float_row(settings, 3, "Immediate fix (%):", self.imm_corr_var, 0.0, 100.0, 5.0)
        self._add_float_row(settings, 4, "Para pause (s):",  self.pause_var,    0.0, 30.0, 0.5)

        # ── Human Factors panel ──────────────────────────────────────────
        hf = ttk.LabelFrame(outer, text=" Human Factors ", padding=8)
        hf.pack(fill=tk.X, pady=(0, 8))
        hf.columnconfigure(1, weight=1)

        self.word_pause_var             = tk.IntVar(value=80)
        self.punct_pause_var            = tk.IntVar(value=200)
        self.transposition_var          = tk.DoubleVar(value=5.0)
        self.longer_pause_prob_var      = tk.DoubleVar(value=2.0)
        self.longer_pause_duration_var  = tk.IntVar(value=1500)
        self.cap_delay_var              = tk.IntVar(value=30)

        self._add_int_row(hf, 0, "Word pause (ms):",        self.word_pause_var,            0, 500)
        self._add_int_row(hf, 1, "Punct pause (ms):",       self.punct_pause_var,            0, 1000)
        self._add_float_row(hf, 2, "Transposition (%):",    self.transposition_var,          0.0, 50.0, 0.5)
        self._add_float_row(hf, 3, "Longer pause (%):",     self.longer_pause_prob_var,      0.0, 20.0, 0.5)
        self._add_int_row(hf, 4, "Longer pause dur (ms):",  self.longer_pause_duration_var,  100, 10000)
        self._add_int_row(hf, 5, "Capital delay (ms):",     self.cap_delay_var,              0, 200)

        # ── Hotkey ───────────────────────────────────────────────────────
        hotkey_frame = ttk.LabelFrame(outer, text=" Start / Stop Hotkey ", padding=8)
        hotkey_frame.pack(fill=tk.X, pady=(0, 8))

        hk_inner = ttk.Frame(hotkey_frame)
        hk_inner.pack(fill=tk.X)

        ttk.Label(hk_inner, text="Modifier:").pack(side=tk.LEFT)
        self.modifier_var = tk.StringVar(value="ctrl")
        ttk.Combobox(
            hk_inner,
            textvariable=self.modifier_var,
            values=["ctrl", "alt", "shift", "cmd"],
            width=6,
            state="readonly",
        ).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Label(hk_inner, text="Key:").pack(side=tk.LEFT)
        self.hotkey_key_var = tk.StringVar(value="`")
        ttk.Entry(hk_inner, textvariable=self.hotkey_key_var, width=5).pack(
            side=tk.LEFT, padx=(4, 24)
        )

        ttk.Label(hk_inner, text="Countdown (s):").pack(side=tk.LEFT)
        self.countdown_var = tk.IntVar(value=3)
        ttk.Spinbox(
            hk_inner,
            from_=0,
            to=10,
            textvariable=self.countdown_var,
            width=4,
        ).pack(side=tk.LEFT, padx=(4, 0))

        # ── Buttons ──────────────────────────────────────────────────────
        btn_frame = ttk.Frame(outer)
        btn_frame.pack(fill=tk.X, pady=(0, 6))

        self.start_btn = tk.Button(
            btn_frame,
            text="▶   Start Typing",
            bg=_ACCENT,
            fg=_BTN_FG,
            font=("Helvetica", 11, "bold"),
            relief=tk.FLAT,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self._on_start,
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_btn = tk.Button(
            btn_frame,
            text="■   Stop",
            bg="#c0392b",
            fg=_BTN_FG,
            font=("Helvetica", 11, "bold"),
            relief=tk.FLAT,
            padx=14,
            pady=6,
            cursor="hand2",
            state=tk.DISABLED,
            command=self._on_stop,
        )
        self.stop_btn.pack(side=tk.LEFT)

        # ── Status bar ───────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(
            outer,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor="w",
            background=_STATUS_BG,
            font=("Helvetica", 9),
            padding=(6, 3),
        )
        status_bar.pack(fill=tk.X)

    # ──────────────────────────────────────────────────────────────────────
    # Helper: add a labelled integer slider + spinbox row
    # ──────────────────────────────────────────────────────────────────────

    def _add_int_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        var: tk.IntVar,
        from_: int,
        to: int,
    ) -> None:
        ttk.Label(parent, text=label, width=22, anchor="w").grid(
            row=row, column=0, sticky="w", pady=3
        )
        ttk.Spinbox(
            parent,
            from_=from_,
            to=to,
            textvariable=var,
            width=6,
        ).grid(row=row, column=1, sticky="w")
        ttk.Scale(
            parent,
            from_=from_,
            to=to,
            variable=var,
            orient=tk.HORIZONTAL,
        ).grid(row=row, column=2, sticky="ew", padx=(8, 0))
        parent.columnconfigure(2, weight=1)

    # ──────────────────────────────────────────────────────────────────────
    # Helper: add a labelled float slider + spinbox row
    # ──────────────────────────────────────────────────────────────────────

    def _add_float_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        var: tk.DoubleVar,
        from_: float,
        to: float,
        increment: float,
    ) -> None:
        ttk.Label(parent, text=label, width=22, anchor="w").grid(
            row=row, column=0, sticky="w", pady=3
        )
        ttk.Spinbox(
            parent,
            from_=from_,
            to=to,
            increment=increment,
            textvariable=var,
            width=6,
            format="%.1f",
        ).grid(row=row, column=1, sticky="w")
        ttk.Scale(
            parent,
            from_=from_,
            to=to,
            variable=var,
            orient=tk.HORIZONTAL,
        ).grid(row=row, column=2, sticky="ew", padx=(8, 0))

    # ──────────────────────────────────────────────────────────────────────
    # Config helpers
    # ──────────────────────────────────────────────────────────────────────

    def _populate_from_config(self) -> None:
        """Fill all UI fields from the loaded AutoTyperConfig."""
        if self.cfg.text:
            self.text_area.insert("1.0", self.cfg.text)
        self.min_wpm_var.set(self.cfg.min_wpm)
        self.max_wpm_var.set(self.cfg.max_wpm)
        self.error_var.set(round(self.cfg.error_rate * 100, 1))
        self.imm_corr_var.set(round(self.cfg.immediate_correct_rate * 100, 1))
        self.pause_var.set(self.cfg.paragraph_pause)
        self.modifier_var.set(self.cfg.hotkey_modifier)
        self.hotkey_key_var.set(self.cfg.hotkey_key)
        self.word_pause_var.set(self.cfg.word_pause)
        self.punct_pause_var.set(self.cfg.punctuation_pause)
        self.transposition_var.set(round(self.cfg.transposition_probability * 100, 1))
        self.longer_pause_prob_var.set(round(self.cfg.longer_pause_probability * 100, 1))
        self.longer_pause_duration_var.set(self.cfg.longer_pause_duration)
        self.cap_delay_var.set(self.cfg.capitalization_delay)

    # ──────────────────────────────────────────────────────────────────────
    # Preset helper
    # ──────────────────────────────────────────────────────────────────────

    def _on_preset_selected(self, _event=None) -> None:
        """Apply the chosen preset to all setting widgets."""
        preset = _PRESETS.get(self.preset_var.get())
        if preset is None:
            return  # "Custom" – leave everything as-is
        self.min_wpm_var.set(preset["min_wpm"])
        self.max_wpm_var.set(preset["max_wpm"])
        self.error_var.set(round(preset["error_rate"] * 100, 1))
        self.imm_corr_var.set(round(preset["immediate_correct_rate"] * 100, 1))
        self.pause_var.set(preset["paragraph_pause"])
        self.word_pause_var.set(preset["word_pause"])
        self.punct_pause_var.set(preset["punctuation_pause"])
        self.transposition_var.set(round(preset["transposition_probability"] * 100, 1))
        self.longer_pause_prob_var.set(round(preset["longer_pause_probability"] * 100, 1))
        self.longer_pause_duration_var.set(preset["longer_pause_duration"])
        self.cap_delay_var.set(preset["capitalization_delay"])

    # ──────────────────────────────────────────────────────────────────────
    # Permanent global hotkey listener
    # ──────────────────────────────────────────────────────────────────────

    def _start_hotkey_listener(self) -> None:
        """(Re-)register the permanent global hotkey listener.

        The listener acts as a start/stop toggle no matter which window has
        focus, matching the CLI behaviour and the "Start / Stop Hotkey" label.
        It is registered once at startup and restarted only when the user
        changes the hotkey combination and clicks Start.
        """
        from pynput import keyboard as _kb
        from autotyper import _hotkey_string
        combo = _hotkey_string(self.cfg)

        # No need to restart if the same combo is already registered.
        if combo == self._registered_combo and self._hotkey_listener is not None:
            return

        # Stop any existing listener before creating a new one.
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
            self._registered_combo = None

        def _toggle() -> None:
            # Schedule the toggle on the Tk main thread (pynput fires on its own thread).
            def _do_toggle() -> None:
                # Use start-button state as the canonical "session active?" check:
                # DISABLED = counting down or typing; NORMAL = idle.
                if self.start_btn["state"] == tk.DISABLED:
                    self._on_stop()
                else:
                    self._on_start()
            self.root.after(0, _do_toggle)

        try:
            listener = _kb.GlobalHotKeys({combo: _toggle})
            listener.start()
            self._hotkey_listener = listener
            self._registered_combo = combo
        except Exception as e:
            # Hotkey registration failed (bad key name, missing permissions, etc.).
            # Print a warning; typing still works via the Start/Stop buttons.
            print(f"[AutoTyper] Warning: could not register hotkey '{combo}': {e}")
            self._hotkey_listener = None
            self._registered_combo = None

    def _on_close(self) -> None:
        """Clean up when the window is closed."""
        if self.typer is not None:
            self.typer.stop()
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
        self.root.destroy()

    def _read_settings(self) -> bool:
        """
        Copy UI values into self.cfg.

        Returns False (and shows a warning) if the settings are invalid.
        """
        min_wpm = self.min_wpm_var.get()
        max_wpm = self.max_wpm_var.get()
        if min_wpm > max_wpm:
            messagebox.showwarning(
                "Invalid Speed",
                "Min speed must not exceed Max speed.\nMax speed has been adjusted.",
            )
            max_wpm = min_wpm
            self.max_wpm_var.set(max_wpm)

        self.cfg.text = self.text_area.get("1.0", tk.END).rstrip("\n")
        self.cfg.min_wpm = min_wpm
        self.cfg.max_wpm = max_wpm
        self.cfg.error_rate = round(self.error_var.get() / 100.0, 4)
        self.cfg.immediate_correct_rate = round(self.imm_corr_var.get() / 100.0, 4)
        self.cfg.paragraph_pause = self.pause_var.get()
        self.cfg.hotkey_modifier = self.modifier_var.get()
        self.cfg.hotkey_key = self.hotkey_key_var.get().strip() or "`"
        self.cfg.word_pause = self.word_pause_var.get()
        self.cfg.punctuation_pause = self.punct_pause_var.get()
        self.cfg.transposition_probability = round(self.transposition_var.get() / 100.0, 4)
        self.cfg.longer_pause_probability = round(self.longer_pause_prob_var.get() / 100.0, 4)
        self.cfg.longer_pause_duration = self.longer_pause_duration_var.get()
        self.cfg.capitalization_delay = self.cap_delay_var.get()
        return True

    # ──────────────────────────────────────────────────────────────────────
    # Button / hotkey callbacks
    # ──────────────────────────────────────────────────────────────────────

    def _on_start(self) -> None:
        if not self._read_settings():
            return
        if not self.cfg.text.strip():
            messagebox.showwarning("No Text", "Please enter the text you want to type.")
            return

        # Restart the hotkey listener if the combo was changed in the UI.
        self._start_hotkey_listener()

        self._manual_stop = False
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self._set_status("Starting…")

        secs = self.countdown_var.get()
        threading.Thread(
            target=self._countdown_then_type,
            args=(secs,),
            daemon=True,
        ).start()

    def _on_stop(self) -> None:
        self._manual_stop = True
        if self.typer:
            self.typer.stop()
        # The hotkey listener stays active so it can trigger the next session.
        self._reset_buttons()
        self._set_status("Stopped — click Start to type again.")

    # ──────────────────────────────────────────────────────────────────────
    # Background typing thread
    # ──────────────────────────────────────────────────────────────────────

    def _countdown_then_type(self, secs: int) -> None:
        """Runs in a background thread: countdown, then start typing."""
        for i in range(secs, 0, -1):
            if self._manual_stop:
                return  # User clicked Stop during countdown
            self._set_status(f"Starting in {i}s – switch to your target window…")
            time.sleep(1)

        if self._manual_stop:
            return

        self._set_status("Typing…")
        self.typer = self._HumanTyper(self.cfg)

        self.typer.start_immediate(self.cfg.text)
        # Wait for typing to finish (naturally or via stop)
        self.typer.wait_for_completion()

        # Only update UI if typing finished naturally (not via Stop button/hotkey)
        if not self._manual_stop:
            self.root.after(0, self._on_typing_done)

    def _on_typing_done(self) -> None:
        self._reset_buttons()
        self._set_status("Done ✓  – click Start to type again.")

    # ──────────────────────────────────────────────────────────────────────
    # Utility
    # ──────────────────────────────────────────────────────────────────────

    def _set_status(self, msg: str) -> None:
        """Thread-safe status update."""
        self.root.after(0, self.status_var.set, msg)

    def _reset_buttons(self) -> None:
        self.root.after(
            0,
            lambda: (
                self.start_btn.config(state=tk.NORMAL),
                self.stop_btn.config(state=tk.DISABLED),
            ),
        )

    # ──────────────────────────────────────────────────────────────────────
    # Entry point
    # ──────────────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the Tk main loop (blocks until the window is closed)."""
        self.root.mainloop()
