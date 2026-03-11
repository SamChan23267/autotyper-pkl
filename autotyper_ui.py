"""
autotyper_ui.py – Tkinter GUI for AutoTyper
============================================
Provides a settings panel where users can interactively configure:
  • Text to type (multi-line text area)
  • Typing speed  – min / max WPM (sliders + spinboxes)
  • Accuracy      – error rate % (slider + spinbox)
  • Paragraph pause – seconds between paragraphs (slider + spinbox)
  • Immediate-correction ratio (slider + spinbox)
  • Start/stop hotkey modifier and key
  • Countdown seconds before typing begins

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
_BG       = "#f5f5f5"
_ACCENT   = "#3a7ebf"
_BTN_FG   = "white"
_STATUS_BG= "#e8e8e8"


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
        from autotyper import HumanTyper   # imported lazily to avoid circular
        self._HumanTyper = HumanTyper
        self.cfg = cfg
        self.typer = None

        self.root = tk.Tk()
        self.root.title("AutoTyper – Human-like Typing Simulator")
        self.root.configure(bg=_BG)
        self.root.minsize(520, 600)
        self.root.resizable(True, True)

        self._build_ui()
        self._populate_from_config()

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
            text='Finish input, then press Start. Use blank lines to separate paragraphs.',
            foreground="gray",
            font=("Helvetica", 8),
        ).pack(anchor="w", pady=(4, 0))

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
        if self.typer:
            self.typer.stop()
        self._reset_buttons()
        self._set_status("Stopped — click Start to type again.")

    # ──────────────────────────────────────────────────────────────────────
    # Background typing thread
    # ──────────────────────────────────────────────────────────────────────

    def _countdown_then_type(self, secs: int) -> None:
        """Runs in a background thread: countdown, then start typing."""
        for i in range(secs, 0, -1):
            self._set_status(f"Starting in {i}s – switch to your target window…")
            time.sleep(1)

        self._set_status("Typing…")
        self.typer = self._HumanTyper(self.cfg)
        self.typer.start_immediate(self.cfg.text)
        # Wait for typing to finish
        if self.typer._thread is not None:
            self.typer._thread.join()

        # Callback on completion
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
