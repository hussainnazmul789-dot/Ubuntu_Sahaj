"""app_widgets.py — Custom Qt widgets and popups."""
import os
import re
import difflib

from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QPlainTextEdit, QComboBox, QListView, QMenu, QTextEdit,
    QToolTip,
)
from PySide6.QtCore import Qt, QTimer, QPoint, QEvent, QMimeData
from PySide6.QtGui import (
    QFont, QTextCursor, QTextCharFormat, QColor, QDrag,
    QCursor, QAction,
)

from app_styles import CUSTOM_FONT_FAMILIES
from app_workers import TranslationWorker, MeaningWorker


class MeaningPopup(QDialog):
    """Small floating card showing the English meaning of Assamese text."""

    def __init__(self, meaning_text, parent=None, theme="dark"):
        super().__init__(parent)
        self.meaning_text = meaning_text or ""
        self._theme = theme

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)

        header = QLabel("📖 English meaning")
        header_font = QFont()
        header_font.setFamilies(CUSTOM_FONT_FAMILIES)
        header_font.setPointSize(10)
        header_font.setBold(True)
        header.setFont(header_font)
        header_row.addWidget(header)
        header_row.addStretch()

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("meaningClose")
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.setToolTip("Close (Esc)")
        self.close_btn.clicked.connect(self.close)
        header_row.addWidget(self.close_btn)

        layout.addLayout(header_row)

        self.text_label = QLabel(self.meaning_text if self.meaning_text else "No translation found")
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body_font = QFont()
        body_font.setFamilies(CUSTOM_FONT_FAMILIES)
        body_font.setPointSize(11)
        self.text_label.setFont(body_font)
        layout.addWidget(self.text_label)

        self.copy_btn = QPushButton("📋 Copy meaning")
        self.copy_btn.setObjectName("meaningCopy")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._on_copy_clicked)
        layout.addWidget(self.copy_btn)

        self._apply_theme()

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        self.adjustSize()

    def _apply_theme(self):
        if self._theme == "dark":
            self.setStyleSheet("""
                MeaningPopup {
                    background-color: #2C2C2C;
                    border: 1px solid #666666;
                    border-radius: 8px;
                }
                QLabel { color: #E0E0E0; background: transparent; }
                QPushButton#meaningClose {
                    background-color: #DC3545; color: #FFFFFF; border: none;
                    border-radius: 11px; font-size: 13px; font-weight: bold; padding: 0px;
                }
                QPushButton#meaningClose:hover { background-color: #E4606D; }
                QPushButton#meaningClose:pressed { background-color: #BB2D3B; }
                QPushButton#meaningCopy {
                    background-color: #0D6EFD; color: white; border: none;
                    border-radius: 6px; padding: 6px 12px; font-weight: bold;
                }
                QPushButton#meaningCopy:hover   { background-color: #0B5ED7; }
                QPushButton#meaningCopy:pressed { background-color: #0A58CA; }
            """)
        else:
            self.setStyleSheet("""
                MeaningPopup {
                    background-color: #FFFFFF;
                    border: 1px solid #CED4DA;
                    border-radius: 8px;
                }
                QLabel { color: #333333; background: transparent; }
                QPushButton#meaningClose {
                    background-color: #DC3545; color: #FFFFFF; border: none;
                    border-radius: 11px; font-size: 13px; font-weight: bold; padding: 0px;
                }
                QPushButton#meaningClose:hover { background-color: #E4606D; }
                QPushButton#meaningClose:pressed { background-color: #BB2D3B; }
                QPushButton#meaningCopy {
                    background-color: #0D6EFD; color: white; border: none;
                    border-radius: 6px; padding: 6px 12px; font-weight: bold;
                }
                QPushButton#meaningCopy:hover   { background-color: #0B5ED7; }
                QPushButton#meaningCopy:pressed { background-color: #0A58CA; }
            """)

    def _on_copy_clicked(self):
        QApplication.clipboard().setText(self.meaning_text or "")
        self.copy_btn.setText("✅ Copied!")
        QTimer.singleShot(800, self.close)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress and self.isVisible():
            try:
                global_pos = event.globalPosition().toPoint()
                if not self.geometry().contains(global_pos):
                    self.close()
            except Exception:
                pass
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        app = QApplication.instance()
        if app is not None:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass
        super().closeEvent(event)

    def show_at(self, global_pos):
        screen = QApplication.primaryScreen().availableGeometry()
        w = self.width()
        h = self.height()
        x = global_pos.x()
        y = global_pos.y() + 14
        if x + w > screen.right():
            x = screen.right() - w - 8
        if x < screen.left():
            x = screen.left() + 8
        if y + h > screen.bottom():
            y = global_pos.y() - h - 14
        if y < screen.top():
            y = screen.top() + 8
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()


