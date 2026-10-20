import time
import os
import sys
import tempfile
import wave
import traceback
import array
import pyaudio
import threading
from contextlib import contextmanager
from PySide6.QtCore import QThread, Signal, QTimer


# ==================================================================
# CRITICAL: Set HuggingFace env vars BEFORE any HF library is imported
# This must happen at module load time, not inside a function.
# ==================================================================

def log_error(msg):
    log_path = os.path.join(os.path.expanduser('~'), 'sahaj_voice_error.log')
    try:
        if os.path.exists(log_path) and os.path.getsize(log_path) > 1024 * 1024:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write("")
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(msg + '\n')
    except:
        pass


def cleanup_old_temp_files(max_age_hours=24):
    """Delete leftover Sahaj temp files from previous sessions."""
    import glob
    import time as _time
    try:
        temp_dir = tempfile.gettempdir()
        now = _time.time()
        cutoff = now - (max_age_hours * 3600)
        removed = 0
        for path in glob.glob(os.path.join(temp_dir, "tmp*.wav")):
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except Exception:
                pass
        if removed:
            log_error(f"Cleanup: removed {removed} leftover temp file(s).")
    except Exception as e:
        log_error(f"Cleanup failed (non-fatal): {e}")


cleanup_old_temp_files(max_age_hours=24)


# --- Locate the bundled ASR cache dir ---
_ASR_CACHE_DIR = None
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
    candidate = os.path.join(base_path, 'indic_asr_cache')
    if os.path.exists(candidate):
        _ASR_CACHE_DIR = candidate
        log_error(f"ASR cache located at {candidate}")
    else:
        log_error(f"Warning: Bundled ASR cache not found at {candidate}")

    ffmpeg_dir = os.path.join(base_path, 'ffmpeg_bin')
    if os.path.exists(ffmpeg_dir) and os.listdir(ffmpeg_dir):
        os.environ['PATH'] = ffmpeg_dir + os.pathsep + os.environ.get('PATH', '')
        os.environ['TORCHAUDIO_USE_FFMPEG'] = '1'
        log_error(f"Added FFmpeg to PATH: {ffmpeg_dir}")
    else:
        # On Linux, FFmpeg is normally installed system-wide via apt.
        import shutil as _shutil
        if _shutil.which('ffmpeg'):
            log_error("Using system FFmpeg (bundled copy not present).")
        else:
            log_error("FFmpeg not found — some audio conversions may fail.")


# ==================================================================
# CRITICAL FIX: Set HuggingFace env vars BEFORE importing indic_asr_onnx.
# This ensures the library reads the correct cache path and offline mode
# from the very first import, preventing network calls on fresh PCs.
# ==================================================================
if _ASR_CACHE_DIR:
    os.environ['HF_HUB_CACHE'] = _ASR_CACHE_DIR
    os.environ['HUGGINGFACE_HUB_CACHE'] = _ASR_CACHE_DIR
    os.environ['TRANSFORMERS_CACHE'] = _ASR_CACHE_DIR
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_DATASETS_OFFLINE'] = '1'


# ---- Diagnostic: verify the bundled cache structure ----
if _ASR_CACHE_DIR:
    try:
        items = os.listdir(_ASR_CACHE_DIR)
        log_error(f"ASR cache contents: {items}")
        for item in items:
            if item.startswith('models--'):
                model_dir = os.path.join(_ASR_CACHE_DIR, item)
                snapshots_dir = os.path.join(model_dir, 'snapshots')
                refs_dir = os.path.join(model_dir, 'refs')
                if os.path.isdir(snapshots_dir):
                    snapshots = os.listdir(snapshots_dir)
                    log_error(f"  {item}: {len(snapshots)} snapshots")
                else:
                    log_error(f"  {item}: NO snapshots folder (cache is malformed!)")
                if not os.path.isdir(refs_dir):
                    log_error(f"  {item}: NO refs folder (cache is malformed!)")
    except Exception as e:
        log_error(f"Failed to inspect ASR cache: {e}")


# --- Import ASR (after env vars are set) ---
HAS_ASR = False
ASR_IMPORT_ERROR = None

try:
    from indic_asr_onnx import IndicTranscriber
    HAS_ASR = True
    log_error("Voice typing: indic_asr_onnx imported successfully.")
