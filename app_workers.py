"""app_workers.py — All QThread workers."""
import os
import json
import traceback
import threading
import requests
import requests.packages.urllib3.util.connection as urllib3_cn
import socket

from PySide6.QtCore import QThread, Signal

import app_utils
from app_utils import (
    suppress_stdout,
    resource_path,
    DictionarySpellChecker,
    setup_default_models,
)

# --- ROCK SOLID NETWORK FIX ---
# Force IPv4 to skip Ubuntu's slow IPv6 fallback
def allowed_gai_family():
    return socket.AF_INET
urllib3_cn.allowed_gai_family = allowed_gai_family

# Create a global session to reuse the TCP connection (TLS handshake)
_global_session = requests.Session()
_session_lock = threading.Lock()
# -----------------------------

class TranslationWorker(QThread):
    # We added start_pos and end_pos to the signal
    finished = Signal(list, str, int, int)

    def __init__(self, word, start_pos, end_pos, xlit_engine=None, mode="google"):
        super().__init__()
        self.word = word
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.xlit_engine = xlit_engine
        self.mode = mode

    def run(self):
        use_google_first = (self.mode == "google")

        if use_google_first:
            try:
                url = f"https://inputtools.google.com/request?text={self.word}&itc=as-t-i0-und&num=10&cp=0&cs=1&ie=utf-8&oe=utf-8&app=demopage"
                # Use the global session with a lock to reuse connections
                with _session_lock:
                    response = _global_session.get(url, timeout=3)
                data = response.json()
                if data[0] == "SUCCESS":
                    suggestions = data[1][0][1]
                    self.finished.emit(suggestions, self.word, self.start_pos, self.end_pos)
                    return
            except Exception:
                pass

            if self.xlit_engine:
                try:
                    res = self.xlit_engine.translit_word(self.word, topk=5)
                    suggestions = []
                    if isinstance(res, dict) and 'as' in res:
                        suggestions = res['as']
                    elif isinstance(res, dict) and len(res) > 0:
                        suggestions = list(res.values())[0]
                    elif isinstance(res, list):
                        suggestions = res
                    if suggestions:
                        self.finished.emit(suggestions, self.word, self.start_pos, self.end_pos)
                        return
                except Exception as e:
                    print("XlitEngine execution error:", e)
        else:
            if self.xlit_engine:
                try:
                    res = self.xlit_engine.translit_word(self.word, topk=5)
                    suggestions = []
                    if isinstance(res, dict) and 'as' in res:
                        suggestions = res['as']
                    elif isinstance(res, dict) and len(res) > 0:
                        suggestions = list(res.values())[0]
                    elif isinstance(res, list):
                        suggestions = res
                    if suggestions:
                        self.finished.emit(suggestions, self.word, self.start_pos, self.end_pos)
                        return
                except Exception as e:
                    print("XlitEngine execution error:", e)

            try:
                url = f"https://inputtools.google.com/request?text={self.word}&itc=as-t-i0-und&num=10&cp=0&cs=1&ie=utf-8&oe=utf-8&app=demopage"
                with _session_lock:
                    response = _global_session.get(url, timeout=3)
                data = response.json()
                if data[0] == "SUCCESS":
                    suggestions = data[1][0][1]
                    self.finished.emit(suggestions, self.word, self.start_pos, self.end_pos)
                    return
            except Exception:
                pass

        self.finished.emit([self.word], self.word, self.start_pos, self.end_pos)


class SpellCheckWorker(QThread):
    results_ready = Signal(list)

    def __init__(self, text, checker):
        super().__init__()
        self.text = text
        self.checker = checker

    def run(self):
        if not self.checker:
            self.results_ready.emit([])
            return
        self.results_ready.emit(self.checker.check_text(self.text))


class MeaningWorker(QThread):
    meaning_fetched = Signal(str, str)

    def __init__(self, word):
        super().__init__()
        self.word = word

    def run(self):
        try:
            url = "https://api.mymemory.translated.net/get"
            params = {"q": self.word, "langpair": "as|en"}
            resp = requests.get(url, params=params, timeout=3)
            data = resp.json()
            meaning = ""
            if data.get("responseStatus") == 200:
                meaning = data.get("responseData", {}).get("translatedText", "")
            from app_utils import clean_translation
            meaning = clean_translation(meaning)
            self.meaning_fetched.emit(self.word, meaning)
        except Exception:
            self.meaning_fetched.emit(self.word, "")


