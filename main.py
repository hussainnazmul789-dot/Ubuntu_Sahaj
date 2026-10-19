"""main.py — Entry point for সহজ-Sahaj v3.0."""
import os
import sys

# On Linux, force Qt to use XWayland (X11) instead of native Wayland.
# Wayland ignores window position hints, which makes our splash and dialogs
# appear top-left instead of centered. XWayland respects them correctly.
# Must be set BEFORE QApplication is created.
if sys.platform.startswith("linux"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PySide6.QtWidgets import (
    QApplication, QLabel,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase, QMovie, QIcon, QPixmap

# app_utils is safe to import early — it does not pull in voice_typing.
import app_utils
from app_utils import resource_path
from app_styles import set_font_families
import sahaj_license
from app_dialogs import ensure_licensed


def center_on_screen(widget):
    """Center a top-level widget on the primary screen."""
    try:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        w = widget.width()
        h = widget.height()
        widget.move(
            geo.x() + (geo.width() - w) // 2,
            geo.y() + (geo.height() - h) // 2,
        )
    except Exception:
        pass


def ensure_desktop_file():
    """Create ~/.local/share/applications/sahaj.desktop on first run,
    so GNOME's taskbar can find our icon."""
    try:
        import shutil
        home = os.path.expanduser("~")
        apps_dir = os.path.join(home, ".local", "share", "applications")
        icons_dir = os.path.join(
            home, ".local", "share", "icons", "hicolor", "256x256", "apps"
        )
        os.makedirs(apps_dir, exist_ok=True)
        os.makedirs(icons_dir, exist_ok=True)

        # Copy icon into the user's icon theme directory
        icon_src = resource_path("header_icon.png")
        icon_dst = os.path.join(icons_dir, "sahaj.png")
        if os.path.exists(icon_src):
            shutil.copy2(icon_src, icon_dst)

        # Write the .desktop file
        exe_path = os.path.abspath(sys.argv[0])
        desktop_path = os.path.join(apps_dir, "sahaj.desktop")
        with open(desktop_path, "w", encoding="utf-8") as f:
            f.write(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Sahaj\n"
                "Comment=AI Assamese Typing Tool\n"
                f"Exec={exe_path}\n"
                "Icon=sahaj\n"
                "Terminal=false\n"
                "Categories=Utility;TextEditor;\n"
                "StartupWMClass=sahaj\n"
            )
    except Exception:
        pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Sahaj")
    app.setApplicationDisplayName("সহজ-Sahaj")
    app.setOrganizationName("NazmulDev")

    # Tell Linux which .desktop file to associate this window with.
    # GNOME uses this to find the correct taskbar icon.
    try:
        app.setDesktopFileName("sahaj")
    except Exception:
        pass

    clipboard = QApplication.clipboard()
    clipboard.clear()

    app_icon_path = resource_path("header_icon.png")
    if os.path.exists(app_icon_path):
        app.setWindowIcon(QIcon(app_icon_path))

    # Create the .desktop file so the taskbar can find our icon
    if sys.platform != "win32":
        ensure_desktop_file()

    # --- LICENSE CHECK (before splash) ---
    if not ensure_licensed():
        sys.exit(0)

    # --- Load fonts (fast, main thread) ---
    available_families = []

    font_path1 = resource_path("Nirmala.ttf")
    font_id1 = QFontDatabase.addApplicationFont(font_path1)
    if font_id1 != -1:
        family1 = QFontDatabase.applicationFontFamilies(font_id1)[0]
        available_families.append(family1)

    font_path2 = resource_path("Banikanta.ttf")
    font_id2 = QFontDatabase.addApplicationFont(font_path2)
    if font_id2 != -1:
        family2 = QFontDatabase.applicationFontFamilies(font_id2)[0]
        if family2 not in available_families:
            available_families.append(family2)

    cross_platform_fallbacks = [
        "Nirmala UI", "Segoe UI",
        "Noto Sans Bengali", "Lohit Bengali",
        "DejaVu Sans", "Arial",
    ]
    if not available_families:
        available_families = list(cross_platform_fallbacks)
    else:
        available_families.extend(cross_platform_fallbacks)

    seen = set()
    available_families = [f for f in available_families if not (f in seen or seen.add(f))]
    set_font_families(available_families)

    # --- Splash: shown BEFORE any heavy imports so it appears fast ---
    splash_gif_path = resource_path("splash_animation.gif")

    splash = QLabel()
    splash.setWindowFlags(
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.Window
    )

    if os.path.exists(splash_gif_path):
        splash.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        movie = QMovie(splash_gif_path)
        splash.setMovie(movie)
        movie.start()
    else:
        splash.setFixedSize(450, 250)
        splash.setAlignment(Qt.AlignmentFlag.AlignCenter)
        splash.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2C3E50, stop:1 #3498DB);
                color: white;
                font-family: "Segoe UI";
                font-size: 26px;
                font-weight: bold;
                border-radius: 12px;
                padding: 20px;
            }
        """)
        splash.setText("সহজ-Sahaj-v3.0\n\nLoading, please wait...\n\nDeveloped by Nazmul Hussain")

    splash.adjustSize()
    center_on_screen(splash)
    splash.show()
    app.processEvents()

    # ============================================================
    # Everything below runs AFTER the splash is visible.
    # ============================================================

    # Deferred: voice_typing pulls in torch, transformers, onnxruntime, pyaudio.
    try:
        import voice_typing
        app_utils.voice_typing = voice_typing
    except ImportError as e:
        app_utils.voice_typing = None
        print(f"Voice typing module not available: {e}")

    # Optional typing_modes
    try:
        import typing_modes
        app_utils.typing_modes = typing_modes
        app_utils.HAS_TYPING_MODES = True
    except ImportError as e:
        app_utils.typing_modes = None
        app_utils.HAS_TYPING_MODES = False
        print(f"Typing modes module not available: {e}")

    # Deferred: heavy app_window import (pulls PySide6 etc.)
    from app_window import AssameseTypingApp
    from app_workers import SetupThread

    # Start the background model-copy thread now that the splash is up.
    setup_thread = SetupThread()
    setup_thread.start()

    # Create the main window — pass setup_thread so Xlit/ASR wait for it.
    # DO NOT call show() or hide() here. Ubuntu 26's GNOME shell gets confused
    # by quickly hiding a window and creates a ghost taskbar icon. The window
    # will be shown properly in finish_startup() via showMaximized().
    main_window = AssameseTypingApp(setup_thread=setup_thread)

    def finish_startup():
        def loaders_busy():
            try:
                if getattr(main_window, "asr_loader_thread", None) and \
                        main_window.asr_loader_thread.isRunning():
                    return True
                if getattr(main_window, "loader_thread", None) and \
                        main_window.loader_thread.isRunning():
                    return True
            except Exception:
                pass
            return False

        def reveal_window_and_dismiss(cover):
            try:
                main_window.showMaximized()
                main_window.raise_()
                main_window.activateWindow()
            except Exception:
                pass

            def _dismiss():
                try:
                    if cover is not None:
                        cover.hide()
                        cover.close()
                except Exception:
                    pass
            QTimer.singleShot(500, _dismiss)

        if not loaders_busy():
            reveal_window_and_dismiss(splash)
            return

        warmup = QLabel(
            "⏳ Warming up Sahaj's AI Engines...\n"
            "...Ready in just a moment !"
        )
        warmup.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warmup.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
        )
        warmup.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                            stop:0 #2C3E50, stop:1 #3498DB);
                color: white;
                font-family: "Segoe UI";
                font-size: 20px;
                font-weight: bold;
                border-radius: 12px;
                padding: 20px;
            }
        """)
        try:
            warmup.setFixedSize(splash.size())
        except Exception:
            warmup.setFixedSize(450, 250)
        center_on_screen(warmup)
        warmup.show()
        try:
            splash.hide()
            splash.close()
        except Exception:
            pass

        # Poll every 300 ms; force-reveal after 60 s
        state = {"count": 0}
        MAX_POLLS = 200  # 200 × 300 ms = 60 seconds

        def poll():
            state["count"] += 1
            if loaders_busy() and state["count"] < MAX_POLLS:
                QTimer.singleShot(300, poll)
            else:
                reveal_window_and_dismiss(warmup)

        QTimer.singleShot(300, poll)

    QTimer.singleShot(5000, finish_startup)
    sys.exit(app.exec())