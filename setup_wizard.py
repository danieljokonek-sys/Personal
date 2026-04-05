#!/usr/bin/env python3
"""
Setup Wizard for Mac Communication Tracker App
A multi-page tkinter GUI that walks the user through initial configuration.

Usage:
    python setup_wizard.py [--app-dir /path/to/app] [--python /path/to/python]
"""

import argparse
import os
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import font as tkfont
from tkinter import messagebox, scrolledtext, ttk

# ---------------------------------------------------------------------------
# Constants / Colours
# ---------------------------------------------------------------------------
BG = "#f5f5f5"
ACCENT = "#1a1a2e"
BTN_COLOR = "#e94560"
BTN_FG = "#ffffff"
ENTRY_BG = "#ffffff"
LABEL_FG = "#333333"
MUTED_FG = "#666666"
HIGHLIGHT = "#e94560"

TOTAL_PAGES = 8

# ---------------------------------------------------------------------------
# Argument parsing (set up before GUI so values are available globally)
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Communication Tracker Setup Wizard")
parser.add_argument(
    "--app-dir",
    default=os.path.dirname(os.path.abspath(__file__)),
    help="Path to the app directory (default: directory of this script)",
)
parser.add_argument(
    "--python",
    default=sys.executable,
    help="Path to the Python interpreter to use (default: current interpreter)",
)
args, _unknown = parser.parse_known_args()

APP_DIR = os.path.abspath(args.app_dir)
PYTHON_BIN = args.python


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_button(parent, text, command, **kwargs):
    """Styled primary button."""
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=BTN_COLOR,
        fg=BTN_FG,
        activebackground="#c73652",
        activeforeground=BTN_FG,
        relief="flat",
        bd=0,
        padx=20,
        pady=10,
        cursor="hand2",
        font=("", 11, "bold"),
        **kwargs,
    )
    return btn


def make_secondary_button(parent, text, command, **kwargs):
    """Styled secondary / outline-style button."""
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=BG,
        fg=ACCENT,
        activebackground="#e0e0e0",
        activeforeground=ACCENT,
        relief="solid",
        bd=1,
        padx=16,
        pady=8,
        cursor="hand2",
        font=("", 10),
        **kwargs,
    )
    return btn


def make_label(parent, text, size=10, bold=False, color=LABEL_FG, **kwargs):
    weight = "bold" if bold else "normal"
    lbl = tk.Label(
        parent,
        text=text,
        bg=BG,
        fg=color,
        font=("", size, weight),
        **kwargs,
    )
    return lbl


def make_entry(parent, width=40, show=None):
    entry = tk.Entry(
        parent,
        width=width,
        bg=ENTRY_BG,
        fg=LABEL_FG,
        relief="solid",
        bd=1,
        font=("", 11),
        show=show or "",
    )
    return entry


def make_frame(parent, **kwargs):
    return tk.Frame(parent, bg=BG, **kwargs)


# ---------------------------------------------------------------------------
# Main wizard window
# ---------------------------------------------------------------------------

class SetupWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Communication Tracker — Setup Wizard")
        self.configure(bg=BG)
        self.resizable(False, False)

        # Centre on screen
        w, h = 680, 560
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        # Collected data
        self.data = {
            "api_key": tk.StringVar(),
            "num_accounts": tk.IntVar(value=1),
            "accounts": [],          # list of dicts: {name, email}
            "entities": [],          # list of dicts: {name, description}
            "digest_email": tk.StringVar(),
            "digest_time": tk.StringVar(value="08:00"),
            "digest_account": tk.StringVar(),
        }

        self.current_page = 0
        self.pages = []

        self._build_chrome()
        self._build_pages()
        self._show_page(0)

    # ------------------------------------------------------------------
    # Chrome (header + footer nav)
    # ------------------------------------------------------------------

    def _build_chrome(self):
        # ---- Header bar ----
        header = tk.Frame(self, bg=ACCENT, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)

        title_lbl = tk.Label(
            header,
            text="Communication Tracker Setup",
            bg=ACCENT,
            fg="#ffffff",
            font=("", 14, "bold"),
        )
        title_lbl.pack(side="left", padx=20, pady=12)

        # ---- Progress / step indicator ----
        prog_frame = tk.Frame(self, bg=ACCENT, height=6)
        prog_frame.pack(fill="x")
        prog_frame.pack_propagate(False)

        self._prog_canvas = tk.Canvas(prog_frame, bg="#3a3a5c", height=6, bd=0, highlightthickness=0)
        self._prog_canvas.pack(fill="x")
        self._prog_bar = self._prog_canvas.create_rectangle(0, 0, 0, 6, fill=BTN_COLOR, width=0)

        # Step labels row
        steps_frame = tk.Frame(self, bg=BG, pady=6)
        steps_frame.pack(fill="x")
        step_names = ["Welcome", "API Key", "Accounts", "Entities", "Digest", "Cloud", "Authorize", "Done"]
        self._step_labels = []
        for i, name in enumerate(step_names):
            lbl = tk.Label(
                steps_frame,
                text=f"{i+1}. {name}",
                bg=BG,
                fg=MUTED_FG,
                font=("", 8),
                anchor="center",
            )
            lbl.pack(side="left", expand=True, fill="x")
            self._step_labels.append(lbl)

        # Divider
        tk.Frame(self, bg="#dddddd", height=1).pack(fill="x")

        # ---- Page container ----
        self._page_container = tk.Frame(self, bg=BG)
        self._page_container.pack(fill="both", expand=True, padx=40, pady=20)

        # ---- Footer navigation ----
        tk.Frame(self, bg="#dddddd", height=1).pack(fill="x")
        footer = tk.Frame(self, bg=BG, pady=14)
        footer.pack(fill="x", padx=40)

        self._back_btn = make_secondary_button(footer, "← Back", self._go_back)
        self._back_btn.pack(side="left")

        self._next_btn = make_button(footer, "Next →", self._go_next)
        self._next_btn.pack(side="right")

    def _update_progress(self, page_idx):
        self.update_idletasks()
        total_w = self._prog_canvas.winfo_width()
        if total_w <= 1:
            total_w = 680
        filled = int(total_w * (page_idx + 1) / TOTAL_PAGES)
        self._prog_canvas.coords(self._prog_bar, 0, 0, filled, 6)

        for i, lbl in enumerate(self._step_labels):
            if i == page_idx:
                lbl.config(fg=HIGHLIGHT, font=("", 8, "bold"))
            elif i < page_idx:
                lbl.config(fg="#888888", font=("", 8))
            else:
                lbl.config(fg=MUTED_FG, font=("", 8))

    # ------------------------------------------------------------------
    # Page management
    # ------------------------------------------------------------------

    def _show_page(self, idx):
        # Hide all pages
        for page in self.pages:
            page.pack_forget()

        self.current_page = idx
        self.pages[idx].pack(fill="both", expand=True)
        self._update_progress(idx)

        # Back button visibility
        if idx == 0:
            self._back_btn.config(state="disabled")
        else:
            self._back_btn.config(state="normal")

        # Next button label on last page
        if idx == TOTAL_PAGES - 1:
            self._next_btn.config(text="Finish", command=self._finish)
        else:
            self._next_btn.config(text="Next →", command=self._go_next)

        # Page-specific on-show hooks
        on_show = getattr(self.pages[idx], "on_show", None)
        if callable(on_show):
            on_show()

    def _go_next(self):
        # Validate current page before advancing
        validate = getattr(self.pages[self.current_page], "validate", None)
        if callable(validate):
            if not validate():
                return
        if self.current_page < TOTAL_PAGES - 1:
            self._show_page(self.current_page + 1)

    def _go_back(self):
        if self.current_page > 0:
            self._show_page(self.current_page - 1)

    def _finish(self):
        try:
            self._write_config()
            self._setup_launchd()
            messagebox.showinfo(
                "Setup Complete",
                "Your Communication Tracker is configured!\n\nThe wizard will now close.",
            )
            self.quit()
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to write config:\n{exc}")

    # ------------------------------------------------------------------
    # Build all pages
    # ------------------------------------------------------------------

    def _build_pages(self):
        self.pages = [
            self._build_page1(),
            self._build_page2(),
            self._build_page3(),
            self._build_page4(),
            self._build_page5(),
            self._build_page6(),
            self._build_page7(),
            self._build_page8(),
        ]

    # ---- Page 1: Welcome ----

    def _build_page1(self):
        frame = make_frame(self._page_container)

        make_label(frame, "Welcome to Communication Tracker", size=18, bold=True, color=ACCENT).pack(pady=(20, 8))
        make_label(frame, "Your personal AI-powered inbox & calendar briefing system", size=11, color=MUTED_FG).pack()

        tk.Frame(frame, bg="#dddddd", height=1).pack(fill="x", pady=20)

        desc = (
            "This wizard will guide you through a one-time setup in about 5 minutes.\n\n"
            "By the end you will have:\n"
            "  •  AI-powered daily email digests delivered to your inbox\n"
            "  •  Gmail accounts connected and authorised\n"
            "  •  Business entities tracked for follow-ups & AR/AP\n"
            "  •  A background job scheduled to run every morning\n\n"
            "Make sure you have your Anthropic API key ready before continuing."
        )
        txt = tk.Label(
            frame,
            text=desc,
            bg=BG,
            fg=LABEL_FG,
            font=("", 10),
            justify="left",
            anchor="w",
        )
        txt.pack(fill="x", padx=10)

        return frame

    # ---- Page 2: API Key ----

    def _build_page2(self):
        frame = make_frame(self._page_container)

        make_label(frame, "Anthropic API Key", size=16, bold=True, color=ACCENT).pack(pady=(16, 4))
        make_label(
            frame,
            "The tracker uses Claude AI to analyse and summarise your communications.",
            size=10,
            color=MUTED_FG,
        ).pack()

        tk.Frame(frame, bg="#dddddd", height=1).pack(fill="x", pady=16)

        make_label(frame, "Get your API key at:", size=10).pack(anchor="w")

        link = tk.Label(
            frame,
            text="  console.anthropic.com",
            bg=BG,
            fg=BTN_COLOR,
            font=("", 10, "underline"),
            cursor="hand2",
        )
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda _e: webbrowser.open("https://console.anthropic.com"))

        make_label(frame, "\nPaste your API key below:", size=10).pack(anchor="w")
        entry = make_entry(frame, width=48, show="•")
        entry.pack(anchor="w", pady=(4, 0))
        entry.config(textvariable=self.data["api_key"])

        make_label(
            frame,
            "Your key is stored only in the local .env file — never transmitted.",
            size=9,
            color=MUTED_FG,
        ).pack(anchor="w", pady=(8, 0))

        def validate():
            key = self.data["api_key"].get().strip()
            if not key:
                messagebox.showwarning("Required", "Please enter your Anthropic API key.")
                return False
            if not key.startswith("sk-"):
                if not messagebox.askyesno(
                    "Unusual Key",
                    "API keys normally start with 'sk-'.\nContinue anyway?",
                ):
                    return False
            return True

        frame.validate = validate
        return frame

    # ---- Page 3: Gmail Accounts ----

    def _build_page3(self):
        frame = make_frame(self._page_container)

        make_label(frame, "Gmail Accounts", size=16, bold=True, color=ACCENT).pack(pady=(16, 4))
        make_label(frame, "Choose how many Gmail accounts to monitor.", size=10, color=MUTED_FG).pack()

        tk.Frame(frame, bg="#dddddd", height=1).pack(fill="x", pady=12)

        # Number selector
        count_row = make_frame(frame)
        count_row.pack(anchor="w", pady=(0, 12))
        make_label(count_row, "Number of accounts:", size=10).pack(side="left", padx=(0, 12))
        for n in (1, 2, 3):
            rb = tk.Radiobutton(
                count_row,
                text=str(n),
                variable=self.data["num_accounts"],
                value=n,
                bg=BG,
                fg=LABEL_FG,
                activebackground=BG,
                selectcolor="#e94560",
                font=("", 10),
                command=lambda: self._refresh_account_rows(acc_frame),
            )
            rb.pack(side="left", padx=4)

        # Account name / email rows (up to 3)
        acc_frame = make_frame(frame)
        acc_frame.pack(fill="x")

        # Pre-populate data list
        for _i in range(3):
            self.data["accounts"].append({"name": tk.StringVar(), "email": tk.StringVar()})

        self._refresh_account_rows(acc_frame)

        def validate():
            n = self.data["num_accounts"].get()
            for i in range(n):
                name = self.data["accounts"][i]["name"].get().strip()
                email = self.data["accounts"][i]["email"].get().strip()
                if not name:
                    messagebox.showwarning("Required", f"Please enter a name for account {i+1}.")
                    return False
                if not email or "@" not in email:
                    messagebox.showwarning("Required", f"Please enter a valid email for account {i+1}.")
                    return False
            return True

        frame.validate = validate
        return frame

    def _refresh_account_rows(self, acc_frame):
        for widget in acc_frame.winfo_children():
            widget.destroy()

        n = self.data["num_accounts"].get()
        headers = make_frame(acc_frame)
        headers.pack(fill="x", pady=(0, 4))
        make_label(headers, "Display Name", size=9, color=MUTED_FG).pack(side="left", padx=(0, 140))
        make_label(headers, "Gmail Address", size=9, color=MUTED_FG).pack(side="left")

        for i in range(n):
            row = make_frame(acc_frame)
            row.pack(fill="x", pady=4)
            name_e = make_entry(row, width=20)
            name_e.config(textvariable=self.data["accounts"][i]["name"])
            name_e.pack(side="left", padx=(0, 8))
            email_e = make_entry(row, width=28)
            email_e.config(textvariable=self.data["accounts"][i]["email"])
            email_e.pack(side="left")

    # ---- Page 4: Business Entities ----

    def _build_page4(self):
        frame = make_frame(self._page_container)

        make_label(frame, "Business Entities", size=16, bold=True, color=ACCENT).pack(pady=(16, 4))
        make_label(
            frame,
            "Define up to 4 entities to track (business, property, project, etc.).\nLeave blank to skip.",
            size=10,
            color=MUTED_FG,
            justify="left",
        ).pack()

        tk.Frame(frame, bg="#dddddd", height=1).pack(fill="x", pady=12)

        examples = [
            ("My Business", "Primary business — invoices, clients, vendors", "invoice, client, contract, payment"),
            ("Rental Property", "Rental income, maintenance, tenant comms", "rent, tenant, lease, maintenance, landlord"),
            ("Side Project", "Freelance or side-hustle related emails", "freelance, project, proposal, deliverable"),
            ("Personal Finance", "Banks, insurance, investments", "bank, insurance, investment, statement, account"),
        ]
        for i in range(4):
            self.data["entities"].append(
                {
                    "name": tk.StringVar(value=examples[i][0]),
                    "description": tk.StringVar(value=examples[i][1]),
                    "keywords": tk.StringVar(value=examples[i][2]),
                }
            )

        headers = make_frame(frame)
        headers.pack(fill="x", pady=(0, 2))
        make_label(headers, "Entity Name", size=9, color=MUTED_FG).pack(side="left", padx=(0, 62))
        make_label(headers, "Description", size=9, color=MUTED_FG).pack(side="left", padx=(0, 68))
        make_label(headers, "Keywords (comma separated)", size=9, color=MUTED_FG).pack(side="left")

        for i in range(4):
            row = make_frame(frame)
            row.pack(fill="x", pady=3)
            name_e = make_entry(row, width=16)
            name_e.config(textvariable=self.data["entities"][i]["name"])
            name_e.pack(side="left", padx=(0, 6))
            desc_e = make_entry(row, width=22)
            desc_e.config(textvariable=self.data["entities"][i]["description"])
            desc_e.pack(side="left", padx=(0, 6))
            kw_e = make_entry(row, width=26)
            kw_e.config(textvariable=self.data["entities"][i]["keywords"])
            kw_e.pack(side="left")

        make_label(
            frame,
            "Keywords help the app quickly sort emails before the AI reads them.\nSeparate with commas. Example: rent, tenant, lease",
            size=9, color=MUTED_FG, justify="left",
        ).pack(pady=(8, 0), anchor="w")

        return frame

    # ---- Page 5: Digest Settings ----

    def _build_page5(self):
        frame = make_frame(self._page_container)

        make_label(frame, "Digest Settings", size=16, bold=True, color=ACCENT).pack(pady=(16, 4))
        make_label(
            frame,
            "Configure where and when to receive your daily AI briefing.",
            size=10,
            color=MUTED_FG,
        ).pack()

        tk.Frame(frame, bg="#dddddd", height=1).pack(fill="x", pady=16)

        # Send-to email
        make_label(frame, "Send daily briefing to:", size=10, bold=True).pack(anchor="w")
        email_entry = make_entry(frame, width=42)
        email_entry.config(textvariable=self.data["digest_email"])
        email_entry.pack(anchor="w", pady=(4, 12))

        # Send-from account
        make_label(frame, "Send from which account:", size=10, bold=True).pack(anchor="w")
        self._digest_acct_menu = None
        acct_row = make_frame(frame)
        acct_row.pack(anchor="w", pady=(4, 12))
        self._digest_acct_frame = acct_row

        # Time
        make_label(frame, "Delivery time each morning (24h HH:MM):", size=10, bold=True).pack(anchor="w")
        time_entry = make_entry(frame, width=10)
        time_entry.config(textvariable=self.data["digest_time"])
        time_entry.pack(anchor="w", pady=(4, 0))

        make_label(
            frame,
            "e.g. 07:30  •  The digest will be emailed to you each weekday morning.",
            size=9,
            color=MUTED_FG,
        ).pack(anchor="w", pady=(4, 0))

        def on_show():
            # Rebuild the account dropdown whenever we land on this page
            for w in self._digest_acct_frame.winfo_children():
                w.destroy()
            n = self.data["num_accounts"].get()
            choices = [
                self.data["accounts"][i]["name"].get() or f"Account {i+1}" for i in range(n)
            ]
            if not self.data["digest_account"].get() and choices:
                self.data["digest_account"].set(choices[0])
            menu = tk.OptionMenu(self._digest_acct_frame, self.data["digest_account"], *choices)
            menu.config(bg=ENTRY_BG, fg=LABEL_FG, relief="solid", bd=1, font=("", 10))
            menu.pack(side="left")

        frame.on_show = on_show

        def validate():
            email = self.data["digest_email"].get().strip()
            if not email or "@" not in email:
                messagebox.showwarning("Required", "Please enter a valid email address for the digest.")
                return False
            t = self.data["digest_time"].get().strip()
            parts = t.split(":")
            if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                messagebox.showwarning("Invalid", "Please enter time in HH:MM format (e.g. 08:00).")
                return False
            return True

        frame.validate = validate
        return frame

    # ---- Page 6: Google Cloud Setup ----

    def _build_page6(self):
        frame = make_frame(self._page_container)

        make_label(frame, "Google Cloud Setup", size=16, bold=True, color=ACCENT).pack(pady=(16, 4))
        make_label(
            frame,
            "Follow these steps to create OAuth credentials for Gmail & Calendar access.",
            size=10,
            color=MUTED_FG,
        ).pack()

        tk.Frame(frame, bg="#dddddd", height=1).pack(fill="x", pady=10)

        steps_text = (
            "1.  Open the Google Cloud Console (button below)\n"
            "2.  Create a new project (or select an existing one)\n"
            "3.  Go to APIs & Services → Library\n"
            "        • Enable  Gmail API\n"
            "        • Enable  Google Calendar API\n"
            "4.  Go to APIs & Services → Credentials → Create Credentials\n"
            "        • Choose  OAuth client ID\n"
            "        • Application type:  Desktop app\n"
            "5.  Download the JSON file and rename it  credentials.json\n"
            f"6.  Place credentials.json in:\n"
            f"        {os.path.join(APP_DIR, 'credentials', 'credentials.json')}"
        )

        txt = tk.Label(
            frame,
            text=steps_text,
            bg=BG,
            fg=LABEL_FG,
            font=("", 9),
            justify="left",
            anchor="w",
        )
        txt.pack(fill="x", padx=4)

        btn_row = make_frame(frame)
        btn_row.pack(fill="x", pady=(12, 4))

        make_button(
            btn_row,
            "Open Google Cloud Console",
            lambda: webbrowser.open("https://console.cloud.google.com"),
        ).pack(side="left", padx=(0, 10))

        self._creds_status = tk.StringVar(value="")
        status_lbl = tk.Label(btn_row, textvariable=self._creds_status, bg=BG, fg="#2ecc71", font=("", 9, "bold"))
        status_lbl.pack(side="left")

        def check_creds():
            creds_path = os.path.join(APP_DIR, "credentials", "credentials.json")
            if os.path.isfile(creds_path):
                self._creds_status.set("✓  credentials.json found!")
            else:
                self._creds_status.set(f"✗  Not found at credentials/credentials.json")
                status_lbl.config(fg="#e94560")

        make_secondary_button(frame, "I've completed these steps — check file", check_creds).pack(
            anchor="w", pady=(6, 0)
        )

        return frame

    # ---- Page 7: Authorize Gmail ----

    def _build_page7(self):
        frame = make_frame(self._page_container)

        make_label(frame, "Authorize Gmail Access", size=16, bold=True, color=ACCENT).pack(pady=(16, 4))
        make_label(
            frame,
            "Click the button below to open a browser and authorize each Gmail account.\n"
            "Follow the prompts — you may need to approve each account separately.",
            size=10,
            color=MUTED_FG,
            justify="left",
        ).pack()

        tk.Frame(frame, bg="#dddddd", height=1).pack(fill="x", pady=10)

        self._auth_output = scrolledtext.ScrolledText(
            frame,
            height=10,
            bg="#1a1a2e",
            fg="#00ff88",
            font=("Courier", 9),
            relief="flat",
            state="disabled",
        )
        self._auth_output.pack(fill="both", expand=True)

        self._auth_btn = make_button(frame, "Authorize Gmail Accounts", self._run_auth)
        self._auth_btn.pack(pady=(10, 0))

        self._auth_done = False

        def validate():
            if not self._auth_done:
                if not messagebox.askyesno(
                    "Skip Authorization?",
                    "Gmail authorization has not completed.\nAre you sure you want to skip this step?",
                ):
                    return False
            return True

        frame.validate = validate
        return frame

    def _run_auth(self):
        self._auth_btn.config(state="disabled", text="Running…")
        self._append_auth_output("Starting Gmail authorization…\n")

        def worker():
            try:
                cmd = [PYTHON_BIN, os.path.join(APP_DIR, "main.py"), "setup-accounts"]
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=APP_DIR,
                )
                for line in proc.stdout:
                    self._append_auth_output(line)
                proc.wait()
                if proc.returncode == 0:
                    self._append_auth_output("\n✓  Authorization complete!\n")
                    self._auth_done = True
                else:
                    self._append_auth_output(f"\n✗  Process exited with code {proc.returncode}\n")
            except FileNotFoundError:
                self._append_auth_output(
                    f"\n✗  Could not find main.py at:\n   {os.path.join(APP_DIR, 'main.py')}\n"
                    "   You can complete this step manually later.\n"
                )
            except Exception as exc:
                self._append_auth_output(f"\n✗  Error: {exc}\n")
            finally:
                self.after(0, lambda: self._auth_btn.config(state="normal", text="Re-run Authorization"))

        threading.Thread(target=worker, daemon=True).start()

    def _append_auth_output(self, text):
        def _do():
            self._auth_output.config(state="normal")
            self._auth_output.insert("end", text)
            self._auth_output.see("end")
            self._auth_output.config(state="disabled")

        self.after(0, _do)

    # ---- Page 8: Done ----

    def _build_page8(self):
        frame = make_frame(self._page_container)

        make_label(frame, "You're all set!", size=20, bold=True, color=ACCENT).pack(pady=(20, 8))
        make_label(
            frame,
            "Communication Tracker is configured and ready to go.",
            size=11,
            color=MUTED_FG,
        ).pack()

        tk.Frame(frame, bg="#dddddd", height=1).pack(fill="x", pady=16)

        self._summary_lbl = tk.Label(
            frame,
            text="",
            bg=BG,
            fg=LABEL_FG,
            font=("", 10),
            justify="left",
            anchor="w",
        )
        self._summary_lbl.pack(fill="x", padx=8)

        next_steps = (
            "Next steps:\n"
            "  •  Your daily digest will arrive at the configured time each morning.\n"
            "  •  Run  python main.py run  at any time to generate a digest now.\n"
            "  •  Edit  config.yaml  to adjust entity keywords, follow-up days, etc.\n"
            f"  •  App directory:  {APP_DIR}"
        )
        make_label(frame, next_steps, size=9, color=MUTED_FG, justify="left", anchor="w").pack(
            fill="x", padx=8, pady=(12, 0)
        )

        def on_show():
            n = self.data["num_accounts"].get()
            acct_list = ", ".join(
                self.data["accounts"][i]["email"].get() for i in range(n) if self.data["accounts"][i]["email"].get()
            )
            entities = [
                self.data["entities"][i]["name"].get()
                for i in range(4)
                if self.data["entities"][i]["name"].get().strip()
            ]
            entity_list = ", ".join(entities) if entities else "None"
            summary = (
                f"  Accounts tracked:    {acct_list or '(none)'}\n"
                f"  Entities:            {entity_list}\n"
                f"  Digest email:        {self.data['digest_email'].get() or '(not set)'}\n"
                f"  Delivery time:       {self.data['digest_time'].get()}\n"
                f"  Configs written to:  {APP_DIR}"
            )
            self._summary_lbl.config(text=summary)

        frame.on_show = on_show
        return frame

    # ------------------------------------------------------------------
    # Config writing
    # ------------------------------------------------------------------

    def _write_config(self):
        os.makedirs(APP_DIR, exist_ok=True)
        os.makedirs(os.path.join(APP_DIR, "credentials"), exist_ok=True)

        # .env
        env_path = os.path.join(APP_DIR, ".env")
        with open(env_path, "w") as f:
            f.write(f'ANTHROPIC_API_KEY="{self.data["api_key"].get().strip()}"\n')

        # config.yaml
        n = self.data["num_accounts"].get()
        accounts = []
        for i in range(n):
            acct_name = self.data["accounts"][i]["name"].get().strip()
            acct_email = self.data["accounts"][i]["email"].get().strip()
            safe_name = acct_name.lower().replace(" ", "_") or f"account{i+1}"
            accounts.append(
                {
                    "name": acct_name,
                    "email": acct_email,
                    "token_file": f"credentials/token_{safe_name}.json",
                }
            )

        digest_email = self.data["digest_email"].get().strip()
        digest_time = self.data["digest_time"].get().strip()
        digest_account = self.data["digest_account"].get().strip() or (accounts[0]["name"] if accounts else "")

        entities = {}
        for i in range(4):
            ename = self.data["entities"][i]["name"].get().strip()
            edesc = self.data["entities"][i]["description"].get().strip()
            ekw_raw = self.data["entities"][i].get("keywords", tk.StringVar()).get().strip()
            # Parse comma-separated keywords into a list
            ekw = [k.strip() for k in ekw_raw.split(",") if k.strip()] if ekw_raw else []
            if ename:
                key = f"entity_{i+1}"
                entities[key] = {"name": ename, "description": edesc, "keywords": ekw}

        # Build YAML manually to avoid requiring pyyaml at wizard runtime
        yaml_lines = ["# Communication Tracker Configuration", "# Generated by setup_wizard.py", ""]

        yaml_lines += [
            "owner:",
            '  name: ""',
            '  phone: ""',
            "",
        ]

        yaml_lines += ["accounts:"]
        for acct in accounts:
            yaml_lines.append(f'  - name: "{acct["name"]}"')
            yaml_lines.append(f'    email: "{acct["email"]}"')
            yaml_lines.append(f'    token_file: "{acct["token_file"]}"')
            yaml_lines.append(f'    primary_entities: ["personal"]')
        yaml_lines.append("")

        yaml_lines += [
            "digest:",
            f'  send_to: "{digest_email}"',
            f'  send_from_account: "{digest_account}"',
            "  schedule:",
            f'    daily_summary: "{digest_time}"',
            '    weekly_deep_dive: "monday 09:00"',
            "",
        ]

        yaml_lines += ["entities:"]
        if entities:
            for key, ent in entities.items():
                kw_yaml = "[" + ", ".join(f'"{k}"' for k in ent["keywords"]) + "]"
                yaml_lines.append(f"  {key}:")
                yaml_lines.append(f'    name: "{ent["name"]}"')
                yaml_lines.append(f'    description: "{ent["description"]}"')
                yaml_lines.append(f"    keywords: {kw_yaml}")
                yaml_lines.append("    accounts_receivable_from: []")
                yaml_lines.append("    accounts_payable_to: []")
        else:
            yaml_lines.append(
                "  entity_1:\n    name: \"\"\n    description: \"\"\n    keywords: []\n"
                "    accounts_receivable_from: []\n    accounts_payable_to: []"
            )
        yaml_lines.append("")

        yaml_lines += [
            "google:",
            '  credentials_file: "credentials/credentials.json"',
            "  max_emails_per_fetch: 100",
            "  lookback_days: 30",
            "  calendar_days_ahead: 30",
            "",
            "sms:",
            '  forwarding_email_subject_prefix: "New text message from"',
            "  enabled: false",
            "",
            "analysis:",
            '  model: "claude-opus-4-6"',
            "  batch_size: 20",
            "",
            "features:",
            "  auto_label_emails: true",
            "  follow_up_detection: true",
            "  follow_up_days: 3",
            "  nag_after_days: 3",
            "",
        ]

        config_path = os.path.join(APP_DIR, "config.yaml")
        with open(config_path, "w") as f:
            f.write("\n".join(yaml_lines))

    # ------------------------------------------------------------------
    # launchd plist
    # ------------------------------------------------------------------

    def _setup_launchd(self):
        launch_agents_dir = os.path.expanduser("~/Library/LaunchAgents")
        os.makedirs(launch_agents_dir, exist_ok=True)

        plist_path = os.path.join(launch_agents_dir, "com.personaltracker.daily.plist")

        digest_time = self.data["digest_time"].get().strip()
        try:
            hour, minute = map(int, digest_time.split(":"))
        except ValueError:
            hour, minute = 8, 0

        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.personaltracker.daily</string>

    <key>ProgramArguments</key>
    <array>
        <string>{PYTHON_BIN}</string>
        <string>{os.path.join(APP_DIR, "main.py")}</string>
        <string>run</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{APP_DIR}</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>{os.path.join(APP_DIR, "logs", "tracker.log")}</string>

    <key>StandardErrorPath</key>
    <string>{os.path.join(APP_DIR, "logs", "tracker_error.log")}</string>

    <key>RunAtLoad</key>
    <false/>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
"""
        with open(plist_path, "w") as f:
            f.write(plist_content)

        # Ensure logs directory exists
        os.makedirs(os.path.join(APP_DIR, "logs"), exist_ok=True)

        # Load the plist (best-effort; may fail if not on macOS)
        try:
            subprocess.run(
                ["launchctl", "load", plist_path],
                check=False,
                capture_output=True,
            )
        except FileNotFoundError:
            pass  # Not on macOS — skip silently


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = SetupWizard()
    app.mainloop()