class EnglishToAssameseWorker(QThread):
    translation_fetched = Signal(str)

    def __init__(self, text):
        super().__init__()
        self.text = text

    def run(self):
        try:
            url = "https://api.mymemory.translated.net/get"
            params = {"q": self.text, "langpair": "en|as"}
            resp = requests.get(url, params=params, timeout=3)
            data = resp.json()
            translation = ""
            if data.get("responseStatus") == 200:
                translation = data.get("responseData", {}).get("translatedText", "")
            from app_utils import clean_translation
            translation = clean_translation(translation)
            self.translation_fetched.emit(translation)
        except Exception:
            self.translation_fetched.emit("Error")


class AppLoaderThread(QThread):
    finished_loading = Signal(object, dict, object)
    error_signal = Signal(str)

    def __init__(self, dictionary_file, dict_path, setup_thread=None):
        super().__init__()
        self.dictionary_file = dictionary_file
        self.dict_path = dict_path
        self.setup_thread = setup_thread

    def run(self):
        # Wait for the model-copy thread to finish before loading Xlit.
        # This prevents the "models missing" race condition on fresh installs.
        if self.setup_thread is not None:
            try:
                self.setup_thread.wait()
            except Exception:
                pass

        spell_tool = None
        try:
            checker = DictionarySpellChecker(self.dict_path)
            if checker.is_available():
                spell_tool = checker
        except Exception:
            spell_tool = None

        dictionary = {}
        if os.path.exists(self.dictionary_file):
            try:
                with open(self.dictionary_file, "r", encoding="utf-8") as f:
                    dictionary = json.load(f)
            except Exception:
                dictionary = {}

        xlit_engine = None

        try:
            from ai4bharat.transliteration import XlitEngine
            app_utils.HAS_XLIT = True
            with suppress_stdout():
                xlit_engine = XlitEngine("as", beam_width=4, rescore=False)

            test = xlit_engine.translit_word("test", topk=1)
            if test:
                print("XlitEngine initialized successfully.")
            else:
                print("XlitEngine initialized but returned empty test result.")

        except ImportError:
            app_utils.HAS_XLIT = False
            print("ai4bharat.transliteration not available — offline engine disabled.")
        except Exception as e:
            import traceback as _tb
            app_utils.HAS_XLIT = True
            error_msg = (f"Failed to load the AI transliteration engine.\n\n"
                         f"Error: {str(e)}\n\n"
                         f"Please check if models are properly installed.")
            print(error_msg)
            log_path = os.path.join(os.path.expanduser('~'), 'sahaj_error.log')
            with open(log_path, 'w', encoding='utf-8') as f:
                _tb.print_exc(file=f)
            full_error = _tb.format_exc()
            self.error_signal.emit(f"{error_msg}\n\nFull traceback:\n{full_error}")
            xlit_engine = None

        self.finished_loading.emit(spell_tool, dictionary, xlit_engine)


class ASRLoaderThread(QThread):
    """Loads the ASR model once at startup so voice typing is instant."""
    finished_loading = Signal(object)

    def __init__(self, setup_thread=None):
        super().__init__()
        self.setup_thread = setup_thread

    def run(self):
        if app_utils.voice_typing is None:
            self.finished_loading.emit(None)
            return

        # Wait for the model-copy thread to finish before loading ASR
        if self.setup_thread is not None:
            try:
                self.setup_thread.wait()
            except Exception:
                pass

        try:
            transcriber = app_utils.voice_typing.load_transcriber()
            self.finished_loading.emit(transcriber)
        except Exception as e:
            print(f"ASR pre-load failed: {e}")
            self.finished_loading.emit(None)


class NetworkProbeThread(QThread):
    """One-shot internet reachability probe, run in the background."""
    result = Signal(bool)

    def run(self):
        try:
            requests.head("https://www.google.com", timeout=3, allow_redirects=True)
            self.result.emit(True)
        except Exception:
            self.result.emit(False)


class SetupThread(QThread):
    """Runs setup_default_models() in the background so the splash can appear instantly."""
    done = Signal()

    def run(self):
        try:
            setup_default_models()
        except Exception as e:
            print(f"setup_default_models failed: {e}")
        self.done.emit()