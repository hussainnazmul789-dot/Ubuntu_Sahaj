"""app_dialogs.py — Settings, activation, and license dialogs."""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QCheckBox, QApplication, QLayout,
)
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QFont

import sahaj_license


class SettingsDialog(QDialog):
    """App settings: performance and behavior preferences."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(560, 0)

        if parent is not None:
            self.setStyleSheet(parent.styleSheet())

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("<b>Settings</b>")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        intro = QLabel(
            "Adjust how Sahaj uses your computer's resources. "
            "Changes take effect the next time you open Sahaj."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(intro)

        layout.addSpacing(6)

        s = QSettings("NazmulDev", "SahajApp")

        self.asr_checkbox = QCheckBox(
            "Load Voice AI engine at startup (uses ~500 MB of RAM)"
        )
        self.asr_checkbox.setChecked(
            s.value("settings/preload_asr", True, type=bool)
        )
        layout.addWidget(self.asr_checkbox)

        asr_hint = QLabel(
            "ON  → voice typing is instant (1–2 sec)\n"
            "OFF → lower RAM, but first voice typing takes ~8–10 seconds"
        )
        asr_hint.setWordWrap(True)
        asr_hint.setStyleSheet("color: gray; font-size: 9pt; margin-left: 22px;")
        layout.addWidget(asr_hint)

        layout.addSpacing(10)

        self.spell_checkbox = QCheckBox(
            "Enable Assamese spell check (uses ~50–100 MB of RAM)"
        )
        self.spell_checkbox.setChecked(
            s.value("settings/spell_check", True, type=bool)
        )
        layout.addWidget(self.spell_checkbox)

        spell_hint = QLabel(
            "When ON, misspelled Assamese words get a red underline and "
            "right-click suggestions.\n"
            "Turn OFF if you don't write in Assamese, to save memory."
        )
        spell_hint.setWordWrap(True)
        spell_hint.setStyleSheet("color: gray; font-size: 9pt; margin-left: 22px;")
        layout.addWidget(spell_hint)

        layout.addStretch()

        btn_row = QHBoxLayout()

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self.reset_defaults)
        btn_row.addWidget(reset_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self.save_and_close)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)
        self.layout().setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

    def reset_defaults(self):
        self.asr_checkbox.setChecked(True)
        self.spell_checkbox.setChecked(True)

    def save_and_close(self):
        s = QSettings("NazmulDev", "SahajApp")
        s.setValue("settings/preload_asr", self.asr_checkbox.isChecked())
        s.setValue("settings/spell_check", self.spell_checkbox.isChecked())
        s.sync()
        self.accept()


class ActivationDialog(QDialog):
    """Modal dialog shown when the app is not yet licensed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Activate সহজ-Sahaj")
        self.setMinimumSize(460, 0)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel(
            "Enter the license key that was emailed to you after purchase:"
        ))

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        layout.addWidget(self.key_input)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        self.activate_btn = QPushButton("Activate Sahaj AI")
        self.activate_btn.clicked.connect(self.do_activate)
        btn_row.addWidget(self.activate_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        layout.addLayout(btn_row)

        machine_label = QLabel(
            "Machine ID (for support):\n"
            f"{sahaj_license._get_machine_id()}"
        )
        machine_label.setStyleSheet("font-size: 9px; color: gray;")
        machine_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(machine_label)

        self.activated = False
        self.layout().setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

    def do_activate(self):
        key = self.key_input.text().strip().upper()
        if not key:
            self.status_label.setText("Please enter a license key.")
            return

        self.activate_btn.setEnabled(False)
        self.status_label.setText("Checking with server... (this may take up to 8 seconds)")
        QApplication.processEvents()

        ok, msg = sahaj_license.activate(key)

        self.activate_btn.setEnabled(True)

        if ok:
            self.activated = True
            self.accept()
        else:
            self.status_label.setText(msg)


def ensure_licensed():
    """Check if licensed. If not, show the activation dialog.
    Returns True if the app should continue, False to exit."""
    if sahaj_license.is_licensed():
        return True
    dialog = ActivationDialog()
    dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    dialog.raise_()
    dialog.activateWindow()
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return True
    return False