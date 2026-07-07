"""
lang.py — ROV Sync Tool v3 localisation
Supported: English (en), Italiano (it)
Default: en
"""

STRINGS = {
    # ── App ──────────────────────────────────────────────────────────────────
    'app_title':        {'en': 'ROV Sync Tool v3.0', 'it': 'ROV Sync Tool v3.0'},
    'ready':            {'en': 'Ready.', 'it': 'Pronto.'},
    'lang_label':       {'en': 'Lingua / Language:', 'it': 'Lingua / Language:'},
    'about':            {'en': 'ℹ About', 'it': 'ℹ Info'},

    # ── About ─────────────────────────────────────────────────────────────────
    'about_title':      {'en': 'About', 'it': 'Informazioni'},
    'about_authors':    {'en': 'Authors', 'it': 'Autori'},
    'about_version':    {'en': 'Version', 'it': 'Versione'},
    'about_desc': {
        'en': 'Tool for synchronising ROV video with USBL and CTD data\nand extracting georeferenced frames for ArcGIS and annotation software.',
        'it': 'Strumento per la sincronizzazione di video ROV con dati USBL e CTD\ne l\'estrazione di frame georiferiti per ArcGIS e software di annotazione.',
    },

    # ── Tabs ──────────────────────────────────────────────────────────────────
    'tab_files':        {'en': '① Files',             'it': '① File'},
    'tab_usbl':         {'en': '② USBL Mapping',      'it': '② USBL Mapping'},
    'tab_ctd':          {'en': '③ CTD / Sensors',     'it': '③ CTD / Sensori'},
    'tab_custom':       {'en': '④ Custom Columns',    'it': '④ Colonne Custom'},
    'tab_extraction':   {'en': '⑤ Sync & Extraction', 'it': '⑤ Sync & Estrazione'},

    # ── Tab 1 — Files ─────────────────────────────────────────────────────────
    'video_file':       {'en': '📹 Video File',        'it': '📹 File Video'},
    'usbl_file':        {'en': '📡 USBL File',         'it': '📡 File USBL'},
    'ctd_file':         {'en': '🌊 CTD / Sensor File', 'it': '🌊 File CTD / Sensore'},
    'browse':           {'en': 'Browse…',              'it': 'Sfoglia…'},
    'clear':            {'en': '✕ Clear',              'it': '✕ Rimuovi'},
    'separator':        {'en': 'Separator:',           'it': 'Separatore:'},
    'has_header':       {'en': 'File has header',      'it': 'Il file ha header'},
    'load_usbl':        {'en': 'Load USBL',            'it': 'Carica USBL'},
    'load_ctd':         {'en': 'Load',                 'it': 'Carica'},
    'dive_name':        {'en': '🏷  Dive Name:',       'it': '🏷  Nome Dive:'},
    'output_folder':    {'en': '📁 Output Folder',     'it': '📁 Cartella Output'},
    'hardware':         {'en': 'Hardware',             'it': 'Hardware'},
    'cuda_available':   {'en': 'Use GPU CUDA ({n} device(s) detected)', 'it': 'Usa GPU CUDA ({n} device rilevati)'},
    'cuda_unavailable': {'en': 'CUDA not available (CPU mode)', 'it': 'CUDA non disponibile (CPU mode)'},
    'hw_info':          {'en': 'CPU cores: {cores}  |  OpenCV: {cv}  |  geopandas: {geo}', 'it': 'CPU core: {cores}  |  OpenCV: {cv}  |  geopandas: {geo}'},
    'profile_label':    {'en': 'Profile:', 'it': 'Profilo:'},
    'save_profile':     {'en': '💾 Save',  'it': '💾 Salva'},
    'load_profile':     {'en': '📂 Load',  'it': '📂 Carica'},

    # ── Tab 2 — USBL ──────────────────────────────────────────────────────────
    'usbl_preview':      {'en': 'File preview (first 5 rows)', 'it': 'Anteprima file (prime 5 righe)'},
    'timestamp_section': {'en': 'Timestamp',                   'it': 'Timestamp'},
    'ts_unified':        {'en': 'Unified',                     'it': 'Unificato'},
    'ts_split':          {'en': 'Date + Time separate',        'it': 'Data + Ora separate'},
    'ts_unix':           {'en': 'Unix epoch',                  'it': 'Unix epoch'},
    'col_label':         {'en': 'Column:',  'it': 'Colonna:'},
    'format_label':      {'en': 'Format:',  'it': 'Formato:'},
    'col_date':          {'en': 'Date col:', 'it': 'Col. Data:'},
    'fmt_date':          {'en': 'Date fmt:', 'it': 'Fmt Data:'},
    'col_time':          {'en': 'Time col:', 'it': 'Col. Ora:'},
    'fmt_time':          {'en': 'Time fmt:', 'it': 'Fmt Ora:'},
    'coordinates':       {'en': 'Coordinates', 'it': 'Coordinate'},
    'coord_format':      {'en': 'Format:', 'it': 'Formato:'},
    'col_lat':           {'en': 'Lat:', 'it': 'Lat:'},
    'col_lon':           {'en': 'Lon:', 'it': 'Lon:'},
    'col_depth':         {'en': 'Depth:', 'it': 'Depth:'},
    'validate_usbl':     {'en': '✅ Validate mapping', 'it': '✅ Valida mapping'},
    'usbl_ok':           {'en': '✅ OK → {lat:.5f}°N  {lon:.5f}°E  depth {depth:.1f}m  |  {n} rows', 'it': '✅ OK → {lat:.5f}°N  {lon:.5f}°E  depth {depth:.1f}m  |  {n} righe'},
    'usbl_loaded':       {'en': '✓ {n} rows | Columns: {cols}', 'it': '✓ {n} righe | Colonne: {cols}'},
    'exclude_cols':      {'en': 'Columns to exclude from output (click to exclude):', 'it': 'Colonne da escludere dall\'output (clicca per escludere):'},

    # ── Tab 3 — CTD ───────────────────────────────────────────────────────────
    'ctd_preview':       {'en': 'CTD Preview',           'it': 'Anteprima CTD'},
    'ctd_sync_mode':     {'en': 'Synchronisation Mode',  'it': 'Modalità Sincronizzazione'},
    'ctd_by_time':       {'en': '⏱ By Time (CTD on ROV)', 'it': '⏱ Per Tempo (CTD sul ROV)'},
    'ctd_by_depth':      {'en': '🌊 By Depth (CTD separate)', 'it': '🌊 Per Profondità (CTD separata)'},
    'ctd_ts_col':        {'en': 'Timestamp:', 'it': 'Timestamp:'},
    'ctd_depth_col':     {'en': 'Depth:', 'it': 'Depth:'},
    'ctd_cols_label':    {'en': 'CTD parameters to include (click to select):', 'it': 'Parametri CTD da includere (clicca per selezionare):'},

    # ── Tab 4 — Custom ────────────────────────────────────────────────────────
    'custom_intro':      {'en': 'Add columns not present in the USBL file', 'it': 'Aggiungi colonne non presenti nel file USBL'},
    'col_name':          {'en': 'Name:', 'it': 'Nome:'},
    'col_value':         {'en': 'Value:', 'it': 'Valore:'},
    'add_column':        {'en': '＋ Add column', 'it': '＋ Aggiungi colonna'},
    'csv_preview_label': {'en': 'CSV output row preview:', 'it': 'Anteprima riga CSV output:'},
    'update_preview':    {'en': '🔄 Update preview', 'it': '🔄 Aggiorna anteprima'},

    # ── Tab 5 — Sync & Extraction ─────────────────────────────────────────────
    'sync_panel':        {'en': '🔗 Synchronisation Panel', 'it': '🔗 Pannello Sincronizzazione'},
    'video_ts_label':    {'en': 'Video creation timestamp (from metadata):', 'it': 'Timestamp creazione video (da metadata):'},
    'video_depth_label': {'en': 'Touchdown depth (read from video):', 'it': 'Profondità touchdown (letta dal video):'},
    'ctd_ts_sync':       {'en': 'CTD start timestamp:', 'it': 'Timestamp inizio CTD:'},
    'ctd_ts_edit':       {'en': 'Correct manually:', 'it': 'Correggi manualmente:'},
    'ctd_delay_label':   {'en': 'CTD additional delay (s):', 'it': 'Delay CTD aggiuntivo (s):'},
    'timeline_label':    {'en': 'Instrument coverage timeline:', 'it': 'Timeline copertura strumenti:'},
    'delay_section':     {'en': '⏱ Video vs USBL Delay', 'it': '⏱ Delay Video vs USBL'},
    'delay_label':       {'en': 'Delay (s):', 'it': 'Delay (s):'},
    'delay_hint':        {'en': '(negative = video starts before USBL data)', 'it': '(negativo = video inizia prima dei dati USBL)'},
    'extraction_section':{'en': '📷 Frame Extraction', 'it': '📷 Estrazione Frame'},
    'every_n_sec':       {'en': 'Every N seconds:', 'it': 'Ogni N secondi:'},
    'assoc_window':      {'en': 'Association tolerance (s):', 'it': 'Tolleranza associazione (s):'},
    'format_label2':     {'en': 'Format:', 'it': 'Formato:'},
    'jpeg_quality':      {'en': 'JPEG Quality:', 'it': 'Qualità JPEG:'},
    'quality_section':   {'en': '🔍 Problematic Frame Detection', 'it': '🔍 Rilevamento Frame Problematici'},
    'blur_thresh':       {'en': 'Blur threshold:', 'it': 'Soglia blur:'},
    'dark_thresh':       {'en': 'Dark threshold:', 'it': 'Soglia buio:'},
    'bright_thresh':     {'en': 'Overexposed threshold:', 'it': 'Soglia sovraesposto:'},
    'quality_hint':      {'en': "Problematic frames extracted but flagged in the CSV 'warning' column.", 'it': "Frame problematici estratti ma segnalati nella colonna 'warning' del CSV."},
    'overlay_section':   {'en': '🖊 Frame Text Overlay', 'it': '🖊 Overlay Testo sul Frame'},
    'overlay_enable':    {'en': 'Enable overlay', 'it': 'Abilita overlay'},
    'ovl_time':          {'en': 'Time', 'it': 'Time'},
    'ovl_depth':         {'en': 'Depth', 'it': 'Depth'},
    'ovl_latlon':        {'en': 'Lat/Lon', 'it': 'Lat/Lon'},
    'ovl_dive':          {'en': 'Dive', 'it': 'Dive'},
    'ovl_position':      {'en': 'Position:', 'it': 'Posizione:'},
    'ovl_fontsize':      {'en': 'Font size:', 'it': 'Font size:'},
    'ovl_color':         {'en': 'Color:', 'it': 'Colore:'},
    'ovl_bg':            {'en': 'Background:', 'it': 'Sfondo:'},
    'btn_start':         {'en': '▶  Start Extraction', 'it': '▶  Avvia Estrazione'},
    'btn_pause':         {'en': '⏸  Pause / Resume',  'it': '⏸  Pausa / Riprendi'},
    'btn_stop':          {'en': '⏹  Stop',            'it': '⏹  Stop'},
    'progress_label':    {'en': 'Progress: {pct}%', 'it': 'Progresso: {pct}%'},

    # ── Errors & log ──────────────────────────────────────────────────────────
    'err_no_video':       {'en': 'Please select a video file.', 'it': 'Seleziona un file video.'},
    'err_no_usbl':        {'en': 'Please select a USBL file.', 'it': 'Seleziona un file USBL.'},
    'err_no_output':      {'en': 'Please select an output folder.', 'it': 'Seleziona la cartella di output.'},
    'err_validate_first': {'en': 'Please run "Validate mapping" in the USBL tab first.', 'it': 'Esegui prima "Valida mapping" nel tab USBL.'},
    'error_title':        {'en': 'Error', 'it': 'Errore'},
    'log_cuda_ok':        {'en': 'CUDA GPU enabled ({n} device(s))', 'it': 'GPU CUDA abilitata ({n} device)'},
    'log_cpu':            {'en': 'Video decoding on CPU', 'it': 'Decodifica video su CPU'},
    'log_video_ok':       {'en': 'Video: {fps:.2f} fps, {dur:.1f}s, {tot} total frames', 'it': 'Video: {fps:.2f} fps, {dur:.1f}s, {tot} frame totali'},
    'log_frames_plan':    {'en': 'Frames to extract: {n} (every {iv}s)', 'it': 'Frame da estrarre: {n} (ogni {iv}s)'},
    'log_frame_skip':     {'en': 'Frame {i}: read failed, skipping', 'it': 'Frame {i}: lettura fallita, skip'},
    'log_stopped':        {'en': 'Extraction stopped by user', 'it': "Estrazione interrotta dall'utente"},
    'log_csv_saved':      {'en': 'CSV saved: {path}', 'it': 'CSV salvato: {path}'},
    'log_shp_saved':      {'en': 'Shapefile saved: {path}', 'it': 'Shapefile salvato: {path}'},
    'log_session_saved':  {'en': 'Session log JSON saved', 'it': 'Session log JSON salvato'},
    'log_done':           {'en': '✅ Done! {n} frames extracted.', 'it': '✅ Completato! {n} frame estratti.'},
    'log_ctd_warn':       {'en': 'CTD not loaded: {e}', 'it': 'CTD non caricata: {e}'},
    'log_profile_saved':  {'en': 'Profile saved: {path}', 'it': 'Profilo salvato: {path}'},
    'log_profile_loaded': {'en': 'Profile loaded: {path}', 'it': 'Profilo caricato: {path}'},
    'log_frame_ok':       {'en': '{img} → {lat:.5f}°N {lon:.5f}°E | depth {d:.1f}m', 'it': '{img} → {lat:.5f}°N {lon:.5f}°E | depth {d:.1f}m'},
    'pause_info':         {'en': 'Pause/Resume: feature in development', 'it': 'Pausa/Riprendi: funzione in sviluppo'},
    'stop_requested':     {'en': 'Stop requested…', 'it': 'Stop richiesto…'},

    # ── Frame warnings ────────────────────────────────────────────────────────
    'warn_blur':          {'en': 'blurry',      'it': 'mosso'},
    'warn_dark':          {'en': 'dark',         'it': 'buio'},
    'warn_bright':        {'en': 'overexposed',  'it': 'sovraesposto'},

    # ── Overlay field labels ───────────────────────────────────────────────────
    'ovl_field_time':     {'en': 'Time',  'it': 'Ora'},
    'ovl_field_depth':    {'en': 'Depth', 'it': 'Prof'},
    'ovl_field_pos':      {'en': 'Pos',   'it': 'Pos'},
    'ovl_field_dive':     {'en': 'Dive',  'it': 'Dive'},

    # ── Tooltips — Sync & Extraction ──────────────────────────────────────────
    'assoc_window_tip': {
        'en': (
            "Maximum time gap allowed when matching a frame to the nearest USBL/CTD data.\n\n"
            "Example: with tolerance 5s, if USBL has a 30-second gap and a frame falls in that gap, "
            "the frame is discarded because the nearest USBL data is too far in time to be reliable.\n\n"
            "Typical values: 2–10 seconds."
        ),
        'it': (
            "Intervallo massimo di tempo entro il quale un frame viene associato ai dati USBL/CTD più vicini.\n\n"
            "Esempio: con tolleranza 5s, se l'USBL ha un buco di 30 secondi e un frame cade in quel buco, "
            "il frame viene scartato perché i dati USBL più vicini sono troppo lontani per essere affidabili.\n\n"
            "Valori tipici: 2–10 secondi."
        ),
    },
    'tip_video_meta_ts': {
        'en': (
            "Original video timestamp read from:\n"
            "① QuickTime Timecode track (most reliable for MOV/MP4)\n"
            "② Container metadata (encoded_date, tagged_date)\n"
            "③ Filename pattern (if configured)\n"
            "④ Windows mtime (unreliable — shown in red)\n\n"
            "Green = reliable  |  Yellow = uncertain  |  Red = unreliable\n"
            "If shown in red, correct it manually below."
        ),
        'it': (
            "Timestamp originale del video letto da:\n"
            "① QuickTime Timecode track (più affidabile per MOV/MP4)\n"
            "② Metadata container (encoded_date, tagged_date)\n"
            "③ Pattern nome file (se configurato)\n"
            "④ mtime Windows (non affidabile — mostrato in rosso)\n\n"
            "Verde = affidabile  |  Giallo = incerto  |  Rosso = non affidabile\n"
            "Se in rosso, correggi manualmente nel campo sottostante."
        ),
    },
    'tip_video_slider': {
        'en': (
            "Scroll the video to find the touchdown point (when the ROV touches the seafloor).\n\n"
            "◀◀ / ▶▶ = ±10 seconds\n"
            "◀ / ▶ = ±1 second\n"
            "-1f / +1f = ±1 frame\n\n"
            "Position the slider at the exact touchdown moment, then click the same\n"
            "point on the USBL depth plot below to synchronise."
        ),
        'it': (
            "Scorri il video per trovare il punto di touchdown (quando il ROV tocca il fondo).\n\n"
            "◀◀ / ▶▶ = ±10 secondi\n"
            "◀ / ▶ = ±1 secondo\n"
            "-1f / +1f = ±1 frame\n\n"
            "Posiziona lo slider sul momento esatto del touchdown, poi clicca lo stesso\n"
            "punto nel grafico USBL sottostante per sincronizzare."
        ),
    },
    'tip_touchdown_depth': {
        'en': (
            "Read the depth visually from the video overlay at the exact touchdown frame.\n"
            "Enter the value here (in metres).\n\n"
            "This depth will appear next to the USBL depth in the alignment table,\n"
            "so you can verify they match — confirming the synchronisation is correct."
        ),
        'it': (
            "Leggi la profondità visivamente dall'overlay del video al frame di touchdown.\n"
            "Inserisci il valore qui (in metri).\n\n"
            "Questa profondità apparirà accanto alla profondità USBL nella tabella di allineamento,\n"
            "così puoi verificare che corrispondano — confermando che la sincronizzazione è corretta."
        ),
    },
    'tip_usbl_plot': {
        'en': (
            "USBL depth profile over time.\n\n"
            "Click on the point where the ROV reached the seafloor (maximum stable depth).\n"
            "This should correspond to the same moment visible in the video.\n\n"
            "Green marker = selected USBL touchdown\n"
            "Yellow dashed line = current video frame position\n\n"
            "After selecting both points, click '🎯 Synchronise'."
        ),
        'it': (
            "Grafico della profondità USBL nel tempo.\n\n"
            "Clicca sul punto in cui il ROV ha raggiunto il fondo (profondità massima stabilizzata).\n"
            "Questo dovrebbe corrispondere allo stesso momento visibile nel video.\n\n"
            "Marker verde = touchdown USBL selezionato\n"
            "Linea tratteggiata gialla = posizione frame video corrente\n\n"
            "Dopo aver selezionato entrambi i punti, clicca '🎯 Synchronise'."
        ),
    },
    'tip_sync_btn': {
        'en': (
            "Calculates the video/USBL offset using two corresponding points:\n"
            "  • Slider position = touchdown moment in the video\n"
            "  • Clicked point on USBL plot = same moment in USBL data\n\n"
            "The calculated start timestamp is written to the 'Corrected video start' field.\n"
            "Check the alignment table to verify the synchronisation quality."
        ),
        'it': (
            "Calcola il delay video/USBL usando due punti corrispondenti:\n"
            "  • Posizione slider = momento del touchdown nel video\n"
            "  • Punto cliccato sul grafico USBL = stesso momento nei dati USBL\n\n"
            "Il timestamp calcolato viene scritto nel campo 'Timestamp inizio video corretto'.\n"
            "Controlla la tabella di allineamento per verificare la qualità della sincronizzazione."
        ),
    },
    'tip_reset_btn': {
        'en': (
            "Resets all synchronisation parameters:\n"
            "  • Video delay → 0\n"
            "  • CTD delay → 0\n"
            "  • Corrected CTD timestamp → cleared\n"
            "  • Video timestamp → restored from metadata\n"
            "  • USBL touchdown selection → cleared\n\n"
            "Useful for starting the synchronisation from scratch."
        ),
        'it': (
            "Ripristina tutti i parametri di sincronizzazione:\n"
            "  • Delay video → 0\n"
            "  • Delay CTD → 0\n"
            "  • Timestamp CTD corretto → svuotato\n"
            "  • Timestamp video → ripristinato dai metadata\n"
            "  • Selezione touchdown USBL → svuotata\n\n"
            "Utile per ricominciare la sincronizzazione da capo."
        ),
    },
    'tip_update_preview': {
        'en': (
            "Recalculates the alignment table with the current settings.\n\n"
            "Press this button after manually modifying timestamps or delays\n"
            "to see the updated alignment quality."
        ),
        'it': (
            "Ricalcola la tabella di allineamento con le impostazioni correnti.\n\n"
            "Premi questo bottone dopo aver modificato manualmente i timestamp o i delay\n"
            "per vedere la qualità dell'allineamento aggiornata."
        ),
    },
    'tip_video_ts_corrected': {
        'en': (
            "Manually corrected UTC timestamp for the start of the video (frame 0).\n"
            "Format: YYYY-MM-DDTHH:MM:SS  (e.g. 2020-10-25T11:49:56)\n\n"
            "This field is filled automatically by the touchdown synchronisation.\n"
            "Edit it here only if you know the exact start time from another source\n"
            "(e.g. dive log, operator notes)."
        ),
        'it': (
            "Timestamp UTC corretto manualmente per l'inizio del video (frame 0).\n"
            "Formato: YYYY-MM-DDTHH:MM:SS  (es. 2020-10-25T11:49:56)\n\n"
            "Questo campo viene compilato automaticamente dalla sincronizzazione touchdown.\n"
            "Modificalo qui solo se conosci l'orario esatto di inizio da un'altra fonte\n"
            "(es. log della dive, appunti dell'operatore)."
        ),
    },
    'tip_ctd_ts_corrected': {
        'en': (
            "Manually corrected UTC timestamp for the start of the CTD file.\n"
            "Format: YYYY-MM-DDTHH:MM:SS\n\n"
            "Use this when the CTD has a wrong date or time — for example if the CTD\n"
            "was deployed on a different day from the ROV dive.\n\n"
            "This value shifts the entire CTD time series to align with the USBL.\n"
            "The alignment table shows the result — aim for small ΔT values."
        ),
        'it': (
            "Timestamp UTC corretto manualmente per l'inizio del file CTD.\n"
            "Formato: YYYY-MM-DDTHH:MM:SS\n\n"
            "Usa questo campo quando la CTD ha una data o un'ora sbagliata — ad esempio se\n"
            "la CTD è stata calata in un giorno diverso dalla dive del ROV.\n\n"
            "Questo valore trasla l'intera serie temporale CTD per allinearla all'USBL.\n"
            "La tabella di allineamento mostra il risultato — punta a valori ΔT piccoli."
        ),
    },
    'tip_ctd_delay': {
        'en': (
            "Additional delay in seconds applied to the CTD after timestamp correction.\n\n"
            "Positive = CTD records later than USBL (CTD clock is fast)\n"
            "Negative = CTD records earlier (CTD clock is slow)\n\n"
            "Use this for fine-tuning after the main timestamp correction.\n"
            "Typical values: ±0 to ±60 seconds."
        ),
        'it': (
            "Delay aggiuntivo in secondi applicato alla CTD dopo la correzione del timestamp.\n\n"
            "Positivo = la CTD registra in ritardo rispetto all'USBL (orologio CTD avanzato)\n"
            "Negativo = la CTD registra in anticipo (orologio CTD in ritardo)\n\n"
            "Usa questo per regolazioni fini dopo la correzione principale del timestamp.\n"
            "Valori tipici: ±0 a ±60 secondi."
        ),
    },
    'tip_extract_from': {
        'en': (
            "Start time (seconds from video beginning) for frame extraction.\n\n"
            "Use the '📍 From current pos.' button to set this to the current slider position.\n"
            "Tip: set this to just before the ROV reaches the seafloor to skip the descent."
        ),
        'it': (
            "Tempo di inizio (secondi dall'inizio del video) per l'estrazione dei frame.\n\n"
            "Usa il bottone '📍 Da pos. corrente' per impostarlo alla posizione corrente dello slider.\n"
            "Tip: impostalo poco prima che il ROV raggiunga il fondo per saltare la discesa."
        ),
    },
    'tip_extract_to': {
        'en': (
            "End time (seconds from video beginning) for frame extraction.\n"
            "Set to 0 to extract until the end of the video.\n\n"
            "Use '📍 To current pos.' to set this to the current slider position.\n"
            "Tip: set this to just after the ROV starts ascending to skip the ascent."
        ),
        'it': (
            "Tempo di fine (secondi dall'inizio del video) per l'estrazione dei frame.\n"
            "Impostare a 0 per estrarre fino alla fine del video.\n\n"
            "Usa '📍 A pos. corrente' per impostarlo alla posizione corrente dello slider.\n"
            "Tip: impostalo poco dopo che il ROV inizia a risalire per saltare la risalita."
        ),
    },
    'tip_interval': {
        'en': (
            "Time interval in seconds between extracted frames.\n\n"
            "Examples:\n"
            "  5s  → ~720 frames per hour of video (high density)\n"
            "  30s → ~120 frames per hour (standard for habitat mapping)\n"
            "  60s →  ~60 frames per hour (sparse)\n\n"
            "Choose based on ROV speed and habitat variability.\n"
            "Faster ROV or more variable habitat → shorter interval."
        ),
        'it': (
            "Intervallo di tempo in secondi tra i frame estratti.\n\n"
            "Esempi:\n"
            "  5s  → ~720 frame per ora di video (alta densità)\n"
            "  30s → ~120 frame per ora (standard per habitat mapping)\n"
            "  60s →  ~60 frame per ora (rado)\n\n"
            "Scegliere in base alla velocità del ROV e alla variabilità dell'habitat.\n"
            "ROV più veloce o habitat più variabile → intervallo più breve."
        ),
    },
    'tip_img_format': {
        'en': (
            "Image format for extracted frames:\n\n"
            "• PNG  — Lossless, maximum quality. ~2–8 MB/frame at 4K.\n"
            "         Best for annotation software and photogrammetry.\n"
            "• JPEG — Lossy, smaller files. ~0.5–2 MB/frame at 4K.\n"
            "         Good for quick review and ArcGIS.\n"
            "• TIFF — Lossless, compatible with GIS and scientific software.\n"
            "         Largest files."
        ),
        'it': (
            "Formato di salvataggio delle immagini estratte:\n\n"
            "• PNG  — Lossless, qualità massima. ~2–8 MB/frame a 4K.\n"
            "         Ottimo per software di annotazione e fotogrammetria.\n"
            "• JPEG — Lossy, file più piccoli. ~0.5–2 MB/frame a 4K.\n"
            "         Buono per review rapida e ArcGIS.\n"
            "• TIFF — Lossless, compatibile con GIS e software scientifici.\n"
            "         File più grandi."
        ),
    },
    'tip_jpeg_quality': {
        'en': (
            "JPEG compression quality (1–100). Used only when format is JPEG.\n\n"
            "95 = near-lossless, recommended for scientific use\n"
            "85 = good quality, ~40% smaller than 95\n"
            "75 = acceptable, ~60% smaller\n\n"
            "Values below 70 are not recommended for annotation work."
        ),
        'it': (
            "Qualità di compressione JPEG (1–100). Usato solo con formato JPEG.\n\n"
            "95 = quasi-lossless, raccomandato per uso scientifico\n"
            "85 = buona qualità, ~40% più piccolo del 95\n"
            "75 = accettabile, ~60% più piccolo\n\n"
            "Valori sotto 70 non sono raccomandati per lavoro di annotazione."
        ),
    },
    'tip_blur_thresh': {
        'en': (
            "Threshold to detect blurry frames.\n"
            "Method: variance of the Laplacian filter on the grayscale image.\n\n"
            "Low variance = blurry frame (camera motion or turbidity).\n"
            "Default: 50\n\n"
            "Lower this value if too many sharp frames are flagged as blurry.\n"
            "Raise it if blurry frames are not being detected.\n\n"
            "Note: flagged frames are still extracted — the choice is yours."
        ),
        'it': (
            "Soglia per rilevare frame mossi.\n"
            "Metodo: varianza del filtro Laplaciano sull'immagine in scala di grigi.\n\n"
            "Varianza bassa = frame mosso (movimento camera o torbidità).\n"
            "Default: 50\n\n"
            "Abbassa se troppi frame nitidi vengono segnalati come mossi.\n"
            "Alza se i frame mossi non vengono rilevati.\n\n"
            "Nota: i frame segnalati vengono comunque estratti — la scelta finale è tua."
        ),
    },
    'tip_dark_thresh': {
        'en': (
            "Average brightness threshold below which a frame is flagged as 'dark'.\n"
            "Range: 0–255. Default: 30.\n\n"
            "Dark frames occur during:\n"
            "  • Descent through the water column\n"
            "  • Camera pointing at dark substrate\n"
            "  • Temporary light failure\n\n"
            "Flagged frames are still extracted — the choice is yours."
        ),
        'it': (
            "Soglia di luminosità media sotto cui un frame è segnalato come 'buio'.\n"
            "Range: 0–255. Default: 30.\n\n"
            "Frame bui si verificano durante:\n"
            "  • Discesa in colonna d'acqua\n"
            "  • Camera puntata su substrato scuro\n"
            "  • Temporanea perdita di illuminazione\n\n"
            "I frame segnalati vengono comunque estratti — la scelta finale è tua."
        ),
    },
    'tip_bright_thresh': {
        'en': (
            "Average brightness threshold above which a frame is flagged as 'overexposed'.\n"
            "Range: 0–255. Default: 230.\n\n"
            "Overexposed frames occur when:\n"
            "  • Camera points directly at ROV lights\n"
            "  • Bioluminescence event\n"
            "  • Camera near the surface in sunlit water\n\n"
            "Flagged frames are still extracted — the choice is yours."
        ),
        'it': (
            "Soglia di luminosità media sopra cui un frame è segnalato come 'sovraesposto'.\n"
            "Range: 0–255. Default: 230.\n\n"
            "Frame sovraesposti si verificano quando:\n"
            "  • La camera punta direttamente verso i fari del ROV\n"
            "  • Evento di bioluminescenza\n"
            "  • Camera vicino alla superficie in acqua illuminata dal sole\n\n"
            "I frame segnalati vengono comunque estratti — la scelta finale è tua."
        ),
    },
    'tip_ovl_enable': {
        'en': (
            "When enabled, selected information is written directly onto each extracted frame.\n\n"
            "The text is rendered with a background for readability on any substrate.\n"
            "This does not affect the CSV — all data is always saved in the CSV regardless."
        ),
        'it': (
            "Quando abilitato, le informazioni selezionate vengono scritte direttamente su ogni frame estratto.\n\n"
            "Il testo viene renderizzato con uno sfondo per leggibilità su qualsiasi substrato.\n"
            "Questo non influisce sul CSV — tutti i dati vengono sempre salvati nel CSV."
        ),
    },
    'tip_ovl_fields': {
        'en': (
            "Select which data fields to write on each frame:\n\n"
            "• Time  — UTC timestamp of the frame (from video + sync offset)\n"
            "• Depth — USBL depth at that timestamp\n"
            "• Lat/Lon — USBL coordinates\n"
            "• Dive — Dive name as entered in Tab ①"
        ),
        'it': (
            "Seleziona i campi da scrivere su ogni frame:\n\n"
            "• Time  — Timestamp UTC del frame (da video + offset sincronizzazione)\n"
            "• Depth — Profondità USBL al timestamp corrispondente\n"
            "• Lat/Lon — Coordinate USBL\n"
            "• Dive — Nome della dive inserito nel Tab ①"
        ),
    },
    'tip_ovl_pos': {
        'en': (
            "Position of the overlay text on the frame:\n\n"
            "• bottom_left  — lower left (default, avoids most ROV HUD elements)\n"
            "• bottom_right — lower right\n"
            "• top_left     — upper left\n"
            "• top_right    — upper right\n\n"
            "Choose a corner that doesn't overlap with the ROV's own overlay."
        ),
        'it': (
            "Posizione del testo overlay sul frame:\n\n"
            "• bottom_left  — in basso a sinistra (default, evita la maggior parte degli HUD del ROV)\n"
            "• bottom_right — in basso a destra\n"
            "• top_left     — in alto a sinistra\n"
            "• top_right    — in alto a destra\n\n"
            "Scegli un angolo che non si sovrapponga all'overlay del ROV."
        ),
    },
    'tip_ovl_fontsize': {
        'en': (
            "Font size in pixels for the overlay text.\n\n"
            "Recommended values by resolution:\n"
            "  4K (3840×2160) → 40–60 px\n"
            "  HD (1920×1080) → 24–36 px\n"
            "  SD (1280×720)  → 18–24 px\n\n"
            "Default: 28 px (designed for HD)"
        ),
        'it': (
            "Dimensione del font in pixel per il testo overlay.\n\n"
            "Valori consigliati per risoluzione:\n"
            "  4K (3840×2160) → 40–60 px\n"
            "  HD (1920×1080) → 24–36 px\n"
            "  SD (1280×720)  → 18–24 px\n\n"
            "Default: 28 px (pensato per HD)"
        ),
    },
    'tip_ovl_color': {
        'en': (
            "Colour of the overlay text:\n\n"
            "• white  — visible on dark substrates (recommended for deep-sea)\n"
            "• yellow — high visibility on most backgrounds\n"
            "• cyan   — good contrast on reddish/orange substrates\n"
            "• black  — for bright/sandy backgrounds"
        ),
        'it': (
            "Colore del testo overlay:\n\n"
            "• white  — visibile su substrati scuri (consigliato per acque profonde)\n"
            "• yellow — alta visibilità su quasi tutti gli sfondi\n"
            "• cyan   — buon contrasto su substrati rossastri/arancioni\n"
            "• black  — per sfondi chiari/sabbiosi"
        ),
    },
    'tip_ovl_bg': {
        'en': (
            "Background style for the overlay text:\n\n"
            "• rect   — semi-transparent black rectangle (maximum readability, recommended)\n"
            "• shadow — drop shadow on the text (less intrusive, less readable)\n"
            "• none   — no background (text directly on frame, may be hard to read)"
        ),
        'it': (
            "Stile dello sfondo del testo overlay:\n\n"
            "• rect   — rettangolo nero semitrasparente (massima leggibilità, consigliato)\n"
            "• shadow — ombra sul testo (meno invasivo, meno leggibile)\n"
            "• none   — nessuno sfondo (testo diretto sul frame, può essere difficile da leggere)"
        ),
    },
}


def get(key: str, lang: str, **kwargs) -> str:
    entry = STRINGS.get(key, {})
    text  = entry.get(lang) or entry.get('en', f'[{key}]')
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass
    return text
