"""app_styles.py — Theme styles and font handling for সহজ-Sahaj."""

# Shared font list — mutated in-place by set_font_families() so every
# module that imports CUSTOM_FONT_FAMILIES sees the update.
CUSTOM_FONT_FAMILIES = [
    "Nirmala UI", "Segoe UI",
    "Noto Sans Bengali", "Lohit Bengali",
    "DejaVu Sans", "Arial",
]


def set_font_families(families):
    """Update the shared font list in-place (all importers see the change)."""
    CUSTOM_FONT_FAMILIES.clear()
    CUSTOM_FONT_FAMILIES.extend(families)


def font_family_css(families):
    """Convert a list of family names to a CSS font-family string."""
    quoted = [f'"{f}"' if ' ' in f else f for f in families]
    return ", ".join(quoted) + ", sans-serif"


LIGHT_STYLE = """
QWidget {
    background-color: #F8F9FA;
    font-family: {font_css};
    color: #333333;
}
QLabel#headerText {
    color: #2C3E50;
    padding: 15px 0px 5px 0px;
}
QPlainTextEdit {
    font-family: {font_css};
    background-color: #FFFFFF;
    border: 2px solid #DEE2E6;
    border-radius: 8px;
    padding: 12px;
    selection-background-color: #0D6EFD;
    selection-color: #FFFFFF;
    color: #333333;
}
QPlainTextEdit:focus {
    border: 2px solid #86B7FE;
}
QLineEdit {
    border: 1px solid #CED4DA;
    border-radius: 6px;
    padding: 6px 8px;
    min-height: 26px;
    background-color: #FFFFFF;
    color: #333333;
}
QPushButton {
    background-color: #FFFFFF;
    border: 1px solid #CED4DA;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 500;
    color: #495057;
}
QPushButton:hover {
    background-color: #E2E6EA;
    border-color: #DAE0E5;
    color: #212529;
}
QPushButton:pressed {
    background-color: #DAE0E5;
}
QPushButton#primaryBtn {
    background-color: #0D6EFD;
    color: #FFFFFF;
    border: none;
}
QPushButton#primaryBtn:hover {
    background-color: #0B5ED7;
}
QPushButton#primaryBtn:pressed {
    background-color: #0A58CA;
}
QPushButton#successBtn {
    background-color: #198754;
    color: #FFFFFF;
    border: none;
    font-weight: bold;
}
QPushButton#successBtn:hover {
    background-color: #157347;
}
QPushButton#successBtn:pressed {
    background-color: #146C43;
}
QPushButton#keepEnBtn {
    background-color: #6C757D;
    color: #FFFFFF;
    border: none;
    font-weight: bold;
}
QPushButton#keepEnBtn:hover {
    background-color: #5A6268;
}
QPushButton#keepEnBtn:pressed {
    background-color: #545B62;
}
QListWidget {
    background-color: #FFFFFF;
    border: 1px solid #CED4DA;
    border-radius: 8px;
    outline: none;
    color: #333333;
    font-family: {font_css};
}
QListWidget::item {
    padding: 10px;
    border-bottom: 1px solid #ADB5BD;
}
QListWidget::item:selected {
    background-color: #E7F1FF;
    color: #0C63E4;
    border-radius: 4px;
}
QListWidget::item:hover:!selected {
    background-color: #F8F9FA;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollBar:horizontal, QScrollBar:vertical {
    border: none;
    background: #E9ECEF;
    width: 8px;
    height: 8px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal, QScrollBar::handle:vertical {
    background: #ADB5BD;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover, QScrollBar::handle:vertical:hover {
    background: #6C757D;
}
QScrollBar::add-line, QScrollBar::sub-line {
    border: none;
    background: none;
}
QLabel#translatedResult {
    font-family: {font_css};
    color: #0D6EFD;
    font-weight: bold;
}
QComboBox {
    background-color: #FFFFFF;
    color: #333333;
    border: 1px solid #CED4DA;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: bold;
    font-size: 14px;
    min-width: 150px;
}
QComboBox:hover {
    border-color: #86B7FE;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #495057;
    width: 0;
    height: 0;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #333333;
    border: 1px solid #E1E4E8;
    border-radius: 8px;
    outline: 0;
    padding: 6px;
    selection-background-color: transparent;
    selection-color: #0C63E4;
}
QComboBox QAbstractItemView::item {
    padding: 8px 14px;
    border-radius: 5px;
    min-height: 22px;
    font-size: 14px;
    color: #333333;
}
QComboBox QAbstractItemView::item:hover {
    background-color: #F1F3F5;
    color: #0C63E4;
}
QComboBox QAbstractItemView::item:selected {
    background-color: #E7F1FF;
    color: #0C63E4;
}
QMenu {
    background-color: #FFFFFF;
    border: 1px solid #CED4DA;
    border-radius: 6px;
    padding: 4px;
    color: #333333;
    font-family: {font_css};
}
QMenu::item {
    padding: 8px 25px 8px 15px;
    border-radius: 4px;
    font-family: {font_css};
}
QMenu::item:selected {
    background-color: #0D6EFD;
    color: #FFFFFF;
}
QMenu::separator {
    height: 1px;
    background-color: #CED4DA;
    margin: 4px 0px;
}
"""