class PhoneticTextEdit(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        editor_font = QFont()
        editor_font.setFamilies(CUSTOM_FONT_FAMILIES)
        editor_font.setPointSize(17)
        self.setFont(editor_font)
        self.translator = None

        self.suggestion_list = QListWidget(self)
        self.suggestion_list.setWindowFlags(Qt.WindowType.ToolTip)
        self.suggestion_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        sugg_font = QFont()
        sugg_font.setFamilies(CUSTOM_FONT_FAMILIES)
        sugg_font.setPointSize(14)
        self.suggestion_list.setFont(sugg_font)
        self.suggestion_list.hide()
        self.suggestion_list.itemClicked.connect(self.apply_suggestion)
        self.last_word_start = 0
        self.last_word_end = 0

        self.original_punctuation = None
        self.punctuation_pos = -1

    def update_suggestion_font(self):
        editor_size = self.font().pointSize()
        sugg_size = max(8, editor_size - 1)
        sugg_font = QFont()
        sugg_font.setFamilies(CUSTOM_FONT_FAMILIES)
        sugg_font.setPointSize(sugg_size)
        self.suggestion_list.setFont(sugg_font)

    def keyPressEvent(self, event):
        if self.suggestion_list.isVisible():
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.suggestion_list.currentRow()
                if event.key() == Qt.Key.Key_Down:
                    row = (row + 1) % self.suggestion_list.count()
                else:
                    row = (row - 1) % self.suggestion_list.count()
                self.suggestion_list.setCurrentRow(row)
                return
            elif event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
                if self.suggestion_list.currentItem():
                    self.apply_suggestion(self.suggestion_list.currentItem())
                return
            elif event.key() == Qt.Key.Key_Escape:
                self.suggestion_list.hide()
                return
            else:
                text = event.text()
                if text and not text in ".,?!;:'\"()-":
                    self.suggestion_list.hide()

        if event.text() == ".":
            self.insertPlainText(".")
            return

        if event.key() == Qt.Key.Key_Space:
            # Lazy import to avoid circular dependency
            from app_window import AssameseTypingApp
            main_win = self.window()
            if isinstance(main_win, AssameseTypingApp) and not main_win.phonetic_enabled:
                super().keyPressEvent(event)
                return

            pos_before_space = self.textCursor().position()
            super().keyPressEvent(event)
            new_pos = self.textCursor().position()

            if new_pos < 2:
                return
            if new_pos >= 2 and self.toPlainText()[new_pos - 2] == ' ':
                return

            cursor = self.textCursor()
            cursor.setPosition(new_pos - 2)
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
            char_before_space = cursor.selectedText()

            if char_before_space == ".":
                cursor.setPosition(new_pos - 2)
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
                cursor.insertText("।")
                char_before_space = "।"
                self.setTextCursor(self.textCursor())
                self.original_punctuation = "."
                self.punctuation_pos = new_pos - 2

            if char_before_space and not char_before_space.isalnum() and not char_before_space.isspace():
                word_end = new_pos - 2
                self.pending_punctuation = char_before_space
            else:
                word_end = new_pos - 1
                self.pending_punctuation = None

            word_start = word_end
            while word_start > 0:
                cursor.setPosition(word_start - 1)
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
                ch = cursor.selectedText()
                if not ch.isascii() or not (ch.isalpha() or ch.isdigit()):
                    break
                word_start -= 1

            if word_start < word_end:
                word = self.toPlainText()[word_start:word_end]
                if word.isascii():
                    if self.original_punctuation == ".":
                        self.english_punctuation = "."
                    else:
                        self.english_punctuation = self.pending_punctuation

                    self.last_word_start = word_start
                    self.last_word_end = word_end
                    self.fetch_translation(word)

            return
        super().keyPressEvent(event)

    def undo(self):
        super().undo()
        self._move_past_space()

    def redo(self):
        super().redo()
        self._move_past_space()

    def _move_past_space(self):
        cursor = self.textCursor()
        pos = cursor.position()
        doc_len = len(self.toPlainText())
        if pos < doc_len and self.toPlainText()[pos] == ' ':
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, 1)
            self.setTextCursor(cursor)

        self.last_word_start = 0
        self.last_word_end = 0
        self.pending_punctuation = None
        self.original_punctuation = None
        self.punctuation_pos = -1

    def mousePressEvent(self, event):
        if self.suggestion_list.isVisible():
            self.suggestion_list.hide()
        super().mousePressEvent(event)

    def focusOutEvent(self, event):
        if self.suggestion_list.isVisible():
            cursor_pos = self.suggestion_list.mapFromGlobal(QCursor.pos())
            if not self.suggestion_list.rect().contains(cursor_pos):
                self.suggestion_list.hide()
        super().focusOutEvent(event)

    def wheelEvent(self, event):
        if self.suggestion_list.isVisible():
            local_pos = self.suggestion_list.mapFromGlobal(event.globalPosition().toPoint())
            if not self.suggestion_list.rect().contains(local_pos):
                self.suggestion_list.hide()
        super().wheelEvent(event)

    def fetch_translation(self, word):
        main_win = self.window()
        xlit_engine = getattr(main_win, 'xlit_engine', None)
        mode = getattr(main_win, 'translation_mode', 'google')
        self.translator = TranslationWorker(word, xlit_engine=xlit_engine, mode=mode)
        self.translator.finished.connect(self.handle_translation)
        self.translator.start()

    def handle_translation(self, suggestions, original_word):
        if not suggestions:
            return
        cursor = self.textCursor()
        cursor.setPosition(self.last_word_start)
        cursor.setPosition(self.last_word_end, QTextCursor.MoveMode.KeepAnchor)

        cursor.insertText(suggestions[0])
        self.last_word_end = self.last_word_start + len(suggestions[0])

        display_suggestions = suggestions[:]
        if self.pending_punctuation:
            display_suggestions = [s + self.pending_punctuation for s in suggestions]

        if len(display_suggestions) > 1:
            self.show_suggestions(display_suggestions)

    def show_suggestions(self, suggestions):
        if not self.hasFocus():
            return
        self.update_suggestion_font()
        self.suggestion_list.clear()
        self.suggestion_list.addItems(suggestions)
        self.suggestion_list.setCurrentRow(0)
        item_height = 40
        visible_items = min(len(suggestions), 5)
        popup_width = 220
        popup_height = (item_height * visible_items) + 10
        self.suggestion_list.resize(popup_width, popup_height)

        cursor_rect = self.cursorRect()
        cursor_global_top_left = self.mapToGlobal(cursor_rect.topLeft())
        cursor_global_bottom_left = self.mapToGlobal(cursor_rect.bottomLeft())

        popup_x = cursor_global_bottom_left.x()
        popup_y = cursor_global_bottom_left.y() + 20
        screen_rect = QApplication.primaryScreen().availableGeometry()
        if popup_y + popup_height > screen_rect.bottom():
            popup_y = cursor_global_top_left.y() - popup_height
            if popup_y < screen_rect.top():
                popup_y = screen_rect.top()

        if popup_x + popup_width > screen_rect.right():
            popup_x = screen_rect.right() - popup_width
        if popup_x < screen_rect.left():
            popup_x = screen_rect.left()

        self.suggestion_list.move(popup_x, popup_y)
        self.suggestion_list.show()

    def apply_suggestion(self, item):
        text = item.text()
        if self.pending_punctuation and text.endswith(self.pending_punctuation):
            text = text[:-len(self.pending_punctuation)]
        cursor = self.textCursor()
        cursor.setPosition(self.last_word_start)
        cursor.setPosition(self.last_word_end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text)
        self.last_word_end = self.last_word_start + len(text)
        self.suggestion_list.hide()
        self.setFocus()
        self.pending_punctuation = None

    def contextMenuEvent(self, event):
        from app_window import AssameseTypingApp
        main_win = self.window()
        is_main_app = isinstance(main_win, AssameseTypingApp)

        cursor = self.textCursor()
        if cursor.hasSelection():
            lookup_text = cursor.selectedText().replace("\u2029", " ").strip()
        else:
            word_cursor = self.cursorForPosition(event.pos())
            word_cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            lookup_text = word_cursor.selectedText().strip()

        has_assamese = bool(re.search(r'[\u0980-\u09FF]', lookup_text))

        misspelled_word = None
        misspelled_range = None
        misspelled_suggestions = None
        if is_main_app and not cursor.hasSelection():
            text = self.toPlainText()
            pos = self.cursorForPosition(event.pos()).position()
            start = pos
            end = pos
            while start > 0 and re.match(r'[\u0980-\u09FF\u200C\u200D]', text[start - 1]):
                start -= 1
            while end < len(text) and re.match(r'[\u0980-\u09FF\u200C\u200D]', text[end]):
                end += 1
            candidate = text[start:end].strip()
            if candidate and re.search(r'[\u0980-\u09FF]', candidate):
                for err_start, err_end, suggestions in main_win.spell_errors:
                    if start == err_start and end == err_end:
                        misspelled_word = text[start:end]
                        misspelled_range = (start, end)
                        misspelled_suggestions = suggestions
                        break

        menu = QMenu(self)
        menu_font = QFont()
        menu_font.setFamilies(CUSTOM_FONT_FAMILIES)
        if misspelled_word and misspelled_range:
            editor_size = self.font().pointSize()
            menu_font.setPointSize(max(10, editor_size - 3))
        else:
            menu_font.setPointSize(10)
        menu.setFont(menu_font)

        if has_assamese and len(lookup_text) >= 1:
            meaning_action = menu.addAction("📖 Show meaning")
            meaning_action.triggered.connect(
                lambda checked=False, t=lookup_text[:500], p=event.globalPos():
                    self._show_meaning_popup(t, p)
            )
            menu.addSeparator()

        if misspelled_word and misspelled_range:
            all_suggestions = list(misspelled_suggestions) if misspelled_suggestions else []
            user_matches = difflib.get_close_matches(
                misspelled_word, main_win.user_dictionary, n=5, cutoff=0.6,
            )
            for um in user_matches:
                if um not in all_suggestions:
                    all_suggestions.append(um)
            all_suggestions = all_suggestions[:8]

            if all_suggestions:
                for sug in all_suggestions:
                    act = menu.addAction(sug)
                    act.triggered.connect(
                        lambda checked=False, s=sug, rng=misspelled_range:
                            self._replace_word_in_range(rng, s)
                    )
            else:
                menu.addAction("(no suggestions)").setEnabled(False)

            menu.addSeparator()
            ignore_action = menu.addAction("Ignore")
            ignore_action.triggered.connect(
                lambda checked=False, s=misspelled_range[0], e=misspelled_range[1]:
                    main_win.ignore_spelling_error(s, e)
            )
            add_dict_action = menu.addAction("Add to Dictionary")
            add_dict_action.triggered.connect(
                lambda checked=False, w=misspelled_word:
                    main_win.add_to_user_dictionary(w)
            )
            menu.addSeparator()

        if not (misspelled_word and misspelled_range):
            std_menu = self.createStandardContextMenu()
            for act in std_menu.actions():
                if act.isSeparator():
                    continue
                menu.addAction(act)

        menu.exec(event.globalPos())

    def replace_word(self, cursor, replacement):
        cursor.insertText(replacement)
        self.setTextCursor(cursor)

    def _replace_word_in_range(self, rng, replacement):
        cursor = QTextCursor(self.document())
        cursor.setPosition(rng[0])
        cursor.setPosition(rng[1], QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(replacement)
        self.setTextCursor(cursor)

    def _show_meaning_popup(self, text, global_pos):
        if getattr(self, "_meaning_popup", None) is not None:
            try:
                self._meaning_popup.close()
                self._meaning_popup.deleteLater()
            except Exception:
                pass
            self._meaning_popup = None

        loading = MeaningPopup("Loading…", parent=self.window(), theme=self._current_theme_name())
        loading.show_at(global_pos)
        self._meaning_popup = loading

        worker = MeaningWorker(text)

        def _on_done(_word, meaning, popup_ref=loading, pos=global_pos):
            if getattr(self, "_meaning_popup", None) is not popup_ref:
                return
            try:
                popup_ref.close()
                popup_ref.deleteLater()
            except Exception:
                pass
            result_text = meaning if meaning else "No translation found"
            new_popup = MeaningPopup(result_text, parent=self.window(), theme=self._current_theme_name())
            new_popup.show_at(pos)
            self._meaning_popup = new_popup

        worker.meaning_fetched.connect(_on_done)

        if not hasattr(self, "_meaning_workers"):
            self._meaning_workers = []
        self._meaning_workers.append(worker)

        def _cleanup():
            try:
                self._meaning_workers.remove(worker)
            except ValueError:
                pass
        worker.finished.connect(_cleanup)
        worker.start()

    def _current_theme_name(self):
        w = self.window()
        while w is not None:
            if hasattr(w, "current_theme"):
                return w.current_theme
            w = w.parent()
        return "dark"

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        QToolTip.hideText()

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)

    def clear_all(self):
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText("")