except ImportError as e:
    ASR_IMPORT_ERROR = str(e)
    log_error(f"Voice typing: ImportError - {e}")
    try:
        traceback.print_exc(file=open(os.path.join(os.path.expanduser('~'), 'sahaj_voice_error.log'), 'a'))
    except Exception:
        pass
except Exception as e:
    ASR_IMPORT_ERROR = str(e)
    log_error(f"Voice typing: Unexpected import error - {e}")
    try:
        traceback.print_exc(file=open(os.path.join(os.path.expanduser('~'), 'sahaj_voice_error.log'), 'a'))
    except Exception:
        pass


# ==================================================================
# ASR env context (kept as a safety net around runtime operations)
# ==================================================================
@contextmanager
def _asr_env_context():
    prev_cache = os.environ.get('HF_HUB_CACHE')
    prev_offline = os.environ.get('HF_HUB_OFFLINE')

    if _ASR_CACHE_DIR:
        os.environ['HF_HUB_CACHE'] = _ASR_CACHE_DIR
    os.environ['HF_HUB_OFFLINE'] = '1'

    try:
        yield
    finally:
        if prev_cache is None:
            os.environ.pop('HF_HUB_CACHE', None)
        else:
            os.environ['HF_HUB_CACHE'] = prev_cache
        if prev_offline is None:
            os.environ.pop('HF_HUB_OFFLINE', None)
        else:
            os.environ['HF_HUB_OFFLINE'] = prev_offline


# ==================================================================
# Voice Recorder
# ==================================================================
class VoiceRecorderWorker(QThread):
    recording_started = Signal()
    recording_stopped = Signal(str)
    error = Signal(str)
    level_update = Signal(float)

    def __init__(self, max_duration=24):
        super().__init__()
        self.audio = None
        self.stream = None
        self.frames = []
        self.is_recording = False
        self._stop_requested = False
        self.max_duration = max_duration
        self.start_time = None

    def run(self):
        try:
            self.audio = pyaudio.PyAudio()
            
            # --- DEBUG: Print all available microphones to the log ---
            log_error("--- AVAILABLE MICROPHONES ---")
            for i in range(self.audio.get_device_count()):
                dev = self.audio.get_device_info_by_index(i)
                if dev['maxInputChannels'] > 0:
                    log_error(f"ID {i}: {dev['name']} (Rate: {dev['defaultSampleRate']})")
            log_error("-----------------------------")
            # ---------------------------------------------------------

            self.frames = []
            self.is_recording = True
            self._stop_requested = False
            self.start_time = time.time()
            
            # --- FALLBACK LOGIC FOR NEWER UBUNTU (PIPEWIRE) ---
            try:
                self.actual_rate = 16000
                self.stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.actual_rate,
                    input=True,
                    frames_per_buffer=1024,
                    stream_callback=self._callback
                )
            except OSError:
                log_error("16000 Hz not supported by default mic. Falling back to device default.")
                default_info = self.audio.get_default_input_device_info()
                self.actual_rate = int(default_info['defaultSampleRate'])
                self.stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.actual_rate,
                    input=True,
                    frames_per_buffer=1024,
                    stream_callback=self._callback
                )
            # ---------------------------------------------------

            self.stream.start_stream()
            self.recording_started.emit()
            log_error(f"Recording started at {self.actual_rate} Hz.")

            while not self._stop_requested:
                elapsed = time.time() - self.start_time
                if elapsed >= self.max_duration:
                    log_error(f"Reached max duration ({self.max_duration}s), stopping.")
                    break
                self.msleep(100)

            self.is_recording = False
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
            if self.audio:
                self.audio.terminate()
                self.audio = None

            if self.frames:
                # Save to a permanent location in the Home folder for debugging
                debug_filename = os.path.join(os.path.expanduser('~'), 'Sahaj_debug_raw.wav')
                with wave.open(debug_filename, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.actual_rate)
                    wf.writeframes(b''.join(self.frames))
                
                log_error(f"DEBUG: Raw recording saved to {debug_filename}")
                self.recording_stopped.emit(debug_filename)
            else:
                self.error.emit("No audio recorded.")

        except Exception as e:
            error_msg = f"Recording error: {str(e)}\n{traceback.format_exc()}"
            log_error(error_msg)
            self.error.emit(error_msg)

    def _callback(self, in_data, frame_count, time_info, status):
        if self.is_recording:
            self.frames.append(in_data)
            try:
                samples = array.array('h', in_data)
                if samples:
                    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
                    raw = rms / 32767.0
                    boosted = min(raw * 8.0, 1.0)
                    normalized = boosted ** 0.5
                    self.level_update.emit(normalized)
            except Exception:
                pass
        return (in_data, pyaudio.paContinue)

    def stop(self):
        self._stop_requested = True


