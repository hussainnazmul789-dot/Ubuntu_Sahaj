"""app_ui_mixin.py — UIMixin providing init_ui() and helper UI methods."""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QProgressBar, QLineEdit,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap

import app_utils
from app_styles import (
    DARK_STYLE, LIGHT_STYLE, font_family_css,
)
from app_utils import resource_path
from app_widgets import PhoneticTextEdit, DraggableButton, ModernComboBox


class UIMixin:
    """Builds the main window UI. Assumes the host class (AssameseTypingApp)
    has the following attributes already set: settings, current_theme,
    helpers, helpers_layout, spell_errors, user_dictionary, phonetic_enabled,
    translation_mode."""

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(20, 10, 20, 20)
        layout.setSpacing(15)

        # ---------------- HEADER ----------------
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.settings_btn = QPushButton("⚙️")
        self.settings_btn.setFixedSize(44, 44)
        self.settings_btn.setFont(QFont("Segoe UI Emoji", 18))
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 0px;
                text-align: center;
            }
            QPushButton:hover {
                background-color: rgba(128, 128, 128, 0.2);
                border-radius: 22px;
            }
        """)
        self.settings_btn.clicked.connect(self.open_settings_dialog)
        header_layout.addWidget(self.settings_btn)

        header_layout.addStretch(1)

        self.header_logo = QLabel()
        self.header_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = resource_path("header_logo.png")

        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            scaled_pixmap = pixmap.scaledToHeight(
                70, Qt.TransformationMode.SmoothTransformation
            )
            self.header_logo.setPixmap(scaled_pixmap)
        else:
            self.header_logo.setText("সহজ-Sahaj v3.0")
            self.header_logo.setObjectName("headerText")
            self.header_logo.setFont(QFont("Arial", 22, QFont.Weight.Bold))

        header_layout.addWidget(self.header_logo)
        header_layout.addStretch(1)

        right_container = QWidget()
        right_layout = QHBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        self.network_status_label = QLabel("🟢 Checking...")
        self.network_status_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.network_status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        right_layout.addWidget(self.network_status_label)

        self.theme_toggle_btn = QPushButton()
        self.theme_toggle_btn.setCheckable(True)
        self.theme_toggle_btn.setChecked(True)
        self.theme_toggle_btn.setFixedSize(44, 44)
        self.theme_toggle_btn.setFont(QFont("Segoe UI Emoji", 22))
        self.theme_toggle_btn.setText("🌙")
        self.theme_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 0px;
                text-align: center;
            }
            QPushButton:hover {
                background-color: rgba(128, 128, 128, 0.2);
                border-radius: 22px;
            }
        """)
        self.theme_toggle_btn.toggled.connect(self.toggle_theme)
        right_layout.addWidget(self.theme_toggle_btn)
        header_layout.addWidget(right_container)
        layout.addLayout(header_layout)

        # ---------------- TOOLBAR ----------------
        toolbar = QHBoxLayout()

        clear_btn = QPushButton("Clear Editor")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #DC3545;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #BB2D3B;
            }
            QPushButton:pressed {
                background-color: #A52834;
            }
        """)
        clear_btn.clicked.connect(self.clear_editor)

        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.setObjectName("primaryBtn")
        self.copy_btn.clicked.connect(self.copy_to_clipboard)

        self.phonetic_btn = QPushButton("Phonetic ON")
        self.phonetic_btn.setCheckable(True)
        self.phonetic_btn.setChecked(True)
        self.phonetic_btn.setToolTip("Toggle phonetic conversion when you press space")
        self.phonetic_btn.setStyleSheet("""
            QPushButton {
                background-color: #198754;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #198754;
            }
            QPushButton:!checked {
                background-color: #DC3545;
            }
            QPushButton:hover {
                opacity: 0.9;
            }
        """)
        self.phonetic_btn.toggled.connect(self.toggle_phonetic)

        self.engine_combo = ModernComboBox()
        self.engine_combo.setToolTip(
            "Choose the translation engine or a typing mode.\n"
            "• Live AI       – Online transliteration\n"
            "• Built-In AI   – Offline In-built engine\n"
            "• Mouse Typing  – Click on-screen Assamese letters\n"
            "• Inscript Typing – Type Assamese with the physical keyboard"
        )
        self.engine_combo.addItems(
            ["Live AI", "Built-In AI", "Mouse Typing", "Inscript Typing"]
        )
        if not app_utils.HAS_TYPING_MODES:
            model = self.engine_combo.model()
            for i in (2, 3):
                item = model.item(i)
                if item is not None:
                    item.setEnabled(False)
        self.engine_combo.setCurrentIndex(0)
        self.engine_combo.currentIndexChanged.connect(self.on_engine_mode_changed)

        self.voice_btn = QPushButton("🎤 Voice Typing (loading…)")
        self.voice_btn.setToolTip(
            "Voice typing is warming up. This takes a few seconds at startup."
        )
        self.voice_btn.setEnabled(False)
        self.voice_btn.setStyleSheet("""
            QPushButton {
                background-color: #6F42C1;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5A32A3;
            }
            QPushButton:pressed {
                background-color: #4A2B8A;
            }
            QPushButton:disabled {
                background-color: #4A4A4A;
                color: #A0A0A0;
            }
        """)
        self.voice_btn.clicked.connect(self.start_voice_typing)

        self.voice_progress = QProgressBar()
        self.voice_progress.setRange(0, 100)
        self.voice_progress.setValue(100)
        self.voice_progress.setTextVisible(False)
        self.voice_progress.setFixedHeight(6)
        self.voice_progress.setStyleSheet("""
            QProgressBar {
                background-color: #D3D3D3;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #008080;
                border-radius: 3px;
            }
        """)
        self.voice_progress.hide()

        self.voice_timer_label = QLabel("24s")
        self.voice_timer_label.setFixedWidth(35)
        self.voice_timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voice_timer_label.setStyleSheet(
            "color: #fb6300; font-weight: bold; font-size: 13px;"
        )
        self.voice_timer_label.hide()

        undo_btn = QPushButton("Undo")
        redo_btn = QPushButton("Redo")
        redo_btn.setToolTip("Redo last undone change (Ctrl+Y)")
        redo_btn.clicked.connect(self.redo_edit)
        undo_btn.setToolTip("Undo last change (Ctrl+Z)")
        undo_btn.clicked.connect(self.undo_edit)

        inc_font_btn = QPushButton("A+")
        inc_font_btn.setToolTip("Increase Editor Font Size")
        inc_font_btn.setStyleSheet("padding: 8px 10px;")
        inc_font_btn.clicked.connect(self.increase_font)

        dec_font_btn = QPushButton("A-")
        dec_font_btn.setToolTip("Decrease Editor Font Size")
        dec_font_btn.setStyleSheet("padding: 8px 10px;")
        dec_font_btn.clicked.connect(self.decrease_font)

        add_helper_btn = QPushButton("+ Add Helper Button")
        add_helper_btn.setObjectName("successBtn")
        add_helper_btn.clicked.connect(self.add_helper_dialog)

        toolbar.addWidget(clear_btn)
        toolbar.addWidget(self.copy_btn)
        toolbar.addWidget(self.phonetic_btn)
        toolbar.addWidget(self.engine_combo)
        toolbar.addWidget(self.voice_btn)
        toolbar.addWidget(self.voice_progress)
        toolbar.addWidget(self.voice_timer_label)
        toolbar.addWidget(undo_btn)
        toolbar.addWidget(redo_btn)
        toolbar.addWidget(inc_font_btn)
        toolbar.addWidget(dec_font_btn)
        toolbar.addStretch()
        toolbar.addWidget(add_helper_btn)
        layout.addLayout(toolbar)

        # ---------------- TRANSLATION ROW ----------------
        translation_layout = QHBoxLayout()
        translation_layout.setSpacing(10)

        self.eng_input = QLineEdit()
        self.eng_input.setPlaceholderText("Type an English word to translate...")
        self.eng_input.setFont(QFont("Arial", 11))
        self.eng_input.returnPressed.connect(self.translate_english)

        self.translate_btn = QPushButton("Translate")
        self.translate_btn.clicked.connect(self.translate_english)

        self.translated_result = QLabel("Result: ")
        trans_font = QFont()
        trans_font.setFamilies(["Nirmala UI", "Segoe UI", "Arial"])
        trans_font.setPointSize(13)
        self.translated_result.setFont(trans_font)
        self.translated_result.setMinimumWidth(150)
        self.translated_result.setObjectName("translatedResult")

        self.add_to_editor_btn = QPushButton("Add to Editor")
        self.add_to_editor_btn.setObjectName("successBtn")
        self.add_to_editor_btn.clicked.connect(self.add_translation_to_editor)
        self.add_to_editor_btn.setEnabled(False)

        translation_layout.addWidget(self.eng_input)
        translation_layout.addWidget(self.translate_btn)
        translation_layout.addWidget(self.translated_result)
        translation_layout.addWidget(self.add_to_editor_btn)
        layout.addLayout(translation_layout)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #CED4DA;")
        layout.addWidget(sep)

        helper_label = QLabel("Your helper buttons right below!")
        helper_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        helper_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        helper_label.setStyleSheet("color: #666; padding: 0px 0px 2px 0px;")
        layout.addWidget(helper_label)

        # ---------------- HELPER BUTTONS ROW ----------------
        self.helpers_scroll = QScrollArea()
        self.helpers_scroll.setFixedHeight(60)
        self.helpers_scroll.setWidgetResizable(True)
        self.helpers_container = QWidget()
        self.helpers_layout = QHBoxLayout(self.helpers_container)
        self.helpers_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.helpers_layout.setContentsMargins(0, 0, 0, 0)
        self.helpers_layout.setSpacing(10)
        self.helpers_scroll.setWidget(self.helpers_container)
        layout.addWidget(self.helpers_scroll)

        # ---------------- TEXT EDITOR ----------------
        self.text_area = PhoneticTextEdit()
        saved_font_size = self.settings.value("editor_font_size", 17, type=int)
        font = self.text_area.font()
        font.setPointSize(saved_font_size)
        self.text_area.setFont(font)
        self.text_area.update_suggestion_font()
        layout.addWidget(self.text_area)

        # ---------------- TYPING MODES ----------------
        if app_utils.HAS_TYPING_MODES:
            self.typing_manager = app_utils.typing_modes.TypingModeManager(
                self, self.text_area, theme=self.current_theme
            )
            self.typing_manager.mode_closed.connect(self.on_typing_mode_closed)
        else:
            self.typing_manager = None

        # ---------------- FOOTER ----------------
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(10)

        dev_label = QLabel(
            "<a href='https://www.facebook.com/nazmul.hussain.319' "
            "style='color: #0D6EFD; text-decoration: none;'>"
            "App designed & developed by Nazmul Hussain</a>"
        )
        dev_label.setOpenExternalLinks(True)
        dev_label.setFont(QFont("Arial", 10))

        self.license_label = QLabel()
        self.license_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.update_license_label()

        about_btn = QPushButton("ℹ️ About")
        about_btn.setFixedWidth(80)
        about_btn.setToolTip("Learn more about সহজ-Sahaj")
        about_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #ADB5BD;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 9pt;
                color: #495057;
            }
            QPushButton:hover {
                background-color: #E2E6EA;
            }
        """)
        about_btn.clicked.connect(self.show_about_dialog)

        support_btn = QPushButton("❤️ Support")
        support_btn.setFixedWidth(90)
        support_btn.setToolTip("Support the developer via UPI")
        support_btn.setStyleSheet("""
            QPushButton {
                background-color: #DC3545;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #BB2D3B;
            }
        """)
        support_btn.clicked.connect(self.show_support_dialog)
        footer_layout.addWidget(self.license_label)
        footer_layout.addStretch()
        footer_layout.addWidget(dev_label)
        footer_layout.addWidget(about_btn)
        footer_layout.addWidget(support_btn)
        layout.addLayout(footer_layout)