class DraggableButton(QPushButton):
    def __init__(self, text, index, parent=None):
        super().__init__(text, parent)
        self.index = index
        self.setAcceptDrops(True)
        self.drag_start_pos = QPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(str(self.index))
        drag.setMimeData(mime)
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        source_index = int(event.mimeData().text())
        target_index = self.index
        if source_index != target_index:
            main_win = self.window()
            helpers = main_win.helpers
            item = helpers.pop(source_index)
            if source_index < target_index:
                target_index -= 1
            helpers.insert(target_index, item)
            main_win.save_helper_buttons()
            main_win.refresh_helper_ui()
        event.acceptProposedAction()


class ModernComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)

        view = QListView()
        view.setUniformItemSizes(True)
        view.setSpacing(2)
        self.setView(view)

        popup_font = QFont()
        popup_font.setPointSize(11)
        popup_font.setBold(True)
        view.setFont(popup_font)

    def _get_theme(self):
        w = self.window()
        while w is not None:
            if hasattr(w, "current_theme"):
                return w.current_theme
            w = w.parent()
        return "dark"

    def showPopup(self):
        super().showPopup()

        container = self.view().window()
        if container is None:
            return

        theme = self._get_theme()
        bg = "#1E1E1E" if theme == "dark" else "#FFFFFF"

        try:
            from PySide6.QtWidgets import QFrame
            if isinstance(container, QFrame):
                container.setFrameShape(QFrame.Shape.NoFrame)
                container.setFrameShadow(QFrame.Shadow.Plain)
        except Exception:
            pass

        container.setStyleSheet(f"""
            QFrame {{
                border: 0px;
                margin: 0px;
                padding: 0px;
                background-color: {bg};
            }}
        """)
        container.setContentsMargins(0, 0, 0, 0)
