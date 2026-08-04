"""Static translations for the UI — English, Spanish, Portuguese, German.

Not a dynamic i18n framework: every string lives in the TRANSLATIONS dict
below, keyed by a short id. tr(key) looks it up in the active language and
falls back to English (then to the key itself) if missing.
"""
from __future__ import annotations

import locale

_SUPPORTED = ("en", "es", "pt", "de")
_DEFAULT = "en"

_active_language = _DEFAULT


def detect_system_language() -> str:
    """Best-effort guess from the OS locale. Falls back to English."""
    try:
        lang_code = locale.getlocale()[0] or locale.getdefaultlocale()[0]
    except Exception:
        lang_code = None
    if not lang_code:
        return _DEFAULT
    lang_code = lang_code.lower()
    for code in _SUPPORTED:
        if lang_code.startswith(code):
            return code
    return _DEFAULT


def set_language(code: str) -> None:
    global _active_language
    _active_language = code if code in _SUPPORTED else _DEFAULT


def get_language() -> str:
    return _active_language


def available_languages() -> tuple[str, ...]:
    return _SUPPORTED


def tr(key: str) -> str:
    table = TRANSLATIONS.get(_active_language, {})
    if key in table:
        return table[key]
    en_table = TRANSLATIONS.get("en", {})
    return en_table.get(key, key)


# ---------------------------------------------------------------------------
# Translation table
# ---------------------------------------------------------------------------

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Language names (shown in the picker regardless of active language)
        "lang_en": "English",
        "lang_es": "Español",
        "lang_pt": "Português",
        "lang_de": "Deutsch",

        # Window / menu
        "window_title": "Image Selector",
        "menu_file": "File",
        "menu_change_library": "Change Library Folder…",
        "menu_change_album": "Change Album Folder…",
        "menu_language": "Language",
        "restart_required": "Language changed. Restart Image Selector for it to take effect.",

        # Folder dialogs
        "select_library_folder": "Select Library Folder",
        "select_album_folder": "Select Album Folder",
        "check_4r": "4R (3:2 / 2:3)",
        "check_instax": "Instax Mini (4:3 / 3:4)",
        "check_run_btn": "Check",
        "check_clear_btn": "Clear",
        "check_status_none": "No print check",
        "check_status_pass": "{name}: all print-ready ✓",
        "check_status_fail": "{name}: {count} to crop",
        "tooltip_album_check": "Mark album photos that aren't sized for the selected print (either orientation is fine)",
        "library_label": "Library: {path}",
        "album_label": "Album: {path}",
        "change_btn": "Change…",
        "tooltip_change_library": "Select a different library folder",
        "tooltip_change_album": "Select a different album folder",

        # Triage strips
        "library_strip_title": "LIBRARY",
        "album_strip_title": "ALBUM",

        # Action bar
        "btn_prev": "← Prev",
        "btn_next": "→ Next",
        "btn_to_album": "↑ To Album",
        "btn_to_library": "↓ To Library",
        "btn_copy_mode": "⧉ Copy",
        "btn_edit": "✏ Edit",
        "btn_rotate": "↻ Rotate",
        "btn_undo": "⟲ Undo",
        "btn_delete": "🗑 Delete",
        "tooltip_left_arrow": "Left arrow",
        "tooltip_right_arrow": "Right arrow",
        "tooltip_to_album": "Up arrow — move to album",
        "tooltip_to_library": "Down arrow — move to library",
        "tooltip_copy_mode": "When on, To Album / To Library copy the file instead of moving it",
        "tooltip_edit": "E — open edit mode",
        "tooltip_rotate": "R — rotate 90° clockwise",
        "tooltip_undo": "Ctrl+Z",
        "tooltip_delete": "Del — send to trash",

        # Info bar
        "no_image": "No image",
        "no_images": "No images",
        "no_date": "No date",

        # Errors / dialogs
        "save_failed_title": "Save failed",
        "save_failed_body": "Could not save image:\n{error}",
        "rotate_failed_title": "Rotate failed",
        "rotate_failed_body": "Could not rotate image:\n{error}",

        # Edit panel — header
        "back_btn": "← Back",
        "crop_btn": "Crop",
        "apply_crop_btn": "✓ Apply Crop",
        "crop_ratio_original": "Original",
        "crop_ratio_4r_land": "4R Landscape (3:2)",
        "crop_ratio_4r_port": "4R Portrait (2:3)",
        "crop_ratio_instax_land": "Instax Mini Landscape (4:3)",
        "crop_ratio_instax_port": "Instax Mini Portrait (3:4)",
        "tooltip_crop_ratio": "Crop aspect ratio (4R = 4×6\" print)",
        "rotate_left_btn": "↺ Rotate L",
        "rotate_right_btn": "↻ Rotate R",
        "save_as_btn": "Save As…",
        "tooltip_rotate_left": "Rotate 90° counter-clockwise",
        "tooltip_rotate_right": "Rotate 90° clockwise",

        # Adjustments panel
        "adjustments_title": "ADJUSTMENTS",
        "brightness": "Brightness",
        "contrast": "Contrast",
        "exposure": "Exposure",
        "saturation": "Saturation",
        "shadows": "Shadows",
        "highlights": "Highlights",
        "reset_btn": "Reset",

        # Filters panel
        "filters_title": "FILTERS",
        "manage_btn": "⚙ Manage",
        "auto_adjustments_title": "AUTO ADJUSTMENTS",
        "film_simulations_title": "FILM SIMULATIONS",
        "manage_filters_title": "Manage Filters",
        "select_all_btn": "Select All",
        "clear_all_btn": "Clear All",
        "ok_btn": "OK",
        "cancel_btn": "Cancel",

        # Filter names
        "filter_original": "Original",
        "filter_provia": "Provia",
        "filter_velvia": "Velvia",
        "filter_astia": "Astia",
        "filter_classic_chrome": "Classic Chrome",
        "filter_classic_neg": "Classic Neg",
        "filter_acros": "Acros",
        "filter_eterna": "Eterna",
        "filter_sepia": "Sepia",
        "filter_faded": "Faded / Matte",
        "filter_cross_process": "Cross Process",
        "filter_fortia_sp": "Fortia SP",
        "filter_neopan_1600": "Neopan 1600",
        "filter_t64": "T64 (Tungsten)",
        "filter_pro_800z": "Pro 800Z",
        "filter_pro_400h": "Pro 400H",
        "filter_pro_160c": "Pro 160C",
        "filter_pro_160s": "Pro 160S",
        "filter_superia_1600": "Superia 1600",
        "filter_superia_400": "Superia 400",
        "filter_superia_100": "Superia 100",
        "filter_normalize": "Normalize (CLAHE)",
        "filter_auto_levels": "Auto Levels",
        "filter_auto_tone": "Auto Tone",
        "filter_auto_wb": "Auto White Balance",

        # AI edit
        "ai_edit_title": "AI EDIT",
        "ai_prompt_placeholder": "describe the look you want…",
        "ai_apply_btn": "✨ Apply",
        "ai_undo_btn": "↩ Undo AI",
        "ai_thinking": "Thinking…",
        "ai_applied": "Applied ✓",
        "ai_undone": "Undone",
        "ai_backend_anthropic": "via Claude (Anthropic)",
        "ai_backend_ollama": "via Ollama ({model})",
        "ai_backend_none": "No AI backend found — set ANTHROPIC_API_KEY or start Ollama",

        # Save As dialog
        "save_as_title": "Save As",
        "images_filter": "Images (*.jpg *.jpeg *.png *.tiff *.tif)",
    },
    "es": {
        "lang_en": "English",
        "lang_es": "Español",
        "lang_pt": "Português",
        "lang_de": "Deutsch",

        "window_title": "Selector de Imágenes",
        "menu_file": "Archivo",
        "menu_change_library": "Cambiar carpeta de biblioteca…",
        "menu_change_album": "Cambiar carpeta de álbum…",
        "menu_language": "Idioma",
        "restart_required": "Idioma cambiado. Reinicia Image Selector para que tenga efecto.",

        "select_library_folder": "Selecciona la carpeta de biblioteca",
        "select_album_folder": "Selecciona la carpeta de álbum",
        "check_4r": "4R (3:2 / 2:3)",
        "check_instax": "Instax Mini (4:3 / 3:4)",
        "check_run_btn": "Comprobar",
        "check_clear_btn": "Limpiar",
        "check_status_none": "Sin comprobación de impresión",
        "check_status_pass": "{name}: listas para imprimir ✓",
        "check_status_fail": "{name}: {count} por recortar",
        "tooltip_album_check": "Marca las fotos del álbum que no tienen el tamaño de la impresión seleccionada (cualquier orientación vale)",
        "library_label": "Biblioteca: {path}",
        "album_label": "Álbum: {path}",
        "change_btn": "Cambiar…",
        "tooltip_change_library": "Selecciona una carpeta de biblioteca distinta",
        "tooltip_change_album": "Selecciona una carpeta de álbum distinta",

        "library_strip_title": "BIBLIOTECA",
        "album_strip_title": "ÁLBUM",

        "btn_prev": "← Anterior",
        "btn_next": "→ Siguiente",
        "btn_to_album": "↑ Al álbum",
        "btn_to_library": "↓ A la biblioteca",
        "btn_copy_mode": "⧉ Copiar",
        "btn_edit": "✏ Editar",
        "btn_rotate": "↻ Rotar",
        "btn_undo": "⟲ Deshacer",
        "btn_delete": "🗑 Eliminar",
        "tooltip_left_arrow": "Flecha izquierda",
        "tooltip_right_arrow": "Flecha derecha",
        "tooltip_to_album": "Flecha arriba — mover al álbum",
        "tooltip_to_library": "Flecha abajo — mover a la biblioteca",
        "tooltip_copy_mode": "Cuando está activo, A la biblioteca / Al álbum copian el archivo en vez de moverlo",
        "tooltip_edit": "E — abrir modo de edición",
        "tooltip_rotate": "R — rotar 90° en sentido horario",
        "tooltip_undo": "Ctrl+Z",
        "tooltip_delete": "Supr — enviar a la papelera",

        "no_image": "Sin imagen",
        "no_images": "Sin imágenes",
        "no_date": "Sin fecha",

        "save_failed_title": "Error al guardar",
        "save_failed_body": "No se pudo guardar la imagen:\n{error}",
        "rotate_failed_title": "Error al rotar",
        "rotate_failed_body": "No se pudo rotar la imagen:\n{error}",

        "back_btn": "← Volver",
        "crop_btn": "Recortar",
        "apply_crop_btn": "✓ Aplicar recorte",
        "crop_ratio_original": "Original",
        "crop_ratio_4r_land": "4R Horizontal (3:2)",
        "crop_ratio_4r_port": "4R Vertical (2:3)",
        "crop_ratio_instax_land": "Instax Mini Horizontal (4:3)",
        "crop_ratio_instax_port": "Instax Mini Vertical (3:4)",
        "tooltip_crop_ratio": "Relación de aspecto del recorte (4R = impresión 4×6\")",
        "rotate_left_btn": "↺ Rotar izq.",
        "rotate_right_btn": "↻ Rotar der.",
        "save_as_btn": "Guardar como…",
        "tooltip_rotate_left": "Rotar 90° en sentido antihorario",
        "tooltip_rotate_right": "Rotar 90° en sentido horario",

        "adjustments_title": "AJUSTES",
        "brightness": "Brillo",
        "contrast": "Contraste",
        "exposure": "Exposición",
        "saturation": "Saturación",
        "shadows": "Sombras",
        "highlights": "Altas luces",
        "reset_btn": "Restablecer",

        "filters_title": "FILTROS",
        "manage_btn": "⚙ Administrar",
        "auto_adjustments_title": "AJUSTES AUTOMÁTICOS",
        "film_simulations_title": "SIMULACIONES DE PELÍCULA",
        "manage_filters_title": "Administrar filtros",
        "select_all_btn": "Seleccionar todo",
        "clear_all_btn": "Deseleccionar todo",
        "ok_btn": "Aceptar",
        "cancel_btn": "Cancelar",

        "filter_original": "Original",
        "filter_provia": "Provia",
        "filter_velvia": "Velvia",
        "filter_astia": "Astia",
        "filter_classic_chrome": "Classic Chrome",
        "filter_classic_neg": "Classic Neg",
        "filter_acros": "Acros",
        "filter_eterna": "Eterna",
        "filter_sepia": "Sepia",
        "filter_faded": "Desvanecido / Mate",
        "filter_cross_process": "Cross Process",
        "filter_fortia_sp": "Fortia SP",
        "filter_neopan_1600": "Neopan 1600",
        "filter_t64": "T64 (Tungsteno)",
        "filter_pro_800z": "Pro 800Z",
        "filter_pro_400h": "Pro 400H",
        "filter_pro_160c": "Pro 160C",
        "filter_pro_160s": "Pro 160S",
        "filter_superia_1600": "Superia 1600",
        "filter_superia_400": "Superia 400",
        "filter_superia_100": "Superia 100",
        "filter_normalize": "Normalizar (CLAHE)",
        "filter_auto_levels": "Niveles automáticos",
        "filter_auto_tone": "Tono automático",
        "filter_auto_wb": "Balance de blancos automático",

        "ai_edit_title": "EDICIÓN CON IA",
        "ai_prompt_placeholder": "describe el estilo que quieres…",
        "ai_apply_btn": "✨ Aplicar",
        "ai_undo_btn": "↩ Deshacer IA",
        "ai_thinking": "Pensando…",
        "ai_applied": "Aplicado ✓",
        "ai_undone": "Deshecho",
        "ai_backend_anthropic": "vía Claude (Anthropic)",
        "ai_backend_ollama": "vía Ollama ({model})",
        "ai_backend_none": "No se encontró backend de IA — configura ANTHROPIC_API_KEY o inicia Ollama",

        "save_as_title": "Guardar como",
        "images_filter": "Imágenes (*.jpg *.jpeg *.png *.tiff *.tif)",
    },
    "pt": {
        "lang_en": "English",
        "lang_es": "Español",
        "lang_pt": "Português",
        "lang_de": "Deutsch",

        "window_title": "Seletor de Imagens",
        "menu_file": "Arquivo",
        "menu_change_library": "Alterar pasta da biblioteca…",
        "menu_change_album": "Alterar pasta do álbum…",
        "menu_language": "Idioma",
        "restart_required": "Idioma alterado. Reinicie o Image Selector para aplicar.",

        "select_library_folder": "Selecione a pasta da biblioteca",
        "select_album_folder": "Selecione a pasta do álbum",
        "check_4r": "4R (3:2 / 2:3)",
        "check_instax": "Instax Mini (4:3 / 3:4)",
        "check_run_btn": "Verificar",
        "check_clear_btn": "Limpar",
        "check_status_none": "Sem verificação de impressão",
        "check_status_pass": "{name}: prontas para impressão ✓",
        "check_status_fail": "{name}: {count} para recortar",
        "tooltip_album_check": "Marca as fotos do álbum sem o tamanho da impressão selecionada (qualquer orientação serve)",
        "library_label": "Biblioteca: {path}",
        "album_label": "Álbum: {path}",
        "change_btn": "Alterar…",
        "tooltip_change_library": "Selecione uma pasta de biblioteca diferente",
        "tooltip_change_album": "Selecione uma pasta de álbum diferente",

        "library_strip_title": "BIBLIOTECA",
        "album_strip_title": "ÁLBUM",

        "btn_prev": "← Anterior",
        "btn_next": "→ Próxima",
        "btn_to_album": "↑ Para o álbum",
        "btn_to_library": "↓ Para a biblioteca",
        "btn_copy_mode": "⧉ Copiar",
        "btn_edit": "✏ Editar",
        "btn_rotate": "↻ Girar",
        "btn_undo": "⟲ Desfazer",
        "btn_delete": "🗑 Excluir",
        "tooltip_left_arrow": "Seta esquerda",
        "tooltip_right_arrow": "Seta direita",
        "tooltip_to_album": "Seta para cima — mover para o álbum",
        "tooltip_to_library": "Seta para baixo — mover para a biblioteca",
        "tooltip_copy_mode": "Quando ativo, Para o álbum / Para a biblioteca copiam o arquivo em vez de movê-lo",
        "tooltip_edit": "E — abrir modo de edição",
        "tooltip_rotate": "R — girar 90° no sentido horário",
        "tooltip_undo": "Ctrl+Z",
        "tooltip_delete": "Del — enviar para a lixeira",

        "no_image": "Sem imagem",
        "no_images": "Sem imagens",
        "no_date": "Sem data",

        "save_failed_title": "Falha ao salvar",
        "save_failed_body": "Não foi possível salvar a imagem:\n{error}",
        "rotate_failed_title": "Falha ao girar",
        "rotate_failed_body": "Não foi possível girar a imagem:\n{error}",

        "back_btn": "← Voltar",
        "crop_btn": "Cortar",
        "apply_crop_btn": "✓ Aplicar corte",
        "crop_ratio_original": "Original",
        "crop_ratio_4r_land": "4R Horizontal (3:2)",
        "crop_ratio_4r_port": "4R Vertical (2:3)",
        "crop_ratio_instax_land": "Instax Mini Horizontal (4:3)",
        "crop_ratio_instax_port": "Instax Mini Vertical (3:4)",
        "tooltip_crop_ratio": "Proporção do corte (4R = impressão 4×6\")",
        "rotate_left_btn": "↺ Girar à esq.",
        "rotate_right_btn": "↻ Girar à dir.",
        "save_as_btn": "Salvar como…",
        "tooltip_rotate_left": "Girar 90° no sentido anti-horário",
        "tooltip_rotate_right": "Girar 90° no sentido horário",

        "adjustments_title": "AJUSTES",
        "brightness": "Brilho",
        "contrast": "Contraste",
        "exposure": "Exposição",
        "saturation": "Saturação",
        "shadows": "Sombras",
        "highlights": "Realces",
        "reset_btn": "Redefinir",

        "filters_title": "FILTROS",
        "manage_btn": "⚙ Gerenciar",
        "auto_adjustments_title": "AJUSTES AUTOMÁTICOS",
        "film_simulations_title": "SIMULAÇÕES DE FILME",
        "manage_filters_title": "Gerenciar filtros",
        "select_all_btn": "Selecionar tudo",
        "clear_all_btn": "Limpar tudo",
        "ok_btn": "OK",
        "cancel_btn": "Cancelar",

        "filter_original": "Original",
        "filter_provia": "Provia",
        "filter_velvia": "Velvia",
        "filter_astia": "Astia",
        "filter_classic_chrome": "Classic Chrome",
        "filter_classic_neg": "Classic Neg",
        "filter_acros": "Acros",
        "filter_eterna": "Eterna",
        "filter_sepia": "Sépia",
        "filter_faded": "Desbotado / Fosco",
        "filter_cross_process": "Cross Process",
        "filter_fortia_sp": "Fortia SP",
        "filter_neopan_1600": "Neopan 1600",
        "filter_t64": "T64 (Tungstênio)",
        "filter_pro_800z": "Pro 800Z",
        "filter_pro_400h": "Pro 400H",
        "filter_pro_160c": "Pro 160C",
        "filter_pro_160s": "Pro 160S",
        "filter_superia_1600": "Superia 1600",
        "filter_superia_400": "Superia 400",
        "filter_superia_100": "Superia 100",
        "filter_normalize": "Normalizar (CLAHE)",
        "filter_auto_levels": "Níveis automáticos",
        "filter_auto_tone": "Tom automático",
        "filter_auto_wb": "Balanço de branco automático",

        "ai_edit_title": "EDIÇÃO COM IA",
        "ai_prompt_placeholder": "descreva o visual que você quer…",
        "ai_apply_btn": "✨ Aplicar",
        "ai_undo_btn": "↩ Desfazer IA",
        "ai_thinking": "Pensando…",
        "ai_applied": "Aplicado ✓",
        "ai_undone": "Desfeito",
        "ai_backend_anthropic": "via Claude (Anthropic)",
        "ai_backend_ollama": "via Ollama ({model})",
        "ai_backend_none": "Nenhum backend de IA encontrado — defina ANTHROPIC_API_KEY ou inicie o Ollama",

        "save_as_title": "Salvar como",
        "images_filter": "Imagens (*.jpg *.jpeg *.png *.tiff *.tif)",
    },
    "de": {
        "lang_en": "English",
        "lang_es": "Español",
        "lang_pt": "Português",
        "lang_de": "Deutsch",

        "window_title": "Image Selector",
        "menu_file": "Datei",
        "menu_change_library": "Bibliotheksordner ändern…",
        "menu_change_album": "Albumordner ändern…",
        "menu_language": "Sprache",
        "restart_required": "Sprache geändert. Image Selector neu starten, damit die Änderung wirksam wird.",

        "select_library_folder": "Bibliotheksordner auswählen",
        "select_album_folder": "Albumordner auswählen",
        "check_4r": "4R (3:2 / 2:3)",
        "check_instax": "Instax Mini (4:3 / 3:4)",
        "check_run_btn": "Prüfen",
        "check_clear_btn": "Löschen",
        "check_status_none": "Keine Druckprüfung",
        "check_status_pass": "{name}: alle druckfertig ✓",
        "check_status_fail": "{name}: {count} zuzuschneiden",
        "tooltip_album_check": "Markiert Albumfotos, die nicht das Format des gewählten Drucks haben (beide Ausrichtungen sind ok)",
        "library_label": "Bibliothek: {path}",
        "album_label": "Album: {path}",
        "change_btn": "Ändern…",
        "tooltip_change_library": "Einen anderen Bibliotheksordner auswählen",
        "tooltip_change_album": "Einen anderen Albumordner auswählen",

        "library_strip_title": "BIBLIOTHEK",
        "album_strip_title": "ALBUM",

        "btn_prev": "← Zurück",
        "btn_next": "→ Weiter",
        "btn_to_album": "↑ Ins Album",
        "btn_to_library": "↓ In die Bibliothek",
        "btn_copy_mode": "⧉ Kopieren",
        "btn_edit": "✏ Bearbeiten",
        "btn_rotate": "↻ Drehen",
        "btn_undo": "⟲ Rückgängig",
        "btn_delete": "🗑 Löschen",
        "tooltip_left_arrow": "Pfeiltaste links",
        "tooltip_right_arrow": "Pfeiltaste rechts",
        "tooltip_to_album": "Pfeiltaste hoch — ins Album verschieben",
        "tooltip_to_library": "Pfeiltaste runter — in die Bibliothek verschieben",
        "tooltip_copy_mode": "Wenn aktiv, kopieren In die Bibliothek / Ins Album die Datei, statt sie zu verschieben",
        "tooltip_edit": "E — Bearbeitungsmodus öffnen",
        "tooltip_rotate": "R — 90° im Uhrzeigersinn drehen",
        "tooltip_undo": "Strg+Z",
        "tooltip_delete": "Entf — in den Papierkorb verschieben",

        "no_image": "Kein Bild",
        "no_images": "Keine Bilder",
        "no_date": "Kein Datum",

        "save_failed_title": "Speichern fehlgeschlagen",
        "save_failed_body": "Bild konnte nicht gespeichert werden:\n{error}",
        "rotate_failed_title": "Drehen fehlgeschlagen",
        "rotate_failed_body": "Bild konnte nicht gedreht werden:\n{error}",

        "back_btn": "← Zurück",
        "crop_btn": "Zuschneiden",
        "apply_crop_btn": "✓ Zuschnitt anwenden",
        "crop_ratio_original": "Original",
        "crop_ratio_4r_land": "4R Querformat (3:2)",
        "crop_ratio_4r_port": "4R Hochformat (2:3)",
        "crop_ratio_instax_land": "Instax Mini Querformat (4:3)",
        "crop_ratio_instax_port": "Instax Mini Hochformat (3:4)",
        "tooltip_crop_ratio": "Seitenverhältnis des Zuschnitts (4R = 4×6\"-Druck)",
        "rotate_left_btn": "↺ Links drehen",
        "rotate_right_btn": "↻ Rechts drehen",
        "save_as_btn": "Speichern unter…",
        "tooltip_rotate_left": "90° gegen den Uhrzeigersinn drehen",
        "tooltip_rotate_right": "90° im Uhrzeigersinn drehen",

        "adjustments_title": "ANPASSUNGEN",
        "brightness": "Helligkeit",
        "contrast": "Kontrast",
        "exposure": "Belichtung",
        "saturation": "Sättigung",
        "shadows": "Schatten",
        "highlights": "Lichter",
        "reset_btn": "Zurücksetzen",

        "filters_title": "FILTER",
        "manage_btn": "⚙ Verwalten",
        "auto_adjustments_title": "AUTOMATISCHE ANPASSUNGEN",
        "film_simulations_title": "FILMSIMULATIONEN",
        "manage_filters_title": "Filter verwalten",
        "select_all_btn": "Alle auswählen",
        "clear_all_btn": "Alle abwählen",
        "ok_btn": "OK",
        "cancel_btn": "Abbrechen",

        "filter_original": "Original",
        "filter_provia": "Provia",
        "filter_velvia": "Velvia",
        "filter_astia": "Astia",
        "filter_classic_chrome": "Classic Chrome",
        "filter_classic_neg": "Classic Neg",
        "filter_acros": "Acros",
        "filter_eterna": "Eterna",
        "filter_sepia": "Sepia",
        "filter_faded": "Verblasst / Matt",
        "filter_cross_process": "Cross Process",
        "filter_fortia_sp": "Fortia SP",
        "filter_neopan_1600": "Neopan 1600",
        "filter_t64": "T64 (Kunstlicht)",
        "filter_pro_800z": "Pro 800Z",
        "filter_pro_400h": "Pro 400H",
        "filter_pro_160c": "Pro 160C",
        "filter_pro_160s": "Pro 160S",
        "filter_superia_1600": "Superia 1600",
        "filter_superia_400": "Superia 400",
        "filter_superia_100": "Superia 100",
        "filter_normalize": "Normalisieren (CLAHE)",
        "filter_auto_levels": "Automatische Tonwerte",
        "filter_auto_tone": "Automatischer Ton",
        "filter_auto_wb": "Automatischer Weißabgleich",

        "ai_edit_title": "KI-BEARBEITUNG",
        "ai_prompt_placeholder": "beschreibe den gewünschten Look…",
        "ai_apply_btn": "✨ Anwenden",
        "ai_undo_btn": "↩ KI rückgängig",
        "ai_thinking": "Denke nach…",
        "ai_applied": "Angewendet ✓",
        "ai_undone": "Rückgängig gemacht",
        "ai_backend_anthropic": "über Claude (Anthropic)",
        "ai_backend_ollama": "über Ollama ({model})",
        "ai_backend_none": "Kein KI-Backend gefunden — ANTHROPIC_API_KEY setzen oder Ollama starten",

        "save_as_title": "Speichern unter",
        "images_filter": "Bilder (*.jpg *.jpeg *.png *.tiff *.tif)",
    },
}
