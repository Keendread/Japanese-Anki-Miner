from __future__ import annotations

import logging
import threading

from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QComboBox, QFileDialog,
    QMessageBox, QVBoxLayout, QHBoxLayout, QFormLayout, QFrame,
    QScrollArea, QApplication,
)
from PySide6.QtCore import Qt, Signal

from core.settings import DEFAULT_SETTINGS
from core.signals import signals


_current_window: "SettingsWindow" = None


class SettingsWindow(QWidget):
    _hotkey_recorded        = Signal(object)   # display: str | None
    _record_hotkey_recorded = Signal(object)   # display: str | None
    _save_succeeded          = Signal()
    _save_failed              = Signal(str)

    def __init__(self, settings, capture=None) -> None:
        super().__init__()
        self.settings = settings
        self._capture = capture
        self._recording_hotkey = False
        self._recording_record_hotkey = False

        self._hotkey_recorded.connect(self._finish_hotkey_recording)
        self._record_hotkey_recorded.connect(self._finish_record_hotkey_recording)
        self._save_succeeded.connect(self._on_save_success)
        self._save_failed.connect(self._on_save_error)

        self.setWindowTitle("JAM Settings")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.resize(520, 480)

        self._build_ui()
        logging.info("[Settings] Window built")

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        outer.addWidget(scroll)

        inner = QWidget()
        form = QFormLayout(inner)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)
        scroll.setWidget(inner)

        # ── Capture Hotkey ──
        combo_display = " + ".join(self.settings.get("capture_combo", DEFAULT_SETTINGS["capture_combo"]))
        self._hotkey_btn = QPushButton(combo_display or "Click to set hotkey")
        self._hotkey_btn.setCursor(Qt.PointingHandCursor)
        self._hotkey_btn.clicked.connect(self._start_hotkey_recording)
        form.addRow("Capture Hotkey:", self._hotkey_btn)

        # ── Capture Mode ──
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["bbox", "screen"])
        self._mode_combo.setCurrentText(self.settings.get("capture_mode", "bbox"))
        form.addRow("Capture Mode:", self._mode_combo)

        # ── Record Hotkey ──
        record_display = " + ".join(self.settings.get("record_combo", DEFAULT_SETTINGS["record_combo"]))
        self._record_hotkey_btn = QPushButton(record_display or "Click to set hotkey")
        self._record_hotkey_btn.setCursor(Qt.PointingHandCursor)
        self._record_hotkey_btn.clicked.connect(self._start_record_hotkey_recording)
        form.addRow("Record Hotkey:", self._record_hotkey_btn)

        form.addRow(self._separator())

        # ── VOICEVOX Voice ──
        from core.audio import VOICEVOX_SPEAKERS
        self._speaker_options = VOICEVOX_SPEAKERS
        speaker_display = [f"{s['english']} ({s['japanese']})" for s in self._speaker_options]
        current_id = self.settings.get("voicevox_speaker_id", 3)
        current_idx = next(
            (i for i, s in enumerate(self._speaker_options) if s["id"] == current_id), 0
        )

        voice_row = QHBoxLayout()
        self._voice_combo = QComboBox()
        self._voice_combo.addItems(speaker_display)
        self._voice_combo.setCurrentIndex(current_idx)
        voice_row.addWidget(self._voice_combo, stretch=1)

        preview_btn = QPushButton("▶ Preview")
        preview_btn.setCursor(Qt.PointingHandCursor)
        preview_btn.clicked.connect(self._preview_voice)
        voice_row.addWidget(preview_btn)

        form.addRow("VOICEVOX Voice:", voice_row)

        form.addRow(self._separator())

        # ── Anki fields ──
        self._deck_edit = QLineEdit(self.settings.get("anki_deck", DEFAULT_SETTINGS["anki_deck"]))
        form.addRow("Anki Deck:", self._deck_edit)

        self._note_type_edit = QLineEdit(self.settings.get("anki_note_type", DEFAULT_SETTINGS["anki_note_type"]))
        form.addRow("Anki Note Type:", self._note_type_edit)

        media_row = QHBoxLayout()
        self._media_path_edit = QLineEdit(self.settings.get("anki_media_path", DEFAULT_SETTINGS["anki_media_path"]))
        media_row.addWidget(self._media_path_edit, stretch=1)
        browse_btn = QPushButton("Browse")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.clicked.connect(self._browse_media_path)
        media_row.addWidget(browse_btn)
        form.addRow("Anki Media Path:", media_row)

        self._misc_info_edit = QLineEdit(self.settings.get("anki_misc_info", DEFAULT_SETTINGS["anki_misc_info"]))
        form.addRow("Anki Misc Info:", self._misc_info_edit)

        self._profile_edit = QLineEdit(self.settings.get("anki_profile", DEFAULT_SETTINGS["anki_profile"]))
        form.addRow("Anki Profile:", self._profile_edit)

        form.addRow(self._separator())

        note = QLabel("Click the hotkey button, then press and hold your desired key combo.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #888888; font-size: 10px;")
        form.addRow(note)

        # ── Buttons ──
        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.close)
        btn_row.addWidget(cancel_btn)

        reset_btn = QPushButton("Reset Defaults")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_defaults)
        btn_row.addWidget(reset_btn)

        form.addRow(btn_row)

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #444444;")
        return line

    # ── Hotkey recording ───────────────────────────────────────────────────────

    def _start_hotkey_recording(self) -> None:
        if self._recording_hotkey:
            return
        self._recording_hotkey = True
        self._hotkey_btn.setEnabled(False)
        self._hotkey_btn.setText("Press keys…")

        if self._capture:
            self._capture.set_recording(True)   # pause old hotkey while recording new one

        def _record():
            try:
                result = self.settings.set_combo_from_recording()
                display = " + ".join(sorted(result["names"]))
            except Exception as e:
                logging.error(f"[Settings] Hotkey recording failed: {e}", exc_info=True)
                display = None
            self._hotkey_recorded.emit(display)

        threading.Thread(target=_record, daemon=True, name="jam-hotkey-record").start()

    def _finish_hotkey_recording(self, display: str | None) -> None:
        self._recording_hotkey = False
        self._hotkey_btn.setEnabled(True)
        if self._capture:
            self._capture.set_recording(False)

        if display:
            self._hotkey_btn.setText(display)
        else:
            current = " + ".join(self.settings.get("capture_combo", []))
            self._hotkey_btn.setText(current or "Click to set hotkey")

    def _start_record_hotkey_recording(self) -> None:
        if self._recording_record_hotkey:
            return
        self._recording_record_hotkey = True
        self._record_hotkey_btn.setEnabled(False)
        self._record_hotkey_btn.setText("Press keys…")

        def _record():
            try:
                result = self.settings.set_record_combo_from_recording()
                display = " + ".join(sorted(result["names"]))
            except Exception as e:
                logging.error(f"[Settings] Record hotkey recording failed: {e}", exc_info=True)
                display = None
            self._record_hotkey_recorded.emit(display)

        threading.Thread(target=_record, daemon=True, name="jam-record-hotkey-record").start()

    def _finish_record_hotkey_recording(self, display: str | None) -> None:
        self._recording_record_hotkey = False
        self._record_hotkey_btn.setEnabled(True)

        if display:
            self._record_hotkey_btn.setText(display)
        else:
            current = " + ".join(self.settings.get("record_combo", []))
            self._record_hotkey_btn.setText(current or "Click to set hotkey")

    # ── Field actions ──────────────────────────────────────────────────────────

    def _browse_media_path(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Select Anki media folder",
            self._media_path_edit.text() or "",
        )
        if directory:
            self._media_path_edit.setText(directory)

    def _preview_voice(self) -> None:
        selected = self._voice_combo.currentText()
        speaker = next(
            (s for s in self._speaker_options
             if f"{s['english']} ({s['japanese']})" == selected),
            None
        )
        if speaker is None:
            return
        speaker_id = speaker["id"]

        def _play():
            try:
                import asyncio, winsound, tempfile, os
                from core.audio import preview_speaker
                audio_bytes = asyncio.run(preview_speaker(speaker_id))
                if audio_bytes is None:
                    print("[Settings] Preview failed — is VOICEVOX running?")
                    return
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(audio_bytes)
                    tmp_path = f.name
                winsound.PlaySound(tmp_path, winsound.SND_FILENAME)
                os.unlink(tmp_path)
            except Exception as e:
                print(f"[Settings] Voice preview error: {e}")

        threading.Thread(target=_play, daemon=True).start()

    # ── Save / Reset ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            selected_voice = self._voice_combo.currentText()
            speaker = next(
                (s for s in self._speaker_options
                 if f"{s['english']} ({s['japanese']})" == selected_voice),
                None
            )

            updated = {
                "capture_mode":       self._mode_combo.currentText(),
                "anki_deck":          self._deck_edit.text().strip(),
                "anki_note_type":     self._note_type_edit.text().strip(),
                "anki_misc_info":     self._misc_info_edit.text().strip(),
                "anki_media_path":    self._media_path_edit.text().strip(),
                "anki_profile":       self._profile_edit.text().strip(),
                "voicevox_speaker_id": speaker["id"] if speaker else 3,
            }

            def save_in_background():
                try:
                    for key, value in updated.items():
                        self.settings.set(key, value)
                    logging.info("[Settings] Settings saved successfully")
                    self._save_succeeded.emit()
                except Exception as e:
                    logging.error(f"[Settings] Background save failed: {e}", exc_info=True)
                    self._save_failed.emit(str(e))

            threading.Thread(target=save_in_background, daemon=True).start()

        except Exception as exc:
            logging.error(f"[Settings] Save failed: {exc}", exc_info=True)
            QMessageBox.critical(self, "Error saving settings", str(exc))

    def _on_save_success(self) -> None:
        QMessageBox.information(self, "JAM Settings", "Settings saved successfully.")
        self.close()

    def _on_save_error(self, message: str) -> None:
        QMessageBox.critical(self, "Error saving settings", message)

    def _reset_defaults(self) -> None:
        self._mode_combo.setCurrentText(DEFAULT_SETTINGS.get("capture_mode", "bbox"))
        self._deck_edit.setText(DEFAULT_SETTINGS.get("anki_deck", ""))
        self._note_type_edit.setText(DEFAULT_SETTINGS.get("anki_note_type", ""))
        self._misc_info_edit.setText(DEFAULT_SETTINGS.get("anki_misc_info", ""))
        self._media_path_edit.setText(DEFAULT_SETTINGS.get("anki_media_path", ""))
        self._profile_edit.setText(DEFAULT_SETTINGS.get("anki_profile", ""))

        default_combo = DEFAULT_SETTINGS.get("capture_combo", [])
        self._hotkey_btn.setText(" + ".join(default_combo) or "Click to set hotkey")

        default_record_combo = DEFAULT_SETTINGS.get("record_combo", [])
        self._record_hotkey_btn.setText(" + ".join(default_record_combo) or "Click to set hotkey")

    # ── Close ──────────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        global _current_window
        _current_window = None
        event.accept()


# ── Public API ─────────────────────────────────────────────────────────────────

def show_settings_window(settings, main_thread_queue=None, capture=None) -> None:
    logging.info("[Settings] show_settings_window() called")
    signals.show_settings.emit(settings, capture)


def _on_show_settings(settings, capture) -> None:
    global _current_window
    if _current_window is not None:
        logging.info("[Settings] Existing window found, raising it")
        _current_window.raise_()
        _current_window.activateWindow()
        return

    logging.info("[Settings] Creating new SettingsWindow")
    _current_window = SettingsWindow(settings, capture=capture)
    _current_window.show()


def connect_settings_window_signal() -> None:
    signals.show_settings.connect(_on_show_settings)