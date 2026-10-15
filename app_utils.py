"""app_utils.py — Utility helpers + shared module-level state."""
import os
import sys
import html
import re
import shutil
import unicodedata
import difflib
from contextlib import contextmanager

import requests


# ==================================================================
# Shared module-level state
# ==================================================================
session = requests.Session()

voice_typing = None
typing_modes = None
HAS_TYPING_MODES = False
HAS_XLIT = None


# ==================================================================
# Set AI4BHARAT model-dir env var when running frozen
# ==================================================================
if getattr(sys, 'frozen', False):
    base_model_dir = os.path.join(
        sys._MEIPASS, '_internal', 'ai4bharat', 'transliteration',
        'transformer', 'models', 'en2indic',
    )
    if os.path.exists(base_model_dir):
        os.environ['AI4BHARAT_XLIT_MODEL_DIR'] = base_model_dir


# ==================================================================
# Helpers
# ==================================================================
@contextmanager
def suppress_stdout():
    """Temporarily suppress stdout AND stderr to avoid progressbar crashes
    in frozen windowed apps (where both are None)."""
    with open(os.devnull, 'w') as devnull:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = devnull
        sys.stderr = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


def setup_default_models():
    """Copy bundled models to the default location ~/.AI4Bharat_Xlit_Models/en2indic."""
    if not getattr(sys, 'frozen', False):
        return

    target_root = os.path.join(os.path.expanduser('~'), '.AI4Bharat_Xlit_Models', 'en2indic')
    target_v1_dir = os.path.join(target_root, 'v1.0')

    bundled_root = os.path.join(sys._MEIPASS, '_internal', 'ai4bharat', 'transliteration',
                                'transformer', 'models', 'en2indic')
    if not os.path.exists(bundled_root):
        bundled_root = os.path.join(sys._MEIPASS, 'ai4bharat', 'transliteration',
                                    'transformer', 'models', 'en2indic')
        if not os.path.exists(bundled_root):
            print("ERROR: Bundled models not found.")
            return

    required_files = ['model.pt', 'vocab.txt', 'dict.txt']
    is_valid = True
    if os.path.exists(target_v1_dir):
        for f in required_files:
            file_path = os.path.join(target_v1_dir, f)
            if not os.path.exists(file_path) or os.path.getsize(file_path) < 1000:
                is_valid = False
                break
        lang_file = os.path.join(target_root, 'lang_list.txt')
        if not os.path.exists(lang_file) or os.path.getsize(lang_file) < 100:
            is_valid = False
    else:
        is_valid = False

    if is_valid:
        print("Models already present in default location.")
        return

    if os.path.exists(target_v1_dir):
        shutil.rmtree(target_v1_dir)

    shutil.copytree(os.path.join(bundled_root, 'v1.0'), target_v1_dir, dirs_exist_ok=True)

    src_lang = os.path.join(bundled_root, 'lang_list.txt')
    if os.path.exists(src_lang):
        shutil.copy2(src_lang, target_root)
        print("Copied lang_list.txt")

    print("Models copied to default location:", target_root)


def get_user_data_dir():
    """Return a writable per-user folder for this app.
    - Windows: %LOCALAPPDATA%\\Sahaj_v1_1
    - Linux/macOS: ~/.local/share/Sahaj_v1_1 (or $XDG_DATA_HOME)
    """
    if sys.platform == "win32":
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    else:
        base = os.environ.get(
            'XDG_DATA_HOME',
            os.path.join(os.path.expanduser('~'), '.local', 'share')
        )
    app_dir = os.path.join(base, 'Sahaj_v1_1')
    os.makedirs(app_dir, exist_ok=True)
    return app_dir


def clean_translation(text):
    """Remove HTML tags, unescape, strip, and clean common MyMemory junk."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = text.strip()
    if text.startswith('(') and text.endswith(')'):
        text = text[1:-1].strip()
    text = re.sub(r'^\(\)\s*', '', text)
    text = text.strip()
    return text


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# ==================================================================
# Dictionary spell checker
# ==================================================================
class DictionarySpellChecker:
    def __init__(self, dict_file="assamese_dictionary.txt"):
        self.words = set()
        if os.path.exists(dict_file):
            with open(dict_file, "r", encoding="utf-8") as f:
                for line in f:
                    word = line.strip()
                    if word and not word.startswith("#"):
                        self.words.add(unicodedata.normalize('NFC', word))
        self.dict_file = dict_file

    def check_text(self, text):
        errors = []
        for match in re.finditer(r'[\u0980-\u09FF\u200C\u200D]+', text):
            raw_word = match.group()
            start = match.start()
            end = match.end()
            word = unicodedata.normalize('NFC', raw_word.strip())
            if word not in self.words:
                suggestions = self.get_suggestions(word)
                if word in suggestions:
                    continue
                errors.append((start, end, suggestions))
        return errors

    def get_suggestions(self, word, max_suggestions=8):
        return difflib.get_close_matches(word, self.words, n=max_suggestions, cutoff=0.6)

    def is_available(self):
        return len(self.words) > 0