# ==================================================================
# Voice Transcriber worker
# ==================================================================
class VoiceTypingWorker(QThread):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, audio_filepath, transcriber=None, timeout_seconds=30):
        super().__init__()
        self.audio_filepath = audio_filepath
        self.transcriber = transcriber
        self.timeout_seconds = timeout_seconds

    def run(self):
        try:
            if not HAS_ASR:
                self.error.emit(f"Voice typing is not available.\nImport error: {ASR_IMPORT_ERROR}")
                return

            if not self.audio_filepath or not os.path.exists(self.audio_filepath):
                self.error.emit("Audio file not found.")
                return

            try:
                with wave.open(self.audio_filepath, 'rb') as wf:
                    n_frames = wf.getnframes()
                    if n_frames == 0:
                        self.error.emit("No audio recorded. Please check your microphone and try again.")
                        return
                    if os.path.getsize(self.audio_filepath) < 1000:
                        self.error.emit("Audio file is too small. Please record a longer clip.")
                        return
            except Exception as e:
                log_error(f"Audio file validation error: {e}")
                self.error.emit("Could not read the audio file. Please try again.")
                return

            with _asr_env_context():
                if self.transcriber is not None:
                    transcriber = self.transcriber
                    log_error("Using pre-loaded IndicTranscriber (fast path).")
                else:
                    log_error("No pre-loaded transcriber — loading on demand (slow path).")
                    devnull = open(os.devnull, 'w')
                    old_stdout = sys.stdout
                    old_stderr = sys.stderr
                    sys.stdout = devnull
                    sys.stderr = devnull
                    try:
                        transcriber = IndicTranscriber()
                        log_error("IndicTranscriber initialized on demand.")
                    finally:
                        sys.stdout = old_stdout
                        sys.stderr = old_stderr
                        devnull.close()

                # --- RESAMPLE AUDIO IF FALLBACK WAS USED ---
                resampled_path = os.path.join(os.path.expanduser('~'), 'Sahaj_debug_resampled.wav')
                process_path = self.audio_filepath
                try:
                    import soundfile as sf
                    import torch
                    import torchaudio
                    
                    # always_2d=False ensures we get a 1D array, preventing channel mix-ups
                    data, samplerate = sf.read(self.audio_filepath, dtype='float32', always_2d=False)
                    
                    if samplerate != 16000:
                        tensor = torch.from_numpy(data).float()
                        # Resample requires the tensor to be at least 1D
                        resampled = torchaudio.functional.resample(tensor, orig_freq=samplerate, new_freq=16000)
                        data_16k = resampled.numpy()
                        # Save for debugging
                        sf.write(resampled_path, data_16k, 16000)
                        process_path = resampled_path
                        log_error(f"Audio successfully resampled from {samplerate} to 16000 Hz.")
                    else:
                        log_error("Audio is already 16000 Hz, no resampling needed.")
                except Exception as e:
                    log_error(f"Resampling failed, using original audio: {e}")
                # -------------------------------------------

                CHUNK_SECONDS = 12
                OVERLAP_SECONDS = 0.5
                SAMPLE_RATE = 16000
                CHUNK_SAMPLES = CHUNK_SECONDS * SAMPLE_RATE
                OVERLAP_SAMPLES = OVERLAP_SECONDS * SAMPLE_RATE

                with wave.open(process_path, 'rb') as wf:
                    raw_data = wf.readframes(wf.getnframes())

                samples = array.array('h', raw_data)
                total_samples = len(samples)

                full_text = []
                start_sample = 0
                start_time = time.time()

                while start_sample < total_samples:
                    elapsed = time.time() - start_time
                    if elapsed > self.timeout_seconds:
                        log_error(f"Transcription timed out after {elapsed:.1f}s")
                        self.error.emit(
                            f"Transcription is taking too long (over {self.timeout_seconds} seconds).\n\n"
                            "This can happen on slower computers.\n"
                            "Please try:\n"
                            "• Recording a shorter sentence (10‑15 seconds)\n"
                            "• Closing other applications to free up memory\n"
                            "• Restarting the app and trying again"
                        )
                        return

                    end_sample = min(start_sample + CHUNK_SAMPLES, total_samples)
                    start_idx = int(start_sample)
                    end_idx = int(end_sample)
                    chunk_samples = samples[start_idx:end_idx]

                    temp_chunk = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                    temp_chunk_path = temp_chunk.name
                    temp_chunk.close()

                    try:
                        with wave.open(temp_chunk_path, 'wb') as wf_chunk:
                            wf_chunk.setnchannels(1)
                            wf_chunk.setsampwidth(2)
                            wf_chunk.setframerate(SAMPLE_RATE)
                            wf_chunk.writeframes(chunk_samples.tobytes())

                        chunk_text = transcriber.transcribe_rnnt(temp_chunk_path, "as")
                        if chunk_text and chunk_text.strip():
                            full_text.append(chunk_text.strip())

                    except Exception as e:
                        log_error(f"Chunk transcription error: {e}")
                    finally:
                        for attempt in range(5):
                            try:
                                os.remove(temp_chunk_path)
                                break
                            except PermissionError:
                                time.sleep(0.1 * (attempt + 1))
                            except Exception as e:
                                log_error(f"Failed to delete {temp_chunk_path}: {e}")
                                break

                    start_sample = int(start_sample + (CHUNK_SAMPLES - OVERLAP_SAMPLES))

            if full_text:
                deduped = []
                prev = ""
                for chunk in full_text:
                    if prev:
                        import difflib
                        ratio = difflib.SequenceMatcher(None, prev, chunk).ratio()
                        if ratio > 0.7:
                            continue
                    deduped.append(chunk)
                    prev = chunk
                combined = " ".join(deduped).strip()
                self.finished.emit(combined)
            else:
                self.error.emit("Could not understand the audio. Please try again with clearer speech.")

        except Exception as e:
            error_msg = f"VoiceTypingWorker.run error: {str(e)}\n{traceback.format_exc()}"
            log_error(error_msg)
            self.error.emit(
                f"An error occurred during voice typing.\n\n"
                f"Error: {str(e)}\n\n"
                f"Please check the log file:\n"
                f"{os.path.join(os.path.expanduser('~'), 'sahaj_voice_error.log')}"
            )
        finally:
            # TEMPORARILY DISABLED FOR DEBUGGING
            log_error("DEBUG MODE: Files were not deleted so you can listen to them.")
            pass


# ==================================================================
# Pre-loader (called once from ASRLoaderThread in main.py)
# ==================================================================
def load_transcriber():
    """
    Load IndicTranscriber once. Env vars are already set at module level
    so HF_HUB_CACHE points to the bundled cache and HF_HUB_OFFLINE is on.
    """
    if not HAS_ASR:
        log_error("load_transcriber: HAS_ASR is False — skipping pre-load.")
        return None

    with _asr_env_context():
        devnull = open(os.devnull, 'w')
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = devnull
        sys.stderr = devnull
        try:
            log_error("Pre-loading IndicTranscriber (startup)...")
            transcriber = IndicTranscriber()
            log_error("Pre-loading IndicTranscriber: SUCCESS.")
            _warm_up_transcriber(transcriber)
            return transcriber
        except Exception as e:
            log_error(f"Pre-loading IndicTranscriber FAILED: {e}")
            return None
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            devnull.close()


def _warm_up_transcriber(transcriber):
    """Run one silent inference to force lazy initialization at startup."""
    try:
        silence = b'\x00\x00' * 16000
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tf:
            temp_path = tf.name
        try:
            with wave.open(temp_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(silence)

            log_error("Running warm-up inference...")
            transcriber.transcribe_rnnt(temp_path, "as")
            log_error("Warm-up inference: SUCCESS.")
        finally:
            try:
                os.remove(temp_path)
            except Exception:
                pass
    except Exception as e:
        log_error(f"Warm-up inference FAILED (non-fatal): {e}")