DARK_STYLE = """
QWidget {
    background-color: #2C2C2C;
    font-family: {font_css};
    color: #E0E0E0;
}
QLabel#headerText {
    color: #EAEAEA;
    padding: 15px 0px 5px 0px;
}
QPlainTextEdit {
    font-family: {font_css};
    background-color: #1E1E1E;
    color: #E0E0E0;
    border: 2px solid #555555;
    border-radius: 8px;
    padding: 12px;
    selection-background-color: #007ACC;
    selection-color: #FFFFFF;
}
QPlainTextEdit:focus {
    border: 2px solid #86B7FE;
}
QLineEdit {
    border: 1px solid #555555;
    border-radius: 6px;
    padding: 6px 8px;
    min-height: 26px;
    background-color: #1E1E1E;
    color: #E0E0E0;
}
QTextEdit:focus {
    border: 2px solid #86B7FE;
}
QPushButton {
    background-color: #3C3C3C;
    border: 1px solid #555555;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 500;
    color: #E0E0E0;
}
QPushButton:hover {
    background-color: #505050;
    border-color: #666666;
    color: #FFFFFF;
}
QPushButton:pressed {
    background-color: #404040;
}
QPushButton#primaryBtn {
    background-color: #0D6EFD;
    color: #FFFFFF;
    border: none;
}
QPushButton#primaryBtn:hover {
    background-color: #0B5ED7;
}
QPushButton#primaryBtn:pressed {
    background-color: #0A58CA;
}
QPushButton#successBtn {
    background-color: #198754;
    color: #FFFFFF;
    border: none;
    font-weight: bold;
}
QPushButton#successBtn:hover {
    background-color: #157347;
}
QPushButton#successBtn:pressed {
    background-color: #146C43;
}
QPushButton#keepEnBtn {
    background-color: #6C757D;
    color: #FFFFFF;
    border: none;
    font-weight: bold;
}
QPushButton#keepEnBtn:hover {
    background-color: #5A6268;
}
QPushButton#keepEnBtn:pressed {
    background-color: #545B62;
}
QListWidget {
    background-color: #2C2C2C;
    color: #E0E0E0;
    border: 1px solid #555555;
    border-radius: 8px;
    outline: none;
    font-family: {font_css};
}
QListWidget::item {
    padding: 10px;
    border-bottom: 1px solid #555555;
}
QListWidget::item:selected {
    background-color: #094771;
    color: #FFFFFF;
    border-radius: 4px;
}
QListWidget::item:hover:!selected {
    background-color: #3C3C3C;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollBar:horizontal, QScrollBar:vertical {
    border: none;
    background: #3C3C3C;
    width: 8px;
    height: 8px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal, QScrollBar::handle:vertical {
    background: #666666;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover, QScrollBar::handle:vertical:hover {
    background: #888888;
}
QScrollBar::add-line, QScrollBar::sub-line {
    border: none;
    background: none;
}
QLabel#translatedResult {
    font-family: {font_css};
    color: #86B7FE;
    font-weight: bold;
}
QComboBox {
    background-color: #3C3C3C;
    color: #E0E0E0;
    border: 1px solid #555555;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: bold;
    font-size: 14px;
    min-width: 150px;
}
QComboBox:hover {
    border-color: #86B7FE;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #E0E0E0;
    width: 0;
    height: 0;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #1E1E1E;
    color: #E0E0E0;
    border: 1px solid #4A4A4A;
    border-radius: 8px;
    outline: 0;
    padding: 6px;
    selection-background-color: transparent;
    selection-color: #86B7FE;
}
QComboBox QAbstractItemView::item {
    padding: 8px 14px;
    border-radius: 5px;
    min-height: 22px;
    font-size: 14px;
    color: #E0E0E0;
}
QComboBox QAbstractItemView::item:hover {
    background-color: #3A3A3A;
    color: #86B7FE;
}
QComboBox QAbstractItemView::item:selected {
    background-color: #094771;
    color: #FFFFFF;
}
QMenu {
    background-color: #2C2C2C;
    border: 1px solid #555555;
    border-radius: 6px;
    padding: 4px;
    color: #E0E0E0;
    font-family: {font_css};
}
QMenu::item {
    padding: 8px 25px 8px 15px;
    border-radius: 4px;
    font-family: {font_css};
}
QMenu::item:selected {
    background-color: #007ACC;
    color: #FFFFFF;
}
QMenu::separator {
    height: 1px;
    background-color: #555555;
    margin: 4px 0px;
}
"""