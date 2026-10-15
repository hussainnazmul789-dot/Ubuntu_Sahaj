"""app_voice_mixin.py — Voice typing methods as a mixin."""
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import QTimer

import app_utils


class VoiceMixin:
    """Voice typing methods. Assumes host class has: voice_btn,
    voice_progress, voice_timer_label, text_area, countdown_timer,
    remaining_seconds, recording_worker, asr_transcriber,
    transcriber_thread, _track_worker."""

    def start_voice_typing(self):
        if not hasattr(self, 'recording_worker') or self.recording_worker is None:
            try:
                self.voice_btn.setEnabled(False)
                self.voice_btn.setText("⏹️ Recording...")
                self.remaining_seconds = 24
                self.voice_progress.setValue(100)
                self.voice_progress.show()
                self.voice_timer_label.setText("24s")
                self.voice_timer_label.show()
                self.recording_worker = app_utils.voice_typing.VoiceRecorderWorker(
                    max_duration=24
                )
                self.recording_worker.recording_started.connect(self.on_recording_started)
                self.recording_worker.recording_stopped.connect(self.on_recording_stopped)
                self.recording_worker.error.connect(self.on_voice_error)
                self.recording_worker.level_update.connect(self.update_voice_level)
                self.recording_worker.start()
                self.countdown_timer.start()

            except Exception as e:
                import traceback
                error_msg = f"start_voice_typing error: {e}\n{traceback.format_exc()}"
                print(error_msg)
                self.on_voice_error(error_msg)
        else:
            if self.recording_worker:
                self.recording_worker.stop()
                self.voice_btn.setEnabled(False)
                self.voice_btn.setText("⏹️ Stopping...")
                self.countdown_timer.stop()

    def on_recording_started(self):
        self.voice_btn.setEnabled(True)
        self.voice_btn.setText("⏹️ Stop")

    def on_recording_stopped(self, audio_filepath):
        self.countdown_timer.stop()
        self.voice_timer_label.hide()
        self.voice_progress.setValue(100)
        self.voice_progress.hide()
        self.voice_btn.setEnabled(False)
        self.voice_btn.setText("⏳ Transcribing...")

        old_recorder = self.recording_worker
        self.recording_worker = None
        if old_recorder is not None:
            self._track_worker(old_recorder)

        worker = app_utils.voice_typing.VoiceTypingWorker(
            audio_filepath,
            transcriber=self.asr_transcriber,
        )
        worker.finished.connect(self.on_voice_transcribed)
        worker.error.connect(self.on_voice_error)
        self._track_worker(worker)
        self.transcriber_thread = worker
        worker.start()

    def on_voice_transcribed(self, text):
        self.voice_progress.hide()
        self.voice_progress.setValue(100)
        if text and text.strip():
            self.text_area.insertPlainText(text + " ")
            self.text_area.setFocus()
            cursor = self.text_area.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.text_area.setTextCursor(cursor)
        self.voice_btn.setEnabled(True)
        self.voice_btn.setText("🎤 Voice Typing")
        self.transcriber_thread = None

    def on_voice_error(self, error_message):
        self.countdown_timer.stop()
        self.voice_timer_label.hide()
        self.voice_progress.hide()
        self.voice_progress.setValue(100)
        QMessageBox.critical(self, "Voice Typing Error", error_message)
        self.voice_btn.setEnabled(True)
        self.voice_btn.setText("🎤 Voice Typing")
        self.recording_worker = None
        self.transcriber_thread = None

    def update_countdown(self):
        self.remaining_seconds -= 1
        self.voice_timer_label.setText(f"{self.remaining_seconds}s")
        if self.remaining_seconds <= 0:
            self.countdown_timer.stop()
            self.voice_timer_label.hide()
            self.voice_progress.hide()
            if self.recording_worker:
                self.recording_worker.stop()
                self.voice_btn.setEnabled(False)
                self.voice_btn.setText("⏹️ Stopping...")

    def update_voice_level(self, rms):
        if self.voice_progress.isVisible():
            value = int(rms * 100)
            self.voice_progress.setValue(value)
        else:
            self.voice_progress.show()
            self.voice_progress.setValue(0)