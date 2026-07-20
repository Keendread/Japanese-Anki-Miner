from PySide6.QtCore import QObject, Signal


class _AppSignals(QObject):
    # ── Dispatch ────────────────────────────────────────────────────────────
    run_on_main_thread = Signal(object)

    # ── Toasts ──────────────────────────────────────────────────────────────
    show_loading   = Signal(object, object, object, object)  # ocr_event, parser_event, dict_event, on_all_ready
    show_ready     = Signal()
    show_card      = Signal(object, object, object, object)  # word, settings, on_confirm, on_discard
    show_success   = Signal(str)                              # surface
    show_duplicate = Signal(str, str)                         # surface, reading

    # ── Overlays / windows ─────────────────────────────────────────────────
    show_settings       = Signal(object, object)  # settings, capture
    show_word_selector  = Signal(object, object, object)  # entries, on_confirm, settings


# Singleton — import and use directly: `from core.signals import signals`
signals = _AppSignals()