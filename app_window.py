"""app_window.py — Main AssameseTypingApp class."""
import os
import json
import time
import unicodedata

from PySide6.QtWidgets import (
    QMainWindow, QMessageBox, QInputDialog, QDialog, QVBoxLayout,
    QPushButton, QLabel, QTextEdit, QApplication, QLayout,
)
from PySide6.QtCore import Qt, QTimer, QSettings, QThread
from PySide6.QtGui import QFont, QIcon, QColor, QTextCursor, QTextCharFormat, QPixmap
from PySide6.QtNetwork import QNetworkInformation

from PySide6.QtWidgets import QTextEdit as _QTextEditForSelection

import app_utils
import sahaj_license
from app_styles import DARK_STYLE, LIGHT_STYLE, font_family_css
from app_utils import resource_path, get_user_data_dir
from app_ui_mixin import UIMixin
from app_voice_mixin import VoiceMixin
from app_widgets import PhoneticTextEdit, DraggableButton
from app_workers import (
    AppLoaderThread, ASRLoaderThread, NetworkProbeThread,
    SpellCheckWorker, EnglishToAssameseWorker,
)
from app_dialogs import SettingsDialog


class AssameseTypingApp(UIMixin, VoiceMixin, QMainWindow):
    def __init__(self, setup_thread=None):
        super().__init__()
        self.setup_thread = setup_thread
        self.setWindowTitle("সহজ-Sahaj v3.0")
        self.resize(1050, 750)
        self.settings = QSettings("NazmulDev", "SahajApp")
        user_data = get_user_data_dir()
        self.autosave_file = os.path.join(user_data, "autosave.txt")
        self.helpers_file = os.path.join(user_data, "helpers.json")
        self.dictionary_file = resource_path("dictionary.json")
        self.user_dict_file = os.path.join(user_data, "user_dictionary.txt")
        self.user_dictionary = self.load_user_dictionary()
        self.current_theme = "dark"
        self.is_online = True
        font_css = font_family_css(["Nirmala UI", "Segoe UI", "Arial"])
        self.setStyleSheet(DARK_STYLE.replace("{font_css}", font_css))
        self.spell_errors = []
        self.spell_tool = None
        self.xlit_engine = None
        self.spell_worker = None
        self.dictionary = {}
        self.ignored_error_ranges = set()
        self.phonetic_enabled = True
        self.translation_mode = "google"
        self.recording_active = False
        self.recording_worker = None
        self.voice_progress = None
        self.asr_transcriber = None
        self.asr_loader_thread = None
        self.net_probe = None
        self._running_workers = []

        # Pass setup_thread so Xlit loading waits for model copy
        self.loader_thread = AppLoaderThread(
            self.dictionary_file,
            resource_path("assamese_dictionary.txt"),
            setup_thread=self.setup_thread,
        )
        self.loader_thread.finished_loading.connect(self.on_backend_loaded)
        self.loader_thread.error_signal.connect(self.show_engine_error)
        self.loader_thread.start()

        self.init_ui()
        self.load_autosave()
        self.load_helper_buttons()
        self.autosave_timer = QTimer()
        self.autosave_timer.timeout.connect(self.save_text)
        self.autosave_timer.start(6000)

        if QNetworkInformation.load(QNetworkInformation.Feature.Reachability):
            net_info = QNetworkInformation.instance()
            net_info.reachabilityChanged.connect(self.on_reachability_changed)
        else:
            print("Warning: QNetworkInformation is not supported on this platform.")

        self.net_probe = NetworkProbeThread()
        self.net_probe.result.connect(self.update_network_status)
        self.net_probe.start()

        self.spell_timer = QTimer()
        self.spell_timer.setSingleShot(True)
        self.spell_timer.timeout.connect(lambda: self.check_spelling())
        self.text_area.textChanged.connect(lambda: self.spell_timer.start(5000))
        self.check_spelling()

        self.autosave_debounce = QTimer()
        self.autosave_debounce.setSingleShot(True)
        self.autosave_debounce.timeout.connect(self.save_text)
        self.text_area.textChanged.connect(lambda: self.autosave_debounce.start(2000))

        self.remaining_seconds = 24
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.countdown_timer.setInterval(1000)

    # ---------------- worker tracking ----------------
    def _track_worker(self, worker):
        self._running_workers.append(worker)
        worker.finished.connect(lambda *_, w=worker: self._untrack_worker(w))

    def _untrack_worker(self, worker):
        try:
            self._running_workers.remove(worker)
        except ValueError:
            pass

    # ---------------- engine mode ----------------
    def on_engine_mode_changed(self, index):
        if index in (0, 1):
            self.translation_mode = "google" if index == 0 else "offline"
            if app_utils.HAS_TYPING_MODES and getattr(self, "typing_manager", None):
                self.typing_manager.set_mode("none")
        elif index == 2:
            if app_utils.HAS_TYPING_MODES and getattr(self, "typing_manager", None):
                self.typing_manager.set_mode("mouse")
        elif index == 3:
            if app_utils.HAS_TYPING_MODES and getattr(self, "typing_manager", None):
                self.typing_manager.set_mode("inscript")

    def on_typing_mode_closed(self):
        target_index = 0 if self.is_online else 1
        self.engine_combo.blockSignals(True)
        self.engine_combo.setCurrentIndex(target_index)
        self.engine_combo.blockSignals(False)
        self.translation_mode = "google" if self.is_online else "offline"

    # ---------------- backend loading ----------------
    def on_backend_loaded(self, spell_tool, dictionary, xlit_engine):
        spell_enabled = QSettings("NazmulDev", "SahajApp").value(
            "settings/spell_check", True, type=bool
        )
        if not spell_enabled:
            spell_tool = None
            print("Spell check disabled by user setting.")

        self.spell_tool = spell_tool
        self.dictionary = dictionary
        self.xlit_engine = xlit_engine

        if not self.spell_tool and spell_enabled:
            QMessageBox.warning(
                self,
                "Spell Check Disabled",
                "Could not load the bundled dictionary.\nSpell checking will be disabled.",
            )
        if not self.xlit_engine:
            QMessageBox.warning(
                self,
                "Offline Engine Disabled",
                "Could not load the offline transliteration engine.\n"
                "Built-In AI mode will not work.",
            )

        self.check_spelling()

        preload = QSettings("NazmulDev", "SahajApp").value(
            "settings/preload_asr", True, type=bool
        )
        if preload and app_utils.voice_typing is not None:
            # Pass setup_thread so ASR waits for model copy too
            self.asr_loader_thread = ASRLoaderThread(setup_thread=self.setup_thread)
            self.asr_loader_thread.finished_loading.connect(self.on_asr_loaded)
            self.asr_loader_thread.start()
            try:
                self.voice_btn.setEnabled(False)
                self.voice_btn.setText("🎤 Voice Typing (loading…)")
                self.voice_btn.setToolTip(
                    "Voice typing is warming up. This takes a few seconds at startup."
                )
            except Exception:
                pass
        else:
            print("ASR pre-load disabled by user setting.")
            self.asr_transcriber = None
            try:
                self.voice_btn.setEnabled(True)
                self.voice_btn.setText("🎤 Voice Typing")
                self.voice_btn.setToolTip(
                    "Voice typing will load the AI on first use (~8–10 seconds)."
                )
            except Exception:
                pass

    def on_asr_loaded(self, transcriber):
        self.asr_transcriber = transcriber
        if transcriber is not None:
            print("ASR model ready. Voice typing will be fast.")
            try:
                self.voice_btn.setEnabled(True)
                self.voice_btn.setText("🎤 Voice Typing")
                self.voice_btn.setToolTip("Click to start voice typing in Assamese")
            except Exception:
                pass
        else:
            print("ASR model not available. Voice typing will load on demand.")
            try:
                self.voice_btn.setEnabled(True)
                self.voice_btn.setText("🎤 Voice Typing")
                self.voice_btn.setToolTip(
                    "ASR model failed to pre-load; it will load on first use."
                )
            except Exception:
                pass
        try:
            if QNetworkInformation.instance() is not None:
                self.on_reachability_changed(
                    QNetworkInformation.instance().reachability()
                )
        except Exception:
            pass

    def show_engine_error(self, message):
        QTimer.singleShot(8000, lambda: QMessageBox.critical(
            self, "AI Engine Error", message))

    # ---------------- settings / theme ----------------
    def open_settings_dialog(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def toggle_theme(self, checked):
        font_css = font_family_css(["Nirmala UI", "Segoe UI", "Arial"])
        if checked:
            self.setStyleSheet(DARK_STYLE.replace("{font_css}", font_css))
            self.theme_toggle_btn.setText("🌙")
            self.current_theme = "dark"
        else:
            self.setStyleSheet(LIGHT_STYLE.replace("{font_css}", font_css))
            self.theme_toggle_btn.setText("☀️")
            self.current_theme = "light"

        if getattr(self, "typing_manager", None):
            self.typing_manager.set_theme(self.current_theme)

    def update_license_label(self):
        email = sahaj_license.get_licensed_email()
        if email:
            self.license_label.setText(f"✅ Licensed to: {email}")
            self.license_label.setStyleSheet("color: #198754;")
        else:
            self.license_label.setText("⚠️ Unregistered")
            self.license_label.setStyleSheet("color: #DC3545;")

    def closeEvent(self, event):
        try:
            self.save_text()
        except Exception:
            pass
        try:
            if getattr(self, "loader_thread", None) and self.loader_thread.isRunning():
                self.loader_thread.wait(1500)
        except Exception:
            pass
        try:
            if getattr(self, "typing_manager", None):
                self.typing_manager.shutdown()
        except Exception:
            pass
        try:
            if getattr(self, "asr_loader_thread", None) and self.asr_loader_thread.isRunning():
                self.asr_loader_thread.wait(2000)
        except Exception:
            pass
        try:
            for w in list(getattr(self, "_running_workers", [])):
                try:
                    if w.isRunning():
                        w.wait(2000)
                except Exception:
                    pass
        except Exception:
            pass
        super().closeEvent(event)

    # ---------------- editing helpers ----------------
    def redo_edit(self):
        self.text_area.redo()
        self.text_area.setFocus()

    def undo_edit(self):
        self.text_area.undo()
        self.text_area.setFocus()

    def toggle_phonetic(self, checked):
        self.phonetic_enabled = checked
        if checked:
            self.phonetic_btn.setText("Phonetic ON")
        else:
            self.phonetic_btn.setText("Phonetic OFF")
        self.text_area.setFocus()

    def clear_editor(self):
        self.text_area.clear_all()

    def increase_font(self):
        font = self.text_area.font()
        current_size = font.pointSize()
        if current_size < 46:
            font.setPointSize(current_size + 1)
            self.text_area.setFont(font)
            self.settings.setValue("editor_font_size", current_size + 1)
            self.text_area.update_suggestion_font()

    def decrease_font(self):
        font = self.text_area.font()
        current_size = font.pointSize()
        if current_size > 8:
            font.setPointSize(current_size - 1)
            self.text_area.setFont(font)
            self.settings.setValue("editor_font_size", current_size - 1)
            self.text_area.update_suggestion_font()

    # ---------------- network ----------------
    def on_reachability_changed(self, reachability):
        is_online = (reachability == QNetworkInformation.Reachability.Online)
        self.update_network_status(is_online)

    def update_network_status(self, is_online):
        self.is_online = is_online
        if is_online:
            self.network_status_label.setText("🟢 Online")
            self.network_status_label.setStyleSheet("color: #198754;")
        else:
            self.network_status_label.setText("🔴 Offline")
            self.network_status_label.setStyleSheet("color: #DC3545;")

    # ---------------- spell check ----------------
    def check_spelling(self):
        if not self.spell_tool:
            return
        if self.spell_worker and self.spell_worker.isRunning():
            return

        full_text = self.text_area.toPlainText()
        MAX_CHECK_LEN = 2000
        if len(full_text) > MAX_CHECK_LEN:
            cursor = self.text_area.textCursor()
            pos = cursor.position()
            start = max(0, pos - MAX_CHECK_LEN // 2)
            end = min(len(full_text), pos + MAX_CHECK_LEN // 2)
            text_to_check = full_text[start:end]
        else:
            start = 0
            text_to_check = full_text

        self.spell_worker = SpellCheckWorker(text_to_check, self.spell_tool)
        self.spell_worker.results_ready.connect(
            lambda errors: self.update_spell_errors(errors, start)
        )
        self.spell_worker.start()

    def update_spell_errors(self, errors, offset=0):
        adjusted_errors = []
        for start, end, suggestions in errors:
            real_start = start + offset
            real_end = end + offset
            if (real_start, real_end) not in self.ignored_error_ranges:
                adjusted_errors.append((real_start, real_end, suggestions))

        final_errors = []
        text = self.text_area.toPlainText()
        for start, end, suggestions in adjusted_errors:
            word = text[start:end]
            if unicodedata.normalize('NFC', word) not in self.user_dictionary:
                final_errors.append((start, end, suggestions))

        self.spell_errors = final_errors

        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        fmt.setUnderlineColor(QColor("red"))
        extra_selections = []
        for start, end, _ in self.spell_errors:
            sel = _QTextEditForSelection.ExtraSelection()
            sel.format = fmt
            sel.cursor = QTextCursor(self.text_area.document())
            sel.cursor.setPosition(start)
            sel.cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            extra_selections.append(sel)
        self.text_area.setExtraSelections(extra_selections)

    def ignore_spelling_error(self, start, end):
        self.ignored_error_ranges.add((start, end))
        self.update_spell_errors(self.spell_errors)

    # ---------------- translation ----------------
    def translate_english(self):
        text = self.eng_input.text().strip()
        if not text:
            return
        self.translated_result.setText("Translating...")
        self.add_to_editor_btn.setEnabled(False)
        self.en_as_worker = EnglishToAssameseWorker(text)
        self.en_as_worker.translation_fetched.connect(self.on_translation_ready)
        self.en_as_worker.start()

    def on_translation_ready(self, translation):
        if translation and translation != "Error":
            self.current_translation = translation
            self.translated_result.setText(f"Result: {translation}")
            self.add_to_editor_btn.setEnabled(True)
        else:
            self.translated_result.setText("Result: Not found")
            self.add_to_editor_btn.setEnabled(False)

    def add_translation_to_editor(self):
        if hasattr(self, 'current_translation') and self.current_translation:
            self.text_area.insertPlainText(self.current_translation + " ")
            self.text_area.setFocus()
            self.eng_input.clear()
            self.translated_result.setText("Result: ")
            self.add_to_editor_btn.setEnabled(False)

    # ---------------- helpers (helper buttons) ----------------
    def load_helper_buttons(self):
        self.helpers = [
            {"name": "Bhuktobhugi", "text": "ভুক্তভোগী"},
            {"name": "Asami", "text": "আচামী"},
            {"name": "Gusoria", "text": "গোচৰীয়া"},
        ]
        if os.path.exists(self.helpers_file):
            with open(self.helpers_file, "r", encoding="utf-8") as f:
                self.helpers = json.load(f)
        self.refresh_helper_ui()

    def refresh_helper_ui(self):
        for i in reversed(range(self.helpers_layout.count())):
            widget = self.helpers_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        for index, helper in enumerate(self.helpers):
            btn = DraggableButton(helper["name"], index)
            btn.setToolTip(
                f"Right-click to delete.\nDrag to reorder.\nInserts: {helper['text']}"
            )
            btn.clicked.connect(lambda checked, text=helper["text"]: self.insert_text(text))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, idx=index: self.remove_helper(idx)
            )
            self.helpers_layout.addWidget(btn)

    def add_helper_dialog(self):
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Add Helper")
        dlg.setLabelText("Button Name (e.g., Victim):")
        dlg.setInputMode(QInputDialog.InputMode.TextInput)
        dlg.setMinimumWidth(420)
        if dlg.exec() != QInputDialog.DialogCode.Accepted:
            return
        name = dlg.textValue()
        if not name:
            return

        dlg2 = QInputDialog(self)
        dlg2.setWindowTitle("Add Helper")
        dlg2.setLabelText(f"Assamese Text to insert for '{name}':")
        dlg2.setInputMode(QInputDialog.InputMode.TextInput)
        dlg2.setMinimumWidth(420)
        if dlg2.exec() != QInputDialog.DialogCode.Accepted:
            return
        text = dlg2.textValue()
        if text:
            self.helpers.append({"name": name, "text": text})
            self.save_helper_buttons()
            self.refresh_helper_ui()

    def remove_helper(self, index):
        reply = QMessageBox.question(
            self, 'Remove Button',
            'Are you sure you want to delete this helper button?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.helpers.pop(index)
            self.save_helper_buttons()
            self.refresh_helper_ui()

    def save_helper_buttons(self):
        with open(self.helpers_file, "w", encoding="utf-8") as f:
            json.dump(self.helpers, f, ensure_ascii=False, indent=4)

    # ---------------- user dictionary ----------------
    def load_user_dictionary(self):
        words = set()
        if os.path.exists(self.user_dict_file):
            try:
                with open(self.user_dict_file, "r", encoding="utf-8") as f:
                    for line in f:
                        w = line.strip()
                        if w:
                            words.add(unicodedata.normalize('NFC', w))
            except Exception:
                pass
        return words

    def save_user_dictionary(self):
        try:
            with open(self.user_dict_file, "w", encoding="utf-8") as f:
                for w in sorted(self.user_dictionary):
                    f.write(w + "\n")
        except Exception:
            pass

    def add_to_user_dictionary(self, word):
        word = unicodedata.normalize('NFC', word.strip())
        if word and word not in self.user_dictionary:
            self.user_dictionary.add(word)
            self.save_user_dictionary()
            self.check_spelling()

    # ---------------- misc ----------------
    def insert_text(self, text):
        self.text_area.insertPlainText(text + " ")
        self.text_area.setFocus()

    def save_text(self):
        text = self.text_area.toPlainText()
        try:
            temp_file = self.autosave_file + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, self.autosave_file)
            try:
                if hasattr(os, "O_DIRECTORY"):
                    dir_fd = os.open(
                        os.path.dirname(self.autosave_file) or ".",
                        os.O_DIRECTORY,
                    )
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
            except Exception:
                pass
            backup_file = self.autosave_file + ".bak"
            with open(backup_file, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            try:
                err_log = os.path.join(get_user_data_dir(), "autosave_error.log")
                with open(err_log, "a", encoding="utf-8") as log:
                    log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {e}\n")
            except Exception:
                pass

    def load_autosave(self):
        candidates = [
            self.autosave_file,
            self.autosave_file + ".tmp",
            self.autosave_file + ".bak",
        ]
        for path in candidates:
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                if content and content.strip():
                    self.text_area.setPlainText(content)
                    if path != self.autosave_file:
                        QMessageBox.information(
                            self,
                            "Recovery",
                            f"Your previous text was recovered from "
                            f"{os.path.basename(path)}.",
                        )
                    return
            except Exception:
                continue
        self.text_area.setPlainText("")

    def copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        text = self.text_area.toPlainText()

        success = False
        for attempt in range(3):
            clipboard.clear()
            clipboard.setText(text)
            if clipboard.text() == text:
                success = True
                break
            QThread.msleep(50)

        if not success:
            cursor = self.text_area.textCursor()
            self.text_area.selectAll()
            self.text_area.copy()
            cursor.clearSelection()
            self.text_area.setTextCursor(cursor)
            if clipboard.text() != text:
                QMessageBox.warning(
                    self, "Clipboard Error",
                    "Could not copy to clipboard. Please try manually (Ctrl+C)."
                )
                return

        original_text = self.copy_btn.text()
        self.copy_btn.setText("Copied ✓")
        QTimer.singleShot(1500, lambda: self.copy_btn.setText(original_text))

    # ---------------- about / support ----------------
    def show_about_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("About সহজ-Sahaj")
        dialog.setMinimumSize(550, 0)
        dialog.setStyleSheet(self.styleSheet())

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("সহজ-Sahaj v3.0 — AI Assamese Typing Tool")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = QLabel(
            "A modern, feature‑rich Assamese typing assistant built for "
            "legal professionals, writers, and anyone who needs to type "
            "in Assamese using English phonetics."
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setFont(QFont("Arial", 10))
        layout.addWidget(desc)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #ADB5BD;")
        layout.addWidget(sep)

        features_label = QLabel("✨ <b>Features</b>")
        features_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(features_label)

        features_text = QTextEdit()
        features_text.setReadOnly(True)
        features_text.setFont(QFont("Arial", 10))
        features_text.setHtml("""
<ul>
<li>🌐 <b>Online and Offline Transliteration</b> — Powered by Google-AI and AI-Xlit Engine.</li>
<li>🔤 <b>Phonetic Typing</b> — Type English (e.g., <i>bhuktobhugi</i>) and get instant Assamese.</li>
<li>🔤 <b>Voice Typing</b> — Dictate on the go! High-precision offline voice recognition.</li>
<li>✅ <b>Mouse Typing</b> — Click your way to perfect Assamese sentences.</li>
<li>✅ <b>Inscript Typing</b> — Seamless Inscript integration.</li>
<li>📖 <b>Spell & Grammar Checking</b> — Smart diagnostics with instant fixes.</li>
<li>✅ <b>English to Assamese Translation</b> — Seamless conversion into the editor.</li>
<li>✅ <b>Assamese to English Translation</b> — Explore definitions without interrupting workflow.</li>
<li>🧩 <b>Draggable Helper Buttons</b> — One‑click insertion of frequently used phrases.</li>
<li>💾 <b>Autosave</b> — Your work is saved automatically every 4 seconds.</li>
<li>🌗 <b>Light / Dark Theme</b> — Toggle between modes with one click.</li>
</ul>
        """)
        features_text.setMaximumHeight(280)
        layout.addWidget(features_text)

        credit = QLabel(
            "👨‍💻 Developed by <b>Nazmul Hussain</b><br>"
            "Contact Me: hussainnazmul786@gmail.com"
        )
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit.setFont(QFont("Arial", 10))
        layout.addWidget(credit)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.layout().setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        dialog.exec()


    def show_support_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Support the Developer")
        dialog.setMinimumSize(400, 0)
        dialog.setStyleSheet(self.styleSheet())

        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)

        title = QLabel("❤️ Support সহজ-Sahaj")
        title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        msg = QLabel(
            "If this tool helps you in your daily work,\n"
            "please consider a small contribution.\n"
            "Your support keeps the project alive! 🙏"
        )
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        layout.addWidget(msg)

        qr_path = resource_path("donate_qr.png")
        if os.path.exists(qr_path):
            qr_label = QLabel()
            pixmap = QPixmap(qr_path)
            pixmap = pixmap.scaled(
                200, 200,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            qr_label.setPixmap(pixmap)
            qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(qr_label)
        else:
            qr_missing = QLabel(
                "(QR code image not found)\nPlace 'donate_qr.png' in the app folder."
            )
            qr_missing.setAlignment(Qt.AlignmentFlag.AlignCenter)
            qr_missing.setStyleSheet("color: gray;")
            layout.addWidget(qr_missing)

        from PySide6.QtWidgets import QHBoxLayout
        upi_layout = QHBoxLayout()
        upi_label = QLabel("UPI ID: hussainnazmul786-2@okicici")
        upi_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        upi_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        upi_layout.addStretch()
        upi_layout.addWidget(upi_label)
        upi_layout.addStretch()
        layout.addLayout(upi_layout)
        copy_upi_btn = QPushButton("📋 Copy UPI ID")
        copy_upi_btn.clicked.connect(
            lambda: QApplication.clipboard().setText("hussainnazmul786-2@okicici")
        )
        layout.addWidget(copy_upi_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.layout().setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        dialog.exec()