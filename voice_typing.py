import time
import os
import sys
import tempfile
import wave
import traceback
import array
import sounddevice as sd
import numpy as np
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
# Voice Recorder (Powered by sounddevice for PipeWire compatibility)
# ==================================================================
class VoiceRecorderWorker(QThread):
    recording_started = Signal()
    recording_stopped = Signal(str)
    error = Signal(str)
    level_update = Signal(float)

    def __init__(self, max_duration=24):
        super().__init__()
        self.max_duration = max_duration
        self._stop_requested = False
        self.actual_rate = 16000
        self.frames = None
        self.start_time = None

    def run(self):
        try:
            # --- FALLBACK LOGIC FOR NEWER UBUNTU (PIPEWIRE) ---
            try:
                # Try to use 16000 Hz
                sd.check_input_settings(samplerate=16000, channels=1)
                self.actual_rate = 16000
            except Exception:
                log_error("16000 Hz not supported by default mic. Falling back to device default.")
                device_info = sd.query_devices(kind='input')
                self.actual_rate = int(device_info['default_samplerate'])
            # ---------------------------------------------------

            log_error(f"Recording started at {self.actual_rate} Hz via sounddevice.")
            self.start_time = time.time()
            self._stop_requested = False
            
            self.recording_started.emit()

            # Start recording in the background
            self.frames = sd.rec(
                int(self.max_duration * self.actual_rate),
                samplerate=self.actual_rate,
                channels=1,
                dtype='int16',
                blocking=False
            )

            # Wait loop (handles stop request and updates UI level)
            while not self._stop_requested:
                elapsed = time.time() - self.start_time
                if elapsed >= self.max_duration:
                    break
                
                # Update level meter
                try:
                    current_sample = int(elapsed * self.actual_rate)
                    start_sample = max(0, current_sample - int(self.actual_rate * 0.1))
                    chunk = self.frames[start_sample:current_sample]
                    
                    if len(chunk) > 0:
                        # Flatten the chunk just in case, and cast to float32 for the math
                        chunk = chunk.flatten().astype(np.float32)
                        rms = np.sqrt(np.mean(chunk**2))
                        raw = rms / 32767.0
                        boosted = min(raw * 8.0, 1.0)
                        normalized = boosted ** 0.5
                        self.level_update.emit(normalized)
                except Exception:
                    pass
                time.sleep(0.1)

            # Stop the stream
            sd.stop()

            # Trim audio based on actual recorded time
            actual_samples = int((time.time() - self.start_time) * self.actual_rate)
            if actual_samples < len(self.frames):
                self.frames = self.frames[:actual_samples]
                
            # CRITICAL: Flatten the 2D array (samples, channels) into a 1D array
            self.frames = self.frames.flatten()

            if len(self.frames) > 0:
                # Save to a permanent location in the Home folder for debugging
                debug_filename = os.path.join(os.path.expanduser('~'), 'Sahaj_debug_raw.wav')
                import soundfile as sf
                sf.write(debug_filename, self.frames, self.actual_rate)
                
                log_error(f"DEBUG: Raw recording saved to {debug_filename}")
                self.recording_stopped.emit(debug_filename)
            else:
                self.error.emit("No audio recorded.")

        except Exception as e:
            error_msg = f"Recording error: {str(e)}\n{traceback.format_exc()}"
            log_error(error_msg)
            self.error.emit(error_msg)

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
                    
                    data, samplerate = sf.read(self.audio_filepath, dtype='float32', always_2d=False)
                    
                    if samplerate != 16000:
                        tensor = torch.from_numpy(data).float()
                        resampled = torchaudio.functional.resample(tensor, orig_freq=samplerate, new_freq=16000)
                        data_16k = resampled.numpy()
                        sf.write(resampled_path, data_16k, 16000, subtype='PCM_16')
                        process_path = resampled_path
                        log_error(f"Audio successfully resampled from {samplerate} to 16000 Hz.")
                    else:
                        log_error("Audio is already 16000 Hz, no resampling needed.")
                except Exception as e:
                    log_error(f"Resampling failed, using original audio: {e}")

                # --- MANUAL SMART CHUNKING (Bypassing the internal 15s VAD limit) ---
                log_error("Starting manual smart chunking...")
                
                # Read the 16kHz audio
                audio_data, sr = sf.read(process_path, dtype='int16')
                
                # Add 0.5s of silence to the end to prevent auto-stop hallucination
                audio_data = np.pad(audio_data, (0, 8000), 'constant')
                
                # We chunk into 8-second pieces with a huge 3-second overlap.
                # 8s ensures we stay safely under the AI's internal 15s limit.
                # 3s overlap gives the AI plenty of context to stitch cut words.
                CHUNK_DURATION = 8 
                OVERLAP = 3         
                CHUNK_SAMPLES = CHUNK_DURATION * 16000
                OVERLAP_SAMPLES = OVERLAP * 16000
                
                transcripts = []
                start_idx = 0
                
                while start_idx < len(audio_data):
                    end_idx = min(start_idx + CHUNK_SAMPLES, len(audio_data))
                    chunk = audio_data[start_idx:end_idx]
                    
                    # Save chunk to temp file
                    tmp_chunk = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                    tmp_path = tmp_chunk.name
                    tmp_chunk.close()
                    
                    with wave.open(tmp_path, 'wb') as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(chunk.tobytes())
                        
                    # Transcribe the chunk
                    text = transcriber.transcribe_rnnt(tmp_path, "as")
                    if text and text.strip():
                        transcripts.append(text.strip())
                        
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
                        
                    # Move start index forward by (chunk size - overlap)
                    start_idx += (CHUNK_SAMPLES - OVERLAP_SAMPLES)

                # --- SMART MERGE (Fuzzy Character Overlap) ---
                if not transcripts:
                    self.error.emit("Could not understand the audio. Please try again with clearer speech.")
                    return
                    
                final_text = transcripts[0]
                for i in range(1, len(transcripts)):
                    prev_text = final_text
                    curr_text = transcripts[i]
                    
                    # Find the longest overlap by checking characters
                    max_overlap_len = 0
                    # We check backwards from the end of prev_text (up to 40 characters)
                    for length in range(1, min(len(prev_text), len(curr_text), 40) + 1):
                        if prev_text[-length:] == curr_text[:length]:
                            max_overlap_len = length
                            
                    # If we found a solid overlap (at least 3 characters to avoid false positives)
                    if max_overlap_len >= 3:
                        final_text += curr_text[max_overlap_len:]
                    else:
                        # Fallback to word matching if characters didn't align exactly
                        prev_words = prev_text.split()
                        curr_words = curr_text.split()
                        max_word_overlap = 0
                        for j in range(1, min(len(prev_words), len(curr_words), 10) + 1):
                            if prev_words[-j:] == curr_words[:j]:
                                max_word_overlap = j
                        final_text += " " + " ".join(curr_words[max_word_overlap:])

                log_error("Transcription complete.")
                self.finished.emit(final_text.strip())

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