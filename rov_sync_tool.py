"""
ROV Sync Tool v3.0
==================
Autori:
  Fabio Marchese — HaBB Lab, Red Sea Research Center, KAUST
  Claude Sonnet 4.6 — Anthropic

Dipendenze:
  pip install opencv-python pandas numpy pillow geopandas shapely pymediainfo
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import threading, json, os, queue, base64, io, math, re, subprocess, shutil
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageTk
from lang import get as _L

try:
    import geopandas as gpd
    from shapely.geometry import Point
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False

try:
    from pymediainfo import MediaInfo
    HAS_MEDIAINFO = True
except ImportError:
    HAS_MEDIAINFO = False

try:
    CUDA_COUNT = cv2.cuda.getCudaEnabledDeviceCount()
    HAS_CUDA   = CUDA_COUNT > 0
except Exception:
    HAS_CUDA   = False
    CUDA_COUNT = 0

HABB_LOGO_B64 = ""


# ─────────────────────────────────────────────────────────────────────────────
# COORDINATE
# ─────────────────────────────────────────────────────────────────────────────

def parse_coord(val, fmt):
    val   = str(val).strip().replace(',', '.')
    sign  = 1
    upper = val.upper()
    if 'S' in upper or 'W' in upper:
        sign = -1
    clean = upper.replace('N','').replace('S','').replace('E','').replace('W','')
    clean = clean.replace('°',' ').replace("'",' ').replace('"',' ').strip()
    parts = [p for p in clean.split() if p.replace('.','').replace('-','').isdigit()]
    if not parts:
        return np.nan
    try:
        fv = float(parts[0])
        if fmt == 'UTM':
            return fv
        if (fmt == 'DD' and abs(fv) > 180) or fmt == 'NMEA':
            d = int(abs(fv) / 100)
            m = abs(fv) - d * 100
            return sign * (d + m / 60.0)
        if fmt == 'DD':
            return sign * fv
        if fmt == 'DM':
            if len(parts) >= 2:
                return sign * (float(parts[0]) + float(parts[1]) / 60.0)
            d = int(abs(fv)/100); m = abs(fv) - d*100
            return sign * (d + m/60.0)
        if fmt == 'DMS':
            if len(parts) >= 3:
                return sign*(float(parts[0])+float(parts[1])/60+float(parts[2])/3600)
            elif len(parts) == 2:
                return sign*(float(parts[0])+float(parts[1])/60)
            return sign*fv
    except Exception:
        return np.nan


def utm_to_dd(easting, northing, zone_number, northern=True):
    a=6378137.0; f=1/298.257223563; b=a*(1-f)
    e2=1-(b/a)**2; k0=0.9996
    x=easting-500000.0
    y=northing if northern else northing-10000000.0
    lon0=math.radians((zone_number-1)*6-180+3)
    M=y/k0
    mu=M/(a*(1-e2/4-3*e2**2/64-5*e2**3/256))
    e1=(1-math.sqrt(1-e2))/(1+math.sqrt(1-e2))
    phi1=(mu+(3*e1/2-27*e1**3/32)*math.sin(2*mu)
            +(21*e1**2/16-55*e1**4/32)*math.sin(4*mu)
            +(151*e1**3/96)*math.sin(6*mu)
            +(1097*e1**4/512)*math.sin(8*mu))
    N1=a/math.sqrt(1-e2*math.sin(phi1)**2)
    T1=math.tan(phi1)**2; C1=e2/(1-e2)*math.cos(phi1)**2
    R1=a*(1-e2)/(1-e2*math.sin(phi1)**2)**1.5; D=x/(N1*k0)
    lat=phi1-(N1*math.tan(phi1)/R1)*(D**2/2
        -(5+3*T1+10*C1-4*C1**2-9*e2/(1-e2))*D**4/24
        +(61+90*T1+298*C1+45*T1**2-252*e2/(1-e2)-3*C1**2)*D**6/720)
    lon=lon0+(D-(1+2*T1+C1)*D**3/6
        +(5-2*C1+28*T1-3*C1**2+8*e2/(1-e2)+24*T1**2)*D**5/120)/math.cos(phi1)
    return math.degrees(lat), math.degrees(lon)


def detect_coord_format(val_str):
    try:
        v=str(val_str).strip()
        fv=float(v.upper().replace('N','').replace('S','').replace('E','').replace('W','')
                   .replace('°','').replace("'",'').replace('"','').replace(',','.').split()[0])
        if abs(fv)>18000: return 'UTM'
        if abs(fv)>180:   return 'NMEA'
        if '°' in v or "'" in v:
            return 'DMS' if '"' in v else 'DM'
        return 'DD'
    except Exception:
        return 'DD'


def _find_hemisphere(df, val_col, direction):
    valid = {'lat':{'N','S'}, 'lon':{'E','W'}}[direction]
    cols  = list(df.columns)
    try: idx = cols.index(val_col)
    except ValueError: return None
    for offset in [1,-1,2,-2]:
        c = idx+offset
        if 0 <= c < len(cols):
            col = cols[c]
            sample = df[col].dropna().astype(str).str.strip().str.upper()
            if sample.isin(valid).mean() > 0.8:
                return col
    return None


# ─────────────────────────────────────────────────────────────────────────────
# TIMESTAMP
# ─────────────────────────────────────────────────────────────────────────────

def parse_timestamp(row, mode, col_date, col_time, fmt_date, fmt_time,
                    col_unified, fmt_unified):
    try:
        if mode == 'unix':
            return datetime.fromtimestamp(float(row[col_unified]), tz=timezone.utc)
        elif mode == 'unified':
            raw = str(row[col_unified]).strip()
            if fmt_unified:
                try:
                    return datetime.strptime(raw, fmt_unified).replace(tzinfo=timezone.utc)
                except Exception: pass
            try: return pd.to_datetime(raw, utc=True).to_pydatetime()
            except Exception: pass
            try: return pd.to_datetime(raw.rstrip('Z'), utc=True).to_pydatetime()
            except Exception: pass
            try: return pd.to_datetime(raw[:19], utc=True).to_pydatetime()
            except Exception: pass
            return None
        elif mode == 'split':
            raw_date = str(row[col_date]).strip()
            raw_time = str(row[col_time]).strip()
            if fmt_time == 'HHMMSS.ss':
                t=float(raw_time.replace(',','.')); hh=int(t//10000)
                mm=int((t%10000)//100); ss=t%100
                time_str=f"{hh:02d}:{mm:02d}:{ss:06.3f}"; fmt_time_std='%H:%M:%S.%f'
            else:
                time_str=raw_time; fmt_time_std=fmt_time
            if fmt_date=='YYYYMMDD':
                date_str=f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"; fmt_date_std='%Y-%m-%d'
            elif fmt_date=='DD/MM/YYYY':
                p=raw_date.replace('-','/').split('/')
                date_str=f"{p[2]}-{p[1]}-{p[0]}"; fmt_date_std='%Y-%m-%d'
            else:
                date_str=raw_date; fmt_date_std=fmt_date
            combined=f"{date_str} {time_str}"
            try: return datetime.strptime(combined,f"{fmt_date_std} {fmt_time_std}").replace(tzinfo=timezone.utc)
            except Exception: pass
            try: return pd.to_datetime(combined, utc=True).to_pydatetime()
            except Exception: pass
            return None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# VIDEO METADATA
# ─────────────────────────────────────────────────────────────────────────────

# Regex per timecode HH:MM:SS o HH:MM:SS:FF (con eventuale ; per drop-frame)
_TC_RX = re.compile(r'^\s*(\d{1,2}):(\d{2}):(\d{2})(?:[:;](\d{1,3}))?\s*$')
# Regex per data ISO o tipica MediaInfo "UTC YYYY-MM-DD HH:MM:SS" o "YYYY-MM-DD HH:MM:SS"
_DT_RX = re.compile(r'(\d{4})[-/](\d{2})[-/](\d{2})[ T](\d{2}):(\d{2}):(\d{2})')


def _parse_tc_string(s):
    """Prova a estrarre (h,m,s) da una stringa tipo '11:49:56:00' o '11:49:56;00'."""
    if not s: return None
    m = _TC_RX.match(str(s).strip())
    if not m: return None
    try:
        h = int(m.group(1)); mm = int(m.group(2)); ss = int(m.group(3))
        if 0 <= h < 24 and 0 <= mm < 60 and 0 <= ss < 60:
            return (h, mm, ss)
    except Exception:
        return None
    return None


def _parse_dt_string(s):
    """Prova a estrarre datetime UTC da stringhe tipo 'UTC 2020-10-25 11:49:56'."""
    if not s: return None
    s2 = str(s).strip().replace('UTC ', '').strip()
    m = _DT_RX.search(s2)
    if not m: return None
    try:
        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                      int(m.group(4)), int(m.group(5)), int(m.group(6)),
                      tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _read_text_any_encoding(path):
    """Legge un file di testo decodificandolo come UTF-16 (BOM o LE) / UTF-8."""
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except Exception:
        return None
    for enc in ('utf-16', 'utf-16-le', 'utf-16-be', 'utf-8-sig', 'utf-8',
                'latin-1'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
        except Exception:
            continue
    return None


def _parse_mediainfo_text(text):
    """
    Parsa un blob testuale stile MediaInfo CLI (quello che produce
    `mediainfo file.mov` o il sidecar .mov.txt). Ritorna (ts_unix, tc_time, src)
    con la stessa convenzione di get_video_creation_time.
    """
    if not text: return None, None, None
    # Cerca prima una data completa (Encoded date / Tagged date / Recorded date)
    for key in ('Encoded date', 'Tagged date', 'Recorded date',
                'File creation date', 'Mastered date'):
        m = re.search(rf'{re.escape(key)}\s*:\s*([^\r\n]+)', text, re.IGNORECASE)
        if m:
            ts = _parse_dt_string(m.group(1))
            if ts is not None:
                return ts, None, f'sidecar: {key}'
    # Cerca poi il timecode "Time code of first frame : HH:MM:SS:FF"
    for key in ('Time code of first frame', 'Starting Time code',
                'Starting timecode', 'Time code'):
        for m in re.finditer(rf'{re.escape(key)}\s*:\s*([^\r\n]+)',
                             text, re.IGNORECASE):
            tc = _parse_tc_string(m.group(1))
            if tc:
                return None, tc, f'sidecar: {key}'
    return None, None, None


def _try_mediainfo_cli(video_path):
    """
    Lancia `mediainfo` o `MediaInfo.exe` come processo esterno se installato.
    Ritorna l'output testuale o None.
    """
    exe = shutil.which('mediainfo') or shutil.which('MediaInfo')
    if not exe:
        # Su Windows MediaInfo CLI viene spesso installato in Program Files
        for cand in (r'C:\Program Files\MediaInfo\MediaInfo.exe',
                     r'C:\Program Files (x86)\MediaInfo\MediaInfo.exe',
                     r'C:\Program Files\MediaInfo_CLI\MediaInfo.exe'):
            if os.path.isfile(cand):
                exe = cand; break
    if not exe: return None
    try:
        out = subprocess.run([exe, '--Output=Text', video_path],
                             capture_output=True, timeout=30)
        if out.returncode == 0:
            txt = out.stdout.decode('utf-8', errors='replace') \
                  or out.stdout.decode('utf-16', errors='replace')
            return txt
    except Exception:
        pass
    return None


def _scan_pymediainfo_attrs(mi):
    """
    Scansiona TUTTE le tracce e tutti gli attributi di una MediaInfo già
    parsata. Ritorna (ts_unix, tc_time, src) — il primo match utile.
    Robusto a rinominazioni di attributi tra versioni di pymediainfo.
    """
    # Pass 1: cerca attributi di tipo data sulla traccia General
    for track in mi.tracks:
        if (track.track_type or '').lower() == 'general':
            data = track.to_data() if hasattr(track, 'to_data') else {}
            for k, v in (data or {}).items():
                kl = k.lower()
                if any(x in kl for x in ('encoded_date', 'tagged_date',
                                         'recorded_date', 'file_creation',
                                         'mastered_date')):
                    ts = _parse_dt_string(v)
                    if ts is not None:
                        return ts, None, f'pymediainfo: {k}'
    # Pass 2: cerca timecode su tracce diverse da Video/Audio
    for track in mi.tracks:
        tt = (track.track_type or '').lower()
        if tt in ('other', 'time code', 'time_code'):
            data = track.to_data() if hasattr(track, 'to_data') else {}
            # Prova prima i nomi noti
            for k in ('time_code_of_first_frame', 'time_code_first_frame',
                      'starting_time_code', 'tc_of_first_frame',
                      'time_code_settings', 'time_code'):
                v = data.get(k) if data else getattr(track, k, None)
                tc = _parse_tc_string(v)
                if tc:
                    return None, tc, f'pymediainfo: {k}'
            # Poi scansiona tutti gli attributi stringa che contengono "time" o "tc"
            for k, v in (data or {}).items():
                if not isinstance(v, str): continue
                kl = k.lower()
                if 'time' not in kl and 'tc' not in kl: continue
                tc = _parse_tc_string(v)
                if tc:
                    return None, tc, f'pymediainfo: {k}'
    return None, None, None


def get_video_creation_time(video_path):
    """
    Restituisce (timestamp_unix, tc_time, source).
      timestamp_unix : float UTC se trovata data+ora completa, altrimenti None.
      tc_time        : (h,m,s) se trovato un timecode QuickTime (solo HH:MM:SS), altrimenti None.
      source         : stringa indicativa della sorgente.

    Strategia (in ordine):
      ① Sidecar testuale: <video>.mov.txt accanto al file (output `mediainfo` CLI)
      ② pymediainfo: encoded_date / tagged_date sul track General, poi scan TC su Other
      ③ Subprocess: chiama `mediainfo` CLI se installato e parsa l'output
      ④ Parser binario interno dei box ISOBMFF (tmcd track) per MOV/MP4
    """
    # ① Sidecar .mov.txt (o equivalente)
    base, ext = os.path.splitext(video_path)
    for sc in (video_path + '.txt', base + '.txt',
               base + '.mediainfo.txt', base + '.MediaInfo.txt'):
        if os.path.isfile(sc):
            txt = _read_text_any_encoding(sc)
            res = _parse_mediainfo_text(txt)
            if res[0] is not None or res[1] is not None:
                return res[0], res[1], res[2]

    # ② pymediainfo (libreria Python)
    if HAS_MEDIAINFO:
        try:
            mi = MediaInfo.parse(video_path)
            ts, tc, src = _scan_pymediainfo_attrs(mi)
            if ts is not None or tc is not None:
                return ts, tc, src
        except Exception:
            pass

    # ③ MediaInfo CLI come fallback
    txt = _try_mediainfo_cli(video_path)
    if txt:
        res = _parse_mediainfo_text(txt)
        if res[0] is not None or res[1] is not None:
            return res[0], res[1], (res[2] or 'mediainfo CLI')

    # ④ Parser binario del box `tmcd` per MOV/MP4
    try:
        tc = _parse_mov_timecode(video_path)
        if tc:
            h, m, s = tc
            return None, (h, m, s), f'TC binario: {h:02d}:{m:02d}:{s:02d}'
    except Exception:
        pass

    return None, None, 'metadata non disponibili'


def _parse_mov_timecode(video_path, max_scan=64*1024*1024):
    """
    Parser minimale dei box ISOBMFF (MOV/MP4) per estrarre il timecode QuickTime.
    Ritorna (h, m, s) o None. Limita la scansione a max_scan byte per file enormi.

    Logica: cerca una traccia il cui media handler sia 'tmcd' (Time Code).
    Nel sample della 'mdat' del tmcd (24 ore × 30 fps ≈ 32 bit) troviamo il numero
    iniziale di frame. Combinandolo col flag dropframe (tmcd box) e con il
    timescale della traccia (mdhd) otteniamo HH:MM:SS:FF.
    Implementazione semplificata: leggiamo il primo sample della tmcd track.
    """
    import struct
    BOX_HEADER = 8
    def read_box(f, end):
        pos = f.tell()
        if pos >= end - BOX_HEADER: return None
        hdr = f.read(BOX_HEADER)
        if len(hdr) < BOX_HEADER: return None
        size, btype = struct.unpack('>I4s', hdr)
        btype = btype.decode('ascii', errors='replace')
        if size == 1:
            ext = f.read(8)
            if len(ext) < 8: return None
            size = struct.unpack('>Q', ext)[0]
            data_start = pos + 16
        elif size == 0:
            size = end - pos
            data_start = pos + BOX_HEADER
        else:
            data_start = pos + BOX_HEADER
        return (btype, pos, size, data_start)

    def find_first(f, parent_end, target):
        """Cerca un box di tipo target a livello attuale."""
        while f.tell() < parent_end:
            box = read_box(f, parent_end)
            if not box: return None
            btype, pos, size, ds = box
            if btype == target:
                f.seek(ds); return (pos, size, ds, pos + size)
            f.seek(pos + size)
        return None

    def find_all(f, parent_end, target):
        results = []
        while f.tell() < parent_end:
            box = read_box(f, parent_end)
            if not box: break
            btype, pos, size, ds = box
            if btype == target:
                results.append((pos, size, ds, pos + size))
            f.seek(pos + size)
        return results

    fsize = os.path.getsize(video_path)
    with open(video_path, 'rb') as f:
        # Cerca moov a top-level
        moov = find_first(f, min(fsize, max_scan), 'moov')
        if not moov:
            f.seek(0); moov = find_first(f, fsize, 'moov')
        if not moov: return None
        _, _, moov_ds, moov_end = moov

        # Tutte le trak nella moov
        f.seek(moov_ds)
        traks = find_all(f, moov_end, 'trak')
        for _, _, trak_ds, trak_end in traks:
            # mdia
            f.seek(trak_ds)
            mdia = find_first(f, trak_end, 'mdia')
            if not mdia: continue
            _, _, mdia_ds, mdia_end = mdia

            # hdlr per identificare tmcd
            f.seek(mdia_ds)
            hdlr = find_first(f, mdia_end, 'hdlr')
            if not hdlr: continue
            _, _, hdlr_ds, hdlr_end = hdlr
            # versione+flags(4) + pre_defined(4) + handler_type(4)
            f.seek(hdlr_ds + 8)
            handler_type = f.read(4)
            if handler_type != b'tmcd': continue

            # mdhd per timescale (non strettamente necessario per HH:MM:SS, ma utile)
            f.seek(mdia_ds)
            mdhd = find_first(f, mdia_end, 'mdhd')
            timescale = 600
            if mdhd:
                _, _, mdhd_ds, _ = mdhd
                f.seek(mdhd_ds)
                vf = f.read(4)
                if len(vf) == 4:
                    version = vf[0]
                    if version == 1:
                        f.read(8 + 8)  # ctime, mtime
                        timescale = struct.unpack('>I', f.read(4))[0]
                    else:
                        f.read(4 + 4)
                        timescale = struct.unpack('>I', f.read(4))[0]

            # minf -> stbl -> stsd (per leggere fps tmcd) e stco/co64+stsz per il primo sample
            f.seek(mdia_ds)
            minf = find_first(f, mdia_end, 'minf')
            if not minf: continue
            _, _, minf_ds, minf_end = minf
            f.seek(minf_ds)
            stbl = find_first(f, minf_end, 'stbl')
            if not stbl: continue
            _, _, stbl_ds, stbl_end = stbl

            # stsd: leggi la timecode entry per ottenere fps e flags
            f.seek(stbl_ds)
            stsd = find_first(f, stbl_end, 'stsd')
            tmcd_fps = 30
            drop_frame = False
            if stsd:
                _, _, stsd_ds, stsd_end = stsd
                f.seek(stsd_ds)
                f.read(8)  # version+flags+entry_count
                # Prima entry
                entry_hdr = f.read(8)
                if len(entry_hdr) == 8:
                    e_size, e_type = struct.unpack('>I4s', entry_hdr)
                    if e_type == b'tmcd':
                        # 6 reserved + 2 data_reference_index + 4 reserved + 4 flags + 4 timescale + 4 frame_duration + 1 frames_per_second + 1 reserved
                        f.read(6 + 2 + 4)
                        flags = struct.unpack('>I', f.read(4))[0]
                        ts = struct.unpack('>I', f.read(4))[0]
                        fdur = struct.unpack('>I', f.read(4))[0]
                        nframes = struct.unpack('>B', f.read(1))[0]
                        if nframes > 0: tmcd_fps = nframes
                        drop_frame = bool(flags & 0x0001)

            # Trova il primo chunk offset (stco/co64) e leggi 4 byte (frame number)
            f.seek(stbl_ds)
            stco = find_first(f, stbl_end, 'stco')
            offset = None
            if stco:
                _, _, stco_ds, _ = stco
                f.seek(stco_ds)
                f.read(4)  # version+flags
                count = struct.unpack('>I', f.read(4))[0]
                if count >= 1:
                    offset = struct.unpack('>I', f.read(4))[0]
            else:
                f.seek(stbl_ds)
                co64 = find_first(f, stbl_end, 'co64')
                if co64:
                    _, _, co64_ds, _ = co64
                    f.seek(co64_ds)
                    f.read(4)
                    count = struct.unpack('>I', f.read(4))[0]
                    if count >= 1:
                        offset = struct.unpack('>Q', f.read(8))[0]
            if offset is None: continue

            # Leggi il primo sample (4 byte = frame number iniziale)
            f.seek(offset)
            sample = f.read(4)
            if len(sample) < 4: continue
            frame_num = struct.unpack('>I', sample)[0]

            # Converti frame_num in HH:MM:SS:FF
            fps = max(1, int(round(tmcd_fps)))
            # Per drop-frame NTSC il calcolo è più complesso; per l'app basta HH:MM:SS
            total_seconds, ff = divmod(frame_num, fps)
            h, rem = divmod(total_seconds, 3600)
            m, s = divmod(rem, 60)
            if 0 <= h < 24:
                return (int(h), int(m), int(s))
    return None


def parse_filename_pattern(filename, pattern):
    """
    Pattern semplificato: YYYY MM DD HH MM SS come segnaposti,
    * come carattere jolly, tutto il resto letterale.
    Esempi:
      pattern: YYYYMMDD_HHMMSS_*
      file:    20221012_085134_ERAY.mov
      → 2022-10-12 08:51:34
    """
    if not pattern:
        return None, 'pattern vuoto'
    name = os.path.splitext(os.path.basename(filename))[0]
    # Costruisci regex dal pattern
    rx = re.escape(pattern)
    rx = rx.replace(re.escape('YYYY'), r'(?P<Y>\d{4})')
    rx = rx.replace(re.escape('MM'),   r'(?P<M>\d{2})', 1)
    rx = rx.replace(re.escape('DD'),   r'(?P<D>\d{2})', 1)
    rx = rx.replace(re.escape('HH'),   r'(?P<h>\d{2})', 1)
    rx = rx.replace(re.escape('MM'),   r'(?P<m>\d{2})', 1)
    rx = rx.replace(re.escape('SS'),   r'(?P<s>\d{2})', 1)
    rx = rx.replace(re.escape('*'),    r'.*')
    rx = '^' + rx + '$'
    try:
        match = re.match(rx, name)
        if not match:
            return None, f'pattern non corrisponde a "{name}"'
        gd = match.groupdict()
        Y = int(gd.get('Y', 1970))
        M = int(gd.get('M', 1))
        D = int(gd.get('D', 1))
        h = int(gd.get('h', 0))
        m = int(gd.get('m', 0))
        s = int(gd.get('s', 0))
        dt = datetime(Y, M, D, h, m, s, tzinfo=timezone.utc)
        return dt.timestamp(), f'pattern nome file'
    except Exception as e:
        return None, f'errore pattern: {e}'


def detect_filename_timestamp(filename):
    """
    Tenta una detection generica di un timestamp (date+time) nel basename del
    file usando una serie di regex comuni:
      - 20221012_085134, 20221012-085134, 20221012T085134, 20221012 085134
      - 2022-10-12_08-51-34, 2022-10-12T08:51:34, 2022-10-12 08:51:34
      - 20221012085134 (senza separatore)
    Ritorna (unix_ts, matched_text, format_label) oppure (None, None, None).
    """
    name = os.path.basename(str(filename))
    # Rimuove eventuali estensioni multiple (.mov.txt → ridurre a .mov)
    name_noext = os.path.splitext(name)[0]
    candidates = [
        # YYYYMMDD<sep>HHMMSS  (sep ∈ _ - T space)
        (r'(?<!\d)(\d{4})(\d{2})(\d{2})[\s_T-](\d{2})(\d{2})(\d{2})(?!\d)',
         'YYYYMMDD<sep>HHMMSS'),
        # YYYY-MM-DD<sep>HH:MM:SS or YYYY-MM-DDTHH-MM-SS or YYYY-MM-DDTHH_MM_SS
        (r'(?<!\d)(\d{4})-(\d{2})-(\d{2})[\s_T](\d{2})[:\-_](\d{2})[:\-_](\d{2})(?!\d)',
         'YYYY-MM-DD<sep>HH:MM:SS'),
        # YYYY-MM-DD_HH-MM-SS (underscore + dashes between time fields)
        (r'(?<!\d)(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})(?!\d)',
         'YYYY-MM-DD_HH-MM-SS'),
        # YYYY/MM/DD HH:MM:SS
        (r'(?<!\d)(\d{4})/(\d{2})/(\d{2})[\sT](\d{2}):(\d{2}):(\d{2})(?!\d)',
         'YYYY/MM/DD HH:MM:SS'),
        # YYYYMMDDHHMMSS (no separator at all)
        (r'(?<!\d)(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?!\d)',
         'YYYYMMDDHHMMSS'),
    ]
    for rx, fmt in candidates:
        m = re.search(rx, name_noext)
        if m:
            try:
                Y, M, D, h, mi, s = (int(g) for g in m.groups())
                # Sanity check: data plausibile
                if 1990 <= Y <= 2100 and 1 <= M <= 12 and 1 <= D <= 31 \
                        and 0 <= h < 24 and 0 <= mi < 60 and 0 <= s < 60:
                    dt = datetime(Y, M, D, h, mi, s, tzinfo=timezone.utc)
                    return dt.timestamp(), m.group(0), fmt
            except Exception:
                continue
    return None, None, None


# ─────────────────────────────────────────────────────────────────────────────
# USBL
# ─────────────────────────────────────────────────────────────────────────────

def load_usbl(path, sep, has_header, ts_params, lat_col, lon_col, coord_fmt,
              depth_col, extra_cols, utm_zone=None, utm_north=True, excluded_cols=None):
    excluded_cols = excluded_cols or []
    header = 0 if has_header else None
    df = pd.read_csv(path, sep=sep, header=header, engine='python', on_bad_lines='skip')
    if not has_header:
        df.columns = [f"col_{i}" for i in range(len(df.columns))]
    else:
        df.columns = [str(c).strip() for c in df.columns]
    ts_list = []
    for _, row in df.iterrows():
        dt = parse_timestamp(row, **ts_params)
        ts_list.append(dt.timestamp() if dt else np.nan)
    df['unix_ts'] = ts_list
    if coord_fmt == 'UTM' and utm_zone:
        zone_num = int(str(utm_zone).replace('N','').replace('S','').strip())
        lats, lons = [], []
        for _, row in df.iterrows():
            try:
                la,lo = utm_to_dd(float(row[lon_col]),float(row[lat_col]),zone_num,utm_north)
                lats.append(la); lons.append(lo)
            except Exception:
                lats.append(np.nan); lons.append(np.nan)
        df['lat_dd']=lats; df['lon_dd']=lons
    else:
        lat_hem = _find_hemisphere(df, lat_col, 'lat')
        lon_hem = _find_hemisphere(df, lon_col, 'lon')
        def build(row, vcol, hcol):
            val = str(row[vcol]).strip().replace(',','.')
            if hcol:
                hem = str(row[hcol]).strip().upper()
                if hem in ('N','S','E','W') and not any(h in val.upper() for h in ('N','S','E','W')):
                    val = val+hem
            return val
        df['lat_dd'] = df.apply(lambda r: parse_coord(build(r,lat_col,lat_hem), coord_fmt), axis=1)
        df['lon_dd'] = df.apply(lambda r: parse_coord(build(r,lon_col,lon_hem), coord_fmt), axis=1)
    df['depth'] = pd.to_numeric(df[depth_col], errors='coerce') if depth_col and depth_col in df.columns else np.nan
    for col in extra_cols:
        if col not in df.columns: df[col] = np.nan
    return df.dropna(subset=['unix_ts']).sort_values('unix_ts').reset_index(drop=True)


def interpolate_usbl(usbl_df, target_unix, extra_cols, window_sec=10.0):
    ts=usbl_df['unix_ts'].values; idx=np.searchsorted(ts, target_unix)
    if idx==0: row=usbl_df.iloc[0]
    elif idx>=len(usbl_df): row=usbl_df.iloc[-1]
    else:
        t0,t1=ts[idx-1],ts[idx]
        if min(abs(target_unix-t0),abs(target_unix-t1))>window_sec: return None
        alpha=(target_unix-t0)/(t1-t0) if t1!=t0 else 0.0
        r0,r1=usbl_df.iloc[idx-1],usbl_df.iloc[idx]
        result={'lat_dd':r0['lat_dd']+alpha*(r1['lat_dd']-r0['lat_dd']),
                'lon_dd':r0['lon_dd']+alpha*(r1['lon_dd']-r0['lon_dd']),
                'depth': r0['depth'] +alpha*(r1['depth'] -r0['depth'])}
        for col in extra_cols:
            try: result[col]=float(r0[col])+alpha*(float(r1[col])-float(r0[col]))
            except: result[col]=r0[col]
        return result
    return {'lat_dd':row['lat_dd'],'lon_dd':row['lon_dd'],'depth':row['depth'],
            **{col:row.get(col,np.nan) for col in extra_cols}}


# ─────────────────────────────────────────────────────────────────────────────
# CTD
# ─────────────────────────────────────────────────────────────────────────────

def load_ctd(path, sep, has_header, ts_params, depth_col, param_cols,
             sync_mode, ctd_ts_offset=0.0):
    header = 0 if has_header else None
    df = pd.read_csv(path, sep=sep, header=header, engine='python',
                     on_bad_lines='skip', comment='#')
    if not has_header:
        df.columns = [f"col_{i}" for i in range(len(df.columns))]
    else:
        df.columns = [str(c).strip() for c in df.columns]
    if sync_mode == 'time':
        ts_list = []
        for _, row in df.iterrows():
            dt = parse_timestamp(row, **ts_params)
            ts_list.append((dt.timestamp()+ctd_ts_offset) if dt else np.nan)
        df['unix_ts'] = ts_list
        df = df.sort_values('unix_ts').reset_index(drop=True)
    if depth_col and depth_col in df.columns:
        df['_depth_key'] = pd.to_numeric(df[depth_col], errors='coerce')
        if sync_mode == 'depth':
            df = df.sort_values('_depth_key').reset_index(drop=True)
    return df


def interpolate_ctd(ctd_df, target, sync_mode, param_cols, window_sec=10.0):
    key_col = 'unix_ts' if sync_mode=='time' else '_depth_key'
    if key_col not in ctd_df.columns: return {}
    if sync_mode == 'depth':
        # Match su |depth| per gestire segno opposto USBL/CTD (es. USBL altitudine
        # negativa, CTD positiva). I keys per searchsorted devono essere ordinati,
        # quindi calcoliamo abs e ri-ordiniamo localmente.
        raw_keys = ctd_df[key_col].values
        abs_keys = np.abs(raw_keys)
        order = np.argsort(abs_keys)
        keys = abs_keys[order]
        target_for_search = abs(float(target)) if target is not None and not pd.isna(target) else target
        # Map: indice locale → indice originale nel df
        def to_orig(i): return int(order[i])
    else:
        raw_keys = ctd_df[key_col].values
        keys = raw_keys
        target_for_search = target
        def to_orig(i): return i
    idx = np.searchsorted(keys, target_for_search)
    if idx == 0:
        row = ctd_df.iloc[to_orig(0)]
        return {c: row[c] for c in param_cols if c in ctd_df.columns}
    if idx >= len(ctd_df):
        row = ctd_df.iloc[to_orig(len(ctd_df)-1)]
        return {c: row[c] for c in param_cols if c in ctd_df.columns}
    t0, t1 = keys[idx-1], keys[idx]
    if sync_mode == 'time' and min(abs(target-t0), abs(target-t1)) > window_sec:
        return {}
    alpha = (target_for_search-t0)/(t1-t0) if t1 != t0 else 0.0
    r0 = ctd_df.iloc[to_orig(idx-1)]; r1 = ctd_df.iloc[to_orig(idx)]
    result = {}
    for col in param_cols:
        if col not in ctd_df.columns: continue
        try: result[col] = float(r0[col]) + alpha*(float(r1[col])-float(r0[col]))
        except: result[col] = r0[col]
    return result


# ─────────────────────────────────────────────────────────────────────────────
# QUALITÀ / OVERLAY
# ─────────────────────────────────────────────────────────────────────────────

def frame_quality(frame):
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray,cv2.CV_64F).var(), gray.mean()

def is_problematic(blur,brightness,blur_thresh=50.0,dark_thresh=30.0,bright_thresh=230.0,lang='it'):
    w=[]
    if blur<blur_thresh: w.append(_L('warn_blur',lang))
    if brightness<dark_thresh: w.append(_L('warn_dark',lang))
    if brightness>bright_thresh: w.append(_L('warn_bright',lang))
    return ', '.join(w)

def draw_overlay(frame,fields_dict,position='bottom_left',font_size=28,color=(255,255,255),bg_style='rect'):
    if not fields_dict: return frame
    h,w=frame.shape[:2]; font=cv2.FONT_HERSHEY_SIMPLEX
    scale=font_size/28.0; thick=max(1,int(scale*1.5)); line_h=int(font_size*1.4); margin=12
    lines=[f"{k}: {v}" for k,v in fields_dict.items()]
    text_w=max(cv2.getTextSize(l,font,scale,thick)[0][0] for l in lines)
    tbh=line_h*len(lines)
    if   position=='bottom_left':  x0,y0=margin,h-margin-tbh
    elif position=='bottom_right': x0,y0=w-margin-text_w,h-margin-tbh
    elif position=='top_left':     x0,y0=margin,margin
    else:                          x0,y0=w-margin-text_w,margin
    if bg_style=='rect':
        ov=frame.copy()
        cv2.rectangle(ov,(x0-6,y0-6),(x0+text_w+6,y0+tbh+6),(0,0,0),-1)
        cv2.addWeighted(ov,0.55,frame,0.45,0,frame)
    for i,line in enumerate(lines):
        y=y0+i*line_h+line_h-4
        if bg_style=='shadow': cv2.putText(frame,line,(x0+2,y+2),font,scale,(0,0,0),thick+1,cv2.LINE_AA)
        cv2.putText(frame,line,(x0,y),font,scale,color,thick,cv2.LINE_AA)
    return frame


# ─────────────────────────────────────────────────────────────────────────────
# ESTRAZIONE
# ─────────────────────────────────────────────────────────────────────────────

def extract_frames(video_path, output_dir, dive_name, video_ts_offset,
                   extract_from, extract_to,
                   usbl_df, usbl_extra_cols, excluded_usbl_cols,
                   ctd_df, ctd_sync_mode, ctd_param_cols, ctd_ts_offset,
                   ctd_depth_window,
                   custom_cols, interval_sec, assoc_window,
                   img_fmt, img_quality, overlay_cfg,
                   blur_thresh, dark_thresh, bright_thresh,
                   use_cuda, lang, progress_q, log_q, stop_event):

    os.makedirs(output_dir, exist_ok=True)
    cap=cv2.VideoCapture(video_path, cv2.CAP_FFMPEG if (use_cuda and HAS_CUDA) else cv2.CAP_ANY)
    log_q.put(('ok' if (use_cuda and HAS_CUDA) else 'info',
               _L('log_cuda_ok',lang,n=CUDA_COUNT) if (use_cuda and HAS_CUDA) else _L('log_cpu',lang)))
    fps=cap.get(cv2.CAP_PROP_FPS); total_frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps<=0: log_q.put(('err','FPS non leggibile.')); cap.release(); return
    duration=total_frames/fps
    log_q.put(('ok',_L('log_video_ok',lang,fps=fps,dur=duration,tot=total_frames)))

    t_start = max(0.0, extract_from)
    t_end   = min(duration, extract_to) if extract_to > 0 else duration
    frame_times = np.arange(t_start, t_end, interval_sec)
    n_frames    = len(frame_times)
    log_q.put(('ok',_L('log_frames_plan',lang,n=n_frames,iv=interval_sec)))

    # Filtra CTD se sync_mode='depth' e finestra impostata
    if ctd_df is not None and ctd_sync_mode == 'depth' and ctd_depth_window:
        idx_from, idx_to = ctd_depth_window
        if idx_from is not None and idx_to is not None:
            ctd_df = ctd_df.iloc[idx_from:idx_to+1].sort_values('_depth_key').reset_index(drop=True)
            log_q.put(('ok', f'CTD filtrata: {len(ctd_df)} righe (window selezionata)'))

    ext={'PNG':'.png','JPEG':'.jpg','TIFF':'.tif'}[img_fmt]
    enc_params=([cv2.IMWRITE_JPEG_QUALITY,img_quality] if img_fmt=='JPEG'
                else [cv2.IMWRITE_PNG_COMPRESSION,0] if img_fmt=='PNG' else [])
    rows_csv=[]; frame_counter=0
    write_pool=ThreadPoolExecutor(max_workers=4); futures=[]

    for i,t_video in enumerate(frame_times):
        if stop_event.is_set():
            log_q.put(('warn',_L('log_stopped',lang))); break
        cap.set(cv2.CAP_PROP_POS_MSEC, t_video * 1000.0)
        ret,frame=cap.read()
        if not ret:
            log_q.put(('warn',_L('log_frame_skip',lang,i=i+1))); continue
        t_abs=video_ts_offset+t_video
        dt_iso=datetime.fromtimestamp(t_abs,tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        unix_t=int(t_abs)
        usbl_vals = interpolate_usbl(usbl_df,t_abs,usbl_extra_cols,assoc_window) if usbl_df is not None else None
        if usbl_df is not None and usbl_vals is None:
            log_q.put(('warn',f'Frame {i+1}: fuori finestra USBL, skip')); continue
        lat = usbl_vals['lat_dd'] if usbl_vals else np.nan
        lon = usbl_vals['lon_dd'] if usbl_vals else np.nan
        depth = usbl_vals['depth'] if usbl_vals else np.nan
        ctd_vals={}
        if ctd_df is not None:
            try:
                tgt=(t_abs+ctd_ts_offset) if ctd_sync_mode=='time' else depth
                skip_ctd = (ctd_sync_mode=='depth' and
                            (depth is None or (isinstance(depth,float) and np.isnan(depth))))
                if not skip_ctd:
                    ctd_vals=interpolate_ctd(ctd_df,tgt,ctd_sync_mode,ctd_param_cols,assoc_window)
            except Exception as e:
                if i==0:
                    log_q.put(('warn',f'CTD lookup error (frame {i+1}): {e}'))
        blur,brightness=frame_quality(frame)
        warning=is_problematic(blur,brightness,blur_thresh,dark_thresh,bright_thresh,lang)
        frame_counter+=1
        img_name=f"image{frame_counter:04d}{ext}"
        img_path=os.path.join(output_dir,img_name)
        if overlay_cfg.get('enabled'):
            fields={}
            if overlay_cfg.get('show_time'):   fields[_L('ovl_field_time',lang)]=dt_iso
            if overlay_cfg.get('show_depth') and not np.isnan(depth):  fields[_L('ovl_field_depth',lang)]=f"{depth:.1f} m"
            if overlay_cfg.get('show_latlon') and not np.isnan(lat):   fields[_L('ovl_field_pos',lang)]=f"{lat:.5f}°N {lon:.5f}°E"
            if overlay_cfg.get('show_dive'):   fields[_L('ovl_field_dive',lang)]=dive_name
            for p in overlay_cfg.get('ctd_params',[]):
                if p in ctd_vals: fields[p]=f"{ctd_vals[p]:.2f}"
            frame=draw_overlay(frame,fields,position=overlay_cfg.get('position','bottom_left'),
                               font_size=overlay_cfg.get('font_size',28),
                               color=overlay_cfg.get('color',(255,255,255)),
                               bg_style=overlay_cfg.get('bg_style','rect'))
        futures.append(write_pool.submit(cv2.imwrite,img_path,frame.copy(),enc_params))
        row={'image':img_name,'dive':dive_name,
             'time_video':dt_iso,'UNIXtime_video':unix_t,
             'depth_USBL':round(float(depth),2) if not np.isnan(depth) else '',
             'Lat_USBL':round(lat,6) if not np.isnan(lat) else '',
             'Long_USBL':round(lon,6) if not np.isnan(lon) else ''}
        for cn,cv_ in custom_cols.items(): row[cn]=cv_
        for col in usbl_extra_cols:
            if col in excluded_usbl_cols: continue
            v=usbl_vals.get(col,np.nan) if usbl_vals else np.nan
            row[f"{col}_USBL"]=round(float(v),4) if isinstance(v,float) and not np.isnan(v) else v
        # Aggiungi time_USBL e ΔT_USBL se disponibile
        if usbl_vals is not None and usbl_df is not None:
            ts_arr=usbl_df['unix_ts'].values
            idx_u=np.searchsorted(ts_arr,t_abs)
            if idx_u>=len(ts_arr): idx_u=len(ts_arr)-1
            row['time_USBL']=datetime.fromtimestamp(ts_arr[idx_u],tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            row['dt_USBL_s']=round(abs(t_abs-ts_arr[idx_u]),2)
        # CTD columns con suffisso _CTD
        if ctd_df is not None:
            for col in ctd_param_cols:
                v=ctd_vals.get(col,np.nan)
                row[f"{col}_CTD"]=round(float(v),4) if isinstance(v,float) and not np.isnan(v) else v
            # time/depth CTD di riferimento + ΔT
            if ctd_sync_mode=='time' and 'unix_ts' in ctd_df.columns:
                ctd_ts=ctd_df['unix_ts'].values
                idx_c=np.searchsorted(ctd_ts,t_abs+ctd_ts_offset)
                if idx_c>=len(ctd_ts): idx_c=len(ctd_ts)-1
                row['time_CTD']=datetime.fromtimestamp(ctd_ts[idx_c],tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
                row['dt_CTD_s']=round(abs((t_abs+ctd_ts_offset)-ctd_ts[idx_c]),2)
                if '_depth_key' in ctd_df.columns:
                    try: row['depth_CTD']=round(float(ctd_df.iloc[idx_c]['_depth_key']),2)
                    except: row['depth_CTD']=''
            elif ctd_sync_mode=='depth' and '_depth_key' in ctd_df.columns and not np.isnan(depth):
                ctd_depths=ctd_df['_depth_key'].values
                idx_c=int(np.argmin(np.abs(ctd_depths-depth)))
                row['depth_CTD']=round(float(ctd_depths[idx_c]),2)
                row['dt_CTD_m']=round(abs(depth-ctd_depths[idx_c]),2)
        row['blur_score']=round(blur,1); row['brightness']=round(brightness,1); row['warning']=warning
        rows_csv.append(row)
        progress_q.put(int((i+1)/n_frames*100))
        if warning: log_q.put(('warn',f"{img_name} ⚠ {warning}"))
        elif i%50==0:
            if not np.isnan(lat):
                log_q.put(('ok',_L('log_frame_ok',lang,img=img_name,lat=lat,lon=lon,d=depth)))

    for f in as_completed(futures): pass
    write_pool.shutdown(wait=True); cap.release()

    if rows_csv:
        csv_path=os.path.join(output_dir,f"{dive_name}.csv")
        pd.DataFrame(rows_csv).to_csv(csv_path,index=False)
        log_q.put(('ok',_L('log_csv_saved',lang,path=csv_path)))
        if HAS_GEOPANDAS and usbl_df is not None:
            df_out=pd.DataFrame(rows_csv)
            df_geo = df_out[(df_out['Lat_USBL']!='') & (df_out['Long_USBL']!='')]
            if len(df_geo):
                gdf=gpd.GeoDataFrame(df_geo,geometry=[Point(r['Long_USBL'],r['Lat_USBL']) for _,r in df_geo.iterrows()],crs='EPSG:4326')
                gdf.to_file(os.path.join(output_dir,f"{dive_name}.shp"))
                log_q.put(('ok',_L('log_shp_saved',lang,path=os.path.join(output_dir,f"{dive_name}.shp"))))
        with open(os.path.join(output_dir,f"{dive_name}_session.json"),'w') as f:
            json.dump(dict(date=datetime.now().isoformat(),dive=dive_name,video=video_path,
                           video_ts_offset=video_ts_offset,extract_from=extract_from,
                           extract_to=extract_to,interval_s=interval_sec,frames=frame_counter,
                           output_dir=output_dir),f,indent=2)
        log_q.put(('ok',_L('log_session_saved',lang)))
    progress_q.put(100)
    log_q.put(('ok',_L('log_done',lang,n=frame_counter)))



# ─────────────────────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────────────────────

class ROVSyncTool(tk.Tk):

    C={'bg':'#1e1e2e','panel':'#2a2a3e','border':'#45475a','fg':'#cdd6f4',
       'blue':'#89b4fa','green':'#a6e3a1','yellow':'#f9e2af','red':'#f38ba8',
       'purple':'#cba6f7','gray':'#6c7086','entry':'#313244'}

    APP_NAME    = "HaBB DiveSync"
    APP_VERSION = "1.0"

    def __init__(self):
        super().__init__()
        self.title(f"{self.APP_NAME} v{self.APP_VERSION}")
        self.resizable(True,True); self.geometry("1000x880"); self.configure(bg=self.C['bg'])
        self.lang='en'

        # File paths
        self.video_path=tk.StringVar(); self.usbl_path=tk.StringVar()
        self.ctd_path=tk.StringVar(); self.output_dir=tk.StringVar()
        self.dive_name=tk.StringVar(value='ROV01')
        self.usbl_sep=tk.StringVar(value=','); self.ctd_sep=tk.StringVar(value=',')
        self.usbl_header=tk.BooleanVar(value=True); self.ctd_header=tk.BooleanVar(value=True)
        self.use_cuda=tk.BooleanVar(value=HAS_CUDA); self.profile_path=tk.StringVar()

        # Filename pattern for video creation time
        self.fn_pattern=tk.StringVar(value='YYYYMMDD_HHMMSS_*')

        # USBL mapping
        self.ts_mode=tk.StringVar(value='split'); self.ts_col_uni=tk.StringVar()
        self.ts_fmt_uni=tk.StringVar(value=''); self.ts_col_date=tk.StringVar()
        self.ts_fmt_date=tk.StringVar(value='DD/MM/YYYY'); self.ts_col_time=tk.StringVar()
        self.ts_fmt_time=tk.StringVar(value='HH:MM:SS'); self.coord_fmt=tk.StringVar(value='DD')
        self.lat_col=tk.StringVar(); self.lon_col=tk.StringVar(); self.depth_col=tk.StringVar()
        self.utm_zone=tk.StringVar(value='36'); self.utm_north=tk.BooleanVar(value=True)

        # CTD mapping
        self.ctd_sync_mode=tk.StringVar(value='time')
        self.ctd_ts_col_uni=tk.StringVar(); self.ctd_ts_fmt_uni=tk.StringVar(value='')
        self.ctd_ts_col_date=tk.StringVar(); self.ctd_ts_fmt_date=tk.StringVar(value='DD/MM/YYYY')
        self.ctd_ts_col_time=tk.StringVar(); self.ctd_ts_fmt_time=tk.StringVar(value='HH:MM:SS')
        self.ctd_ts_mode=tk.StringVar(value='unified')
        self.ctd_depth_col=tk.StringVar()

        # Sync vars
        self.video_pos_var=tk.DoubleVar(value=0.0)
        self.video_meta_ts_str=tk.StringVar(value='—')
        self.video_meta_source=tk.StringVar(value='')
        self.video_ts_corrected=tk.StringVar()
        self.video_depth_manual=tk.StringVar()
        self.ctd_ts_corrected=tk.StringVar()
        self.ctd_ts_offset=tk.DoubleVar(value=0.0)
        self.video_delay=tk.DoubleVar(value=0.0)
        # Tolleranza differenza profondità CTD vs USBL (m): blocca extraction se superata
        self.ctd_depth_tol=tk.DoubleVar(value=5.0)
        # Status validazione CTD: aggiornato in _build_alignment_table
        self.ctd_depth_status=tk.StringVar(value='')
        self._ctd_depth_ok=True
        # Offset cumulato applicato manualmente al CTD unix_ts (per il pulsante "Apply CTD time only")
        self._ctd_manual_unix_shift=0.0
        # Stato grafico overlay USBL/CTD depth (drag interattivo)
        self._overlay_drag_active=False
        self._overlay_drag_x0=0
        self._overlay_pending_shift=0.0   # shift in secondi, in attesa di "Apply"
        self._overlay_shift_at_press=0.0
        self._overlay_t_min=None; self._overlay_t_max=None
        self._overlay_pix_per_sec=1.0

        self.extract_from=tk.DoubleVar(value=0.0)
        self.extract_to=tk.DoubleVar(value=0.0)
        self.interval_sec=tk.DoubleVar(value=5.0)
        self.assoc_window=tk.DoubleVar(value=5.0)
        self.img_fmt=tk.StringVar(value='PNG'); self.img_quality=tk.IntVar(value=95)
        self.blur_thresh=tk.DoubleVar(value=50.0); self.dark_thresh=tk.DoubleVar(value=30.0)
        self.bright_thresh=tk.DoubleVar(value=230.0)
        self.ovl_enabled=tk.BooleanVar(value=True); self.ovl_time=tk.BooleanVar(value=True)
        self.ovl_depth=tk.BooleanVar(value=True); self.ovl_latlon=tk.BooleanVar(value=False)
        self.ovl_dive=tk.BooleanVar(value=False); self.ovl_pos=tk.StringVar(value='bottom_left')
        self.ovl_fontsize=tk.IntVar(value=28); self.ovl_color=tk.StringVar(value='white')
        self.ovl_bg=tk.StringVar(value='rect')

        # CTD depth window selection (per sync 'depth')
        self.ctd_depth_window_idx=(None,None)  # (from_idx, to_idx) nel df CTD ordinato per indice

        # Stato dati
        self.usbl_df=None; self.usbl_cols=[]; self.usbl_extra=[]; self.excluded_usbl=set()
        self.ctd_df=None; self.ctd_df_validated=None; self.ctd_cols=[]; self.ctd_selected=[]
        self.custom_col_rows=[]; self._raw_usbl_df=None
        self._usbl_combos=[]; self._ctd_combos=[]
        self._video_duration=0.0; self._video_fps=25.0
        self._video_meta_unix=None
        self._rebuildable=[]
        self.stop_event=threading.Event(); self.progress_q=queue.Queue(); self.log_q=queue.Queue()

        self._build_ui(); self._update_hw_label()

    # ── stile ────────────────────────────────────────────────────────────────
    def _style(self):
        s=ttk.Style(self); s.theme_use('clam')
        bg,fg=self.C['bg'],self.C['fg']
        s.configure('TFrame',background=bg)
        s.configure('TLabel',background=bg,foreground=fg,font=('Segoe UI',10))
        s.configure('TNotebook',background=bg,tabmargins=[0,0,0,0])
        s.configure('TNotebook.Tab',background=bg,foreground=self.C['gray'],
                    padding=[14,6],font=('Segoe UI',10))
        s.map('TNotebook.Tab',background=[('selected',self.C['panel'])],
                              foreground=[('selected',self.C['blue'])])
        s.configure('TCombobox',fieldbackground=self.C['entry'],foreground=fg,
                    selectbackground=self.C['entry'],selectforeground=fg)
        s.map('TCombobox',fieldbackground=[('readonly',self.C['entry'])],
                          foreground=[('readonly',fg)],
                          selectbackground=[('readonly',self.C['entry'])],
                          selectforeground=[('readonly',fg)])
        s.configure('TCheckbutton',background=bg,foreground=fg)
        s.configure('TRadiobutton',background=bg,foreground=fg)
        s.configure('Horizontal.TProgressbar',troughcolor=self.C['entry'],
                    background=self.C['blue'],bordercolor=bg)
        s.configure('TLabelframe',background=bg,foreground=self.C['blue'],
                    bordercolor=self.C['border'])
        s.configure('TLabelframe.Label',background=bg,foreground=self.C['blue'],
                    font=('Segoe UI',10,'bold'))
        s.configure('TScrollbar',background=self.C['entry'],troughcolor=bg)
        s.configure('Treeview',background=self.C['entry'],foreground=fg,
                    fieldbackground=self.C['entry'],rowheight=20)
        s.configure('Treeview.Heading',background=self.C['panel'],foreground=self.C['blue'])

    # ── helpers ──────────────────────────────────────────────────────────────
    def _lbl(self,p,text,color=None,bold=False,size=10):
        return tk.Label(p,text=text,bg=self.C['bg'],fg=color or self.C['fg'],
                        font=('Segoe UI',size,'bold' if bold else ''))

    def _entry(self,p,var,width=20):
        return tk.Entry(p,textvariable=var,width=width,bg=self.C['entry'],
                        fg=self.C['fg'],insertbackground=self.C['fg'],relief='flat',bd=4)

    def _combo(self,p,var,values,width=16):
        self._style()
        return ttk.Combobox(p,textvariable=var,values=values,width=width,state='readonly')

    def _col_dd(self,p,var,width=32):
        # width = larghezza minima (caratteri); il dropdown visualizza il testo completo
        c=ttk.Combobox(p,textvariable=var,values=self.usbl_cols or ['—'],
                       width=width,state='readonly')
        self._usbl_combos.append(c); return c

    def _ctd_dd(self,p,var,width=32):
        c=ttk.Combobox(p,textvariable=var,values=self.ctd_cols or ['—'],
                       width=width,state='readonly')
        self._ctd_combos.append(c); return c

    def _btn(self,p,text,cmd,accent=None):
        return tk.Button(p,text=text,command=cmd,bg=self.C['entry'],
                         fg=accent or self.C['fg'],activebackground=self.C['border'],
                         activeforeground=accent or self.C['fg'],
                         relief='flat',bd=0,padx=10,pady=4,
                         font=('Segoe UI',10),cursor='hand2')

    def _sep(self,p):
        return tk.Frame(p,bg=self.C['border'],height=1)

    def _attach_tooltip(self, widget, text):
        """Tooltip on hover."""
        tip = {'win': None}
        def show(e):
            if tip['win'] is not None: return
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            tw = tk.Toplevel(widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            tk.Label(tw, text=text, bg='#1a1a2e', fg=self.C['fg'],
                     relief='solid', bd=1, padx=8, pady=4,
                     font=('Segoe UI', 9), wraplength=380,
                     justify='left').pack()
            tip['win'] = tw
        def hide(e):
            if tip['win'] is not None:
                tip['win'].destroy(); tip['win'] = None
        widget.bind('<Enter>', show)
        widget.bind('<Leave>', hide)

    def _scrollable(self,parent):
        # Container con due scrollbar (verticale + orizzontale) per il contenuto
        wrap = tk.Frame(parent, bg=self.C['bg'])
        wrap.pack(fill='both', expand=True)
        canvas = tk.Canvas(wrap, bg=self.C['bg'], highlightthickness=0)
        vsb = ttk.Scrollbar(wrap, orient='vertical', command=canvas.yview)
        hsb = ttk.Scrollbar(wrap, orient='horizontal', command=canvas.xview)
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        # Layout via grid: scrollbar verticale a destra, orizzontale in basso
        canvas.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)

        inner = tk.Frame(canvas, bg=self.C['bg'])
        wid = canvas.create_window((0,0), window=inner, anchor='nw')

        def _on_inner_config(e):
            # Aggiorna scrollregion. Se il contenuto è più stretto del canvas,
            # mostra/nasconde la scrollbar orizzontale.
            canvas.configure(scrollregion=canvas.bbox('all'))
        inner.bind('<Configure>', _on_inner_config)

        def _on_canvas_config(e):
            # Larghezza minima del contenuto = larghezza canvas, ma se il contenuto
            # è naturalmente più largo lascia che si estenda (e abilita hscroll).
            req = inner.winfo_reqwidth()
            target = max(e.width, req)
            canvas.itemconfig(wid, width=target)
            # Mostra hsb solo se serve
            if req > e.width:
                if not hsb.winfo_ismapped():
                    hsb.grid(row=1, column=0, sticky='ew')
            else:
                if hsb.winfo_ismapped():
                    hsb.grid_remove()
        canvas.bind('<Configure>', _on_canvas_config)

        # Mouse wheel: verticale (default), Shift+wheel = orizzontale
        def _mw_v(e):
            try: canvas.yview_scroll(int(-1*(e.delta/120)),'units')
            except: pass
        def _mw_h(e):
            try: canvas.xview_scroll(int(-1*(e.delta/120)),'units')
            except: pass
        canvas.bind_all('<MouseWheel>', _mw_v)
        canvas.bind_all('<Shift-MouseWheel>', _mw_h)
        # Linux (X11) wheel events
        canvas.bind_all('<Button-4>', lambda e: canvas.yview_scroll(-1,'units'))
        canvas.bind_all('<Button-5>', lambda e: canvas.yview_scroll(1,'units'))
        canvas.bind_all('<Shift-Button-4>', lambda e: canvas.xview_scroll(-1,'units'))
        canvas.bind_all('<Shift-Button-5>', lambda e: canvas.xview_scroll(1,'units'))
        return inner

    # ── build UI ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        self._style(); self._rebuildable=[]; self._usbl_combos=[]; self._ctd_combos=[]
        tb=tk.Frame(self,bg='#181825'); tb.pack(fill='x')
        tk.Label(tb,text=f"🎬  {self.APP_NAME} v{self.APP_VERSION}",
                 bg='#181825',fg=self.C['blue'],
                 font=('Segoe UI',13,'bold')).pack(side='left',padx=14,pady=8)
        self._load_habb_logo(tb)
        self.hw_label=tk.Label(tb,text='',bg='#181825',fg=self.C['gray'],font=('Segoe UI',9))
        self.hw_label.pack(side='right',padx=14)
        top=tk.Frame(self,bg=self.C['bg']); top.pack(fill='x',padx=10,pady=(6,0))
        self._lang_var=tk.StringVar(value='EN — English')
        tk.Label(top,text=_L('lang_label',self.lang),bg=self.C['bg'],fg=self.C['gray'],
                 font=('Segoe UI',10)).pack(side='left')
        lc=ttk.Combobox(top,textvariable=self._lang_var,
                         values=['IT — Italiano','EN — English'],width=14,state='readonly')
        lc.pack(side='left',padx=(4,16)); lc.bind('<<ComboboxSelected>>',self._change_lang)
        self._btn(top,_L('about',self.lang),self._show_about).pack(side='right',padx=4)
        self._profile_bar=tk.Frame(top,bg=self.C['bg'])
        self._profile_bar.pack(side='left',fill='x',expand=True)
        self._build_profile_bar()
        self._sep(self).pack(fill='x',padx=10,pady=5)
        self._build_notebook()

    def _find_habb_logo(self, prefer_raster=True):
        """Cerca il file logo nella cartella `Logos/` accanto allo script o
        all'eseguibile. Restituisce il path al primo file trovato."""
        try:
            import sys
            base_dirs = []
            if getattr(sys, 'frozen', False):
                base_dirs.append(os.path.dirname(sys.executable))
            base_dirs.append(os.path.dirname(os.path.abspath(__file__)))
            base_dirs.append(os.getcwd())
            candidates_raster = [
                'Logos/HaBB logo.jpg', 'Logos/HaBB logo (2).jpg',
                'Logos/HaBB_logo.png', 'Logos/habb_logo.png',
                'Logos/HaBB_logo.jpg', 'Logos/habb_logo.jpg',
                'logos/HaBB logo.jpg', 'logos/HaBB logo (2).jpg',
            ]
            candidates_vector = ['Logos/habb_logo.svg', 'logos/habb_logo.svg']
            order = (candidates_raster + candidates_vector) if prefer_raster else \
                    (candidates_vector + candidates_raster)
            for bd in base_dirs:
                for c in order:
                    p = os.path.join(bd, c)
                    if os.path.isfile(p):
                        return p
        except Exception:
            pass
        return None

    def _load_habb_logo_image(self, target_size):
        """Carica il logo HaBB ridimensionato a `target_size` = (w,h).
        Ritorna un PIL.Image o None. Per .svg richiede cairosvg (opzionale)."""
        path = self._find_habb_logo(prefer_raster=True)
        if not path: return None
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext == '.svg':
                try:
                    import cairosvg
                    png_bytes = cairosvg.svg2png(url=path,
                                                 output_width=target_size[0],
                                                 output_height=target_size[1])
                    return Image.open(io.BytesIO(png_bytes)).convert('RGBA')
                except ImportError:
                    return None
            img = Image.open(path)
            img.thumbnail(target_size, Image.LANCZOS)
            return img
        except Exception:
            return None

    def _load_habb_logo(self, parent):
        """Logo nella topbar (piccolo)."""
        img = self._load_habb_logo_image((140, 44))
        if img is not None:
            self._habb_img = ImageTk.PhotoImage(img)
            tk.Label(parent, image=self._habb_img, bg='#181825').pack(side='left', padx=10)
        else:
            tk.Label(parent, text="HaBB | KAUST", bg='#181825', fg='#00b8a0',
                     font=('Segoe UI', 9, 'bold')).pack(side='left', padx=10)

    def _show_about(self):
        L=self.lang; win=tk.Toplevel(self)
        win.title(_L('about_title',L)); win.configure(bg=self.C['bg'])
        win.geometry("520x440"); win.resizable(False,False)
        # Logo grande nell'About
        big_img = self._load_habb_logo_image((280, 110))
        if big_img is not None:
            self._habb_about = ImageTk.PhotoImage(big_img)
            tk.Label(win, image=self._habb_about, bg=self.C['bg']).pack(pady=(20, 8))
        else:
            tk.Label(win, text="HaBB — Habitat and Benthic Biodiversity",
                     bg=self.C['bg'], fg='#00b8a0',
                     font=('Segoe UI', 12, 'bold')).pack(pady=(20, 4))
            tk.Label(win, text="Red Sea Research Center | KAUST", bg=self.C['bg'],
                     fg='#00b8a0', font=('Segoe UI', 10)).pack(pady=(0, 10))
        tk.Label(win, text=f"{self.APP_NAME} v{self.APP_VERSION}",
                 bg=self.C['bg'], fg=self.C['blue'],
                 font=('Segoe UI', 16, 'bold')).pack()
        tk.Label(win,text=_L('about_desc',L),bg=self.C['bg'],fg=self.C['fg'],
                 font=('Segoe UI',10),justify='center').pack(pady=8)
        self._sep(win).pack(fill='x',padx=20,pady=4)
        tk.Label(win,text=_L('about_authors',L)+":",bg=self.C['bg'],fg=self.C['blue'],
                 font=('Segoe UI',10,'bold')).pack()
        tk.Label(win,text="Fabio Marchese\nHaBB Lab — Red Sea Research Center — KAUST",
                 bg=self.C['bg'],fg=self.C['fg'],font=('Segoe UI',10),justify='center').pack(pady=4)
        tk.Label(win,text="Claude Sonnet 4.6 — Anthropic",bg=self.C['bg'],fg=self.C['gray'],
                 font=('Segoe UI',9,'italic')).pack()
        self._sep(win).pack(fill='x',padx=20,pady=8)
        self._btn(win,'OK',win.destroy).pack(pady=4)

    def _build_profile_bar(self):
        for w in self._profile_bar.winfo_children(): w.destroy()
        f=self._profile_bar
        self._lbl(f,_L('profile_label',self.lang)).pack(side='left')
        self._entry(f,self.profile_path,26).pack(side='left',padx=4)
        self._btn(f,_L('save_profile',self.lang),self._save_profile,self.C['green']).pack(side='left',padx=2)
        self._btn(f,_L('load_profile',self.lang),self._load_profile,self.C['blue']).pack(side='left',padx=2)

    def _build_notebook(self):
        nb=ttk.Notebook(self); nb.pack(fill='both',expand=True,padx=10,pady=(0,6))
        self._rebuildable.append(nb)
        self.tab_files=tk.Frame(nb,bg=self.C['bg']); self.tab_usbl=tk.Frame(nb,bg=self.C['bg'])
        self.tab_ctd=tk.Frame(nb,bg=self.C['bg']); self.tab_custom=tk.Frame(nb,bg=self.C['bg'])
        self.tab_ext=tk.Frame(nb,bg=self.C['bg'])
        for tab,key,fallback in [(self.tab_files,'tab_files','Files'),
                                  (self.tab_usbl,'tab_usbl','USBL'),
                                  (self.tab_ctd,'tab_ctd','CTD'),
                                  (self.tab_custom,'tab_custom','Custom'),
                                  (self.tab_ext,'tab_extraction','Sync & Extract')]:
            try: txt=_L(key,self.lang)
            except Exception: txt=fallback
            # Se il key non esiste in lang.py, fallback hard-coded
            if txt==key: txt=fallback
            nb.add(tab,text=txt)
        self._build_tab_files(); self._build_tab_usbl(); self._build_tab_ctd()
        self._build_tab_custom(); self._build_tab_extraction()

    def _change_lang(self,*_):
        self.lang='it' if self._lang_var.get().startswith('IT') else 'en'
        for w in self._rebuildable: w.destroy()
        self._rebuildable=[]; self._usbl_combos=[]; self._ctd_combos=[]
        self._build_notebook(); self._build_profile_bar(); self._update_hw_label()

    # ── Tab 1 — FILE ─────────────────────────────────────────────────────────
    def _build_tab_files(self):
        p=self.tab_files; L=self.lang; inner=self._scrollable(p)

        def file_row(key, path_var, cmd, clear_cmd):
            lf = tk.LabelFrame(inner, text=_L(key, L), bg=self.C['bg'],
                               fg=self.C['blue'], font=('Segoe UI', 10, 'bold'))
            lf.pack(fill='x', padx=10, pady=6)
            r = tk.Frame(lf, bg=self.C['bg']); r.pack(fill='x', padx=8, pady=4)
            self._entry(r, path_var, 52).pack(side='left', fill='x', expand=True)
            self._btn(r, _L('browse', L), cmd, self.C['blue']).pack(side='left', padx=4)
            self._btn(r, _L('clear', L), clear_cmd, self.C['red']).pack(side='left', padx=2)
            return lf

        # Video
        vf = file_row('video_file', self.video_path,
                      self._browse_video,
                      lambda: (self.video_path.set(''),
                               self.video_info.config(text=''),
                               self.lbl_video_meta_ts.config(text='—'),
                               self.lbl_video_meta_src.config(text='')))
        self.video_info = self._lbl(vf, "", color=self.C['gray'], size=9)
        self.video_info.pack(anchor='w', padx=10, pady=(0,2))

        # Filename pattern
        rfp = tk.Frame(vf, bg=self.C['bg']); rfp.pack(fill='x', padx=8, pady=2)
        self._lbl(rfp, "Filename timestamp pattern:", size=9).pack(side='left')
        self._entry(rfp, self.fn_pattern, 22).pack(side='left', padx=4)
        self._lbl(rfp, "  YYYY MM DD HH MM SS = placeholders, * = wildcard",
                  color=self.C['gray'], size=9).pack(side='left', padx=4)

        rts = tk.Frame(vf, bg=self.C['bg']); rts.pack(fill='x', padx=8, pady=(0, 6))
        self._lbl(rts, "Video creation timestamp (auto-pick):", size=9).pack(side='left')
        self.lbl_video_meta_ts = self._lbl(rts, "—", color=self.C['yellow'])
        self.lbl_video_meta_ts.pack(side='left', padx=6)
        self.lbl_video_meta_src = self._lbl(rts, "", color=self.C['gray'], size=9)
        self.lbl_video_meta_src.pack(side='left', padx=4)
        self._btn(vf, "🔍 Detect timestamp", self._detect_video_ts,
                  self.C['blue']).pack(anchor='w', padx=10, pady=(0, 4))

        # 🕐 All available timestamps — picker
        ts_box = tk.LabelFrame(vf, text="🕐 All available timestamps — pick one to use",
                               bg=self.C['bg'], fg=self.C['blue'],
                               font=('Segoe UI', 10, 'bold'))
        ts_box.pack(fill='x', padx=10, pady=(0, 6))
        self._lbl(ts_box,
                  "Tutti i timestamp letti dal file (filesystem, container, sidecar, "
                  "timecode, pattern del nome). Seleziona quello da usare come "
                  "'video start timestamp' nella scheda Sync.",
                  color=self.C['gray'], size=9).pack(anchor='w', padx=8, pady=2)
        self.video_ts_choice = tk.StringVar(value='')   # chiave del timestamp scelto
        self.ts_picker_frame = tk.Frame(ts_box, bg=self.C['bg'])
        self.ts_picker_frame.pack(fill='x', padx=8, pady=(2, 4))
        self._lbl(self.ts_picker_frame,
                  "Carica un video e premi 'Detect timestamp'.",
                  color=self.C['gray'], size=9).pack(anchor='w')
        # Riga azione
        rta = tk.Frame(ts_box, bg=self.C['bg']); rta.pack(fill='x', padx=8, pady=(2, 6))
        self._btn(rta, "✅ Use selected as video start",
                  self._apply_selected_video_ts,
                  self.C['green']).pack(side='left', padx=2)
        self._btn(rta, "↻ Re-scan",
                  self._detect_video_ts,
                  self.C['blue']).pack(side='left', padx=2)

        # USBL
        uf = file_row('usbl_file', self.usbl_path,
                      self._browse_usbl,
                      lambda: (self.usbl_path.set(''),
                               self.usbl_info.config(text=''),
                               setattr(self, 'usbl_df', None),
                               setattr(self, 'usbl_cols', [])))
        ru2 = tk.Frame(uf, bg=self.C['bg']); ru2.pack(fill='x', padx=8, pady=2)
        self._lbl(ru2, _L('separator', L)).pack(side='left')
        self._combo(ru2, self.usbl_sep, [',', '\t', ' ', ';', 'Auto'], 7).pack(side='left', padx=4)
        tk.Checkbutton(ru2, text=_L('has_header', L), variable=self.usbl_header,
                       bg=self.C['bg'], fg=self.C['fg'],
                       selectcolor=self.C['entry']).pack(side='left', padx=10)
        self._btn(ru2, _L('load_usbl', L), self._load_usbl_preview,
                  self.C['blue']).pack(side='left', padx=8)
        self.usbl_info = self._lbl(uf, "", color=self.C['gray'], size=9)
        self.usbl_info.pack(anchor='w', padx=10, pady=(0, 4))

        # CTD
        cf = file_row('ctd_file', self.ctd_path,
                      self._browse_ctd,
                      lambda: (self.ctd_path.set(''),
                               self.ctd_info.config(text=''),
                               setattr(self, 'ctd_df', None),
                               setattr(self, 'ctd_df_validated', None),
                               setattr(self, 'ctd_cols', [])))
        rc2 = tk.Frame(cf, bg=self.C['bg']); rc2.pack(fill='x', padx=8, pady=2)
        self._lbl(rc2, _L('separator', L)).pack(side='left')
        self._combo(rc2, self.ctd_sep, [',', '\t', ' ', ';', 'Auto'], 7).pack(side='left', padx=4)
        tk.Checkbutton(rc2, text=_L('has_header', L), variable=self.ctd_header,
                       bg=self.C['bg'], fg=self.C['fg'],
                       selectcolor=self.C['entry']).pack(side='left', padx=10)
        self._btn(rc2, _L('load_ctd', L), self._load_ctd_preview,
                  self.C['blue']).pack(side='left', padx=8)
        self.ctd_info = self._lbl(cf, "", color=self.C['gray'], size=9)
        self.ctd_info.pack(anchor='w', padx=10, pady=(0, 4))

        # Dive name
        df=tk.LabelFrame(inner,text="Dive",bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        df.pack(fill='x',padx=10,pady=6)
        rd=tk.Frame(df,bg=self.C['bg']); rd.pack(fill='x',padx=8,pady=6)
        self._lbl(rd,_L('dive_name',L)).pack(side='left')
        self._entry(rd,self.dive_name,20).pack(side='left',padx=6)

        # Output
        of=tk.LabelFrame(inner,text=_L('output_folder',L),bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        of.pack(fill='x',padx=10,pady=6)
        ro=tk.Frame(of,bg=self.C['bg']); ro.pack(fill='x',padx=8,pady=4)
        self._entry(ro,self.output_dir,55).pack(side='left',fill='x',expand=True)
        self._btn(ro,_L('browse',L),self._browse_output,self.C['blue']).pack(side='left',padx=4)

        # Hardware
        hf=tk.LabelFrame(inner,text=_L('hardware',L),bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        hf.pack(fill='x',padx=10,pady=(10,4))
        cuda_txt=_L('cuda_available',L,n=CUDA_COUNT) if HAS_CUDA else _L('cuda_unavailable',L)
        tk.Checkbutton(hf,text=cuda_txt,variable=self.use_cuda,
                       state='normal' if HAS_CUDA else 'disabled',
                       bg=self.C['bg'],fg=self.C['green'] if HAS_CUDA else self.C['gray'],
                       selectcolor=self.C['entry'],font=('Segoe UI',10)).pack(anchor='w',padx=8,pady=4)
        geo='✓' if HAS_GEOPANDAS else '✗ pip install geopandas'
        mi='✓' if HAS_MEDIAINFO else '✗ pip install pymediainfo'
        self._lbl(hf,_L('hw_info',L,cores=os.cpu_count(),cv=cv2.__version__,geo=geo)+f" | mediainfo: {mi}",
                  color=self.C['gray'],size=9).pack(anchor='w',padx=8,pady=(0,6))

    # ── Tab 2 — USBL ─────────────────────────────────────────────────────────
    def _build_tab_usbl(self):
        p=self.tab_usbl; L=self.lang; inner=self._scrollable(p)
        lf=tk.LabelFrame(inner,text=_L('usbl_preview',L),bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        lf.pack(fill='x',padx=10,pady=6)
        # Treeview con scrollbar V+H (preview di 20 righe scrollabili)
        ptv=tk.Frame(lf,bg=self.C['bg']); ptv.pack(fill='both',expand=True,padx=4,pady=4)
        self.usbl_preview=ttk.Treeview(ptv,height=20)
        vsb=ttk.Scrollbar(ptv,orient='vertical',command=self.usbl_preview.yview)
        hsb=ttk.Scrollbar(ptv,orient='horizontal',command=self.usbl_preview.xview)
        self.usbl_preview.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        self.usbl_preview.grid(row=0,column=0,sticky='nsew')
        vsb.grid(row=0,column=1,sticky='ns')
        hsb.grid(row=1,column=0,sticky='ew')
        ptv.grid_rowconfigure(0,weight=1); ptv.grid_columnconfigure(0,weight=1)
        # Status: indici delle prime righe popolate
        self.usbl_populated_lbl=self._lbl(lf,"",color=self.C['gray'],size=9)
        self.usbl_populated_lbl.pack(anchor='w',padx=8,pady=(0,4))
        ts_lf=tk.LabelFrame(inner,text=_L('timestamp_section',L),bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        ts_lf.pack(fill='x',padx=10,pady=4)
        def ts_row(mode_val,mode_label,fields):
            r=tk.Frame(ts_lf,bg=self.C['bg']); r.pack(fill='x',padx=6,pady=3)
            tk.Radiobutton(r,text=mode_label,variable=self.ts_mode,value=mode_val,
                           width=22,anchor='w',bg=self.C['bg'],fg=self.C['fg'],
                           selectcolor=self.C['entry']).pack(side='left')
            for lbl,wfn in fields:
                self._lbl(r,lbl,size=9).pack(side='left',padx=(6,0))
                wfn(r).pack(side='left',padx=(2,0))
        ts_row('unified',_L('ts_unified',L),[
            (_L('col_label',L),lambda p:self._col_dd(p,self.ts_col_uni,28)),
            (_L('format_label',L),lambda p:self._entry(p,self.ts_fmt_uni,22)),])
        ts_row('split',_L('ts_split',L),[
            (_L('col_date',L),lambda p:self._col_dd(p,self.ts_col_date,24)),
            (_L('fmt_date',L),lambda p:self._combo(p,self.ts_fmt_date,['DD/MM/YYYY','YYYYMMDD','MM/DD/YYYY','%Y-%m-%d'],14)),
            (_L('col_time',L),lambda p:self._col_dd(p,self.ts_col_time,24)),
            (_L('fmt_time',L),lambda p:self._combo(p,self.ts_fmt_time,['HH:MM:SS','HHMMSS.ss','HH:MM:SS.sss'],14)),])
        ts_row('unix',_L('ts_unix',L),[
            (_L('col_label',L),lambda p:self._col_dd(p,self.ts_col_uni,28)),])
        co_lf=tk.LabelFrame(inner,text=_L('coordinates',L),bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        co_lf.pack(fill='x',padx=10,pady=4)
        r1=tk.Frame(co_lf,bg=self.C['bg']); r1.pack(fill='x',padx=6,pady=4)
        self._lbl(r1,_L('coord_format',L)).pack(side='left')
        for fmt in ['NMEA','DD','DM','DMS','UTM']:
            tk.Radiobutton(r1,text=fmt,variable=self.coord_fmt,value=fmt,
                           bg=self.C['bg'],fg=self.C['fg'],selectcolor=self.C['entry'],
                           command=self._coord_fmt_changed).pack(side='left',padx=5)
        r2=tk.Frame(co_lf,bg=self.C['bg']); r2.pack(fill='x',padx=6,pady=2)
        for lk,var in [('col_lat',self.lat_col),('col_lon',self.lon_col),('col_depth',self.depth_col)]:
            self._lbl(r2,_L(lk,L)).pack(side='left',padx=(8,0))
            self._col_dd(r2,var,28).pack(side='left',padx=(2,0))
        self.utm_row=tk.Frame(co_lf,bg=self.C['bg']); self.utm_row.pack(fill='x',padx=6,pady=2)
        self._lbl(self.utm_row,'Zona UTM:').pack(side='left')
        self._entry(self.utm_row,self.utm_zone,5).pack(side='left',padx=3)
        tk.Checkbutton(self.utm_row,text='Emisfero Nord (WGS84)',variable=self.utm_north,
                       bg=self.C['bg'],fg=self.C['fg'],selectcolor=self.C['entry']).pack(side='left',padx=8)
        self._lbl(self.utm_row,'⚠ Lat=Northing, Lon=Easting',color=self.C['yellow'],size=9).pack(side='left')
        self.utm_row.pack_forget()
        ex_lf=tk.LabelFrame(inner,text=_L('exclude_cols',L),bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        ex_lf.pack(fill='x',padx=10,pady=4)
        self.exclude_frame=tk.Frame(ex_lf,bg=self.C['bg']); self.exclude_frame.pack(fill='x',padx=6,pady=4)
        self._lbl(ex_lf,"Carica prima il file USBL.",color=self.C['gray'],size=9).pack(anchor='w',padx=6,pady=(0,4))
        self.coord_preview=self._lbl(inner,"",color=self.C['green'])
        self.coord_preview.pack(anchor='w',padx=14,pady=4)
        self._btn(inner,_L('validate_usbl',L),self._validate_usbl,self.C['blue']).pack(padx=10,pady=6,anchor='w')

    def _coord_fmt_changed(self):
        if self.coord_fmt.get()=='UTM': self.utm_row.pack(fill='x',padx=6,pady=2)
        else: self.utm_row.pack_forget()

    def _refresh_exclude_ui(self):
        for w in self.exclude_frame.winfo_children(): w.destroy()
        for col in self.usbl_cols:
            is_ex=col in self.excluded_usbl
            b=tk.Button(self.exclude_frame,text=col,
                        bg=self.C['red'] if is_ex else self.C['entry'],
                        fg=self.C['bg'] if is_ex else self.C['fg'],
                        relief='flat',bd=0,padx=6,pady=3,font=('Segoe UI',9),cursor='hand2')
            b.config(command=lambda c=col,btn=b:self._toggle_exclude(c,btn))
            b.pack(side='left',padx=2,pady=2)

    def _toggle_exclude(self,col,btn):
        if col in self.excluded_usbl:
            self.excluded_usbl.discard(col); btn.config(bg=self.C['entry'],fg=self.C['fg'])
        else:
            self.excluded_usbl.add(col); btn.config(bg=self.C['red'],fg=self.C['bg'])

    # ── Tab 3 — CTD ──────────────────────────────────────────────────────────
    def _build_tab_ctd(self):
        p=self.tab_ctd; L=self.lang; inner=self._scrollable(p)
        lf=tk.LabelFrame(inner,text=_L('ctd_preview',L),bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        lf.pack(fill='x',padx=10,pady=6)
        # Treeview con scrollbar V+H (preview di 20 righe scrollabili)
        ptv=tk.Frame(lf,bg=self.C['bg']); ptv.pack(fill='both',expand=True,padx=4,pady=4)
        self.ctd_preview=ttk.Treeview(ptv,height=20)
        vsb=ttk.Scrollbar(ptv,orient='vertical',command=self.ctd_preview.yview)
        hsb=ttk.Scrollbar(ptv,orient='horizontal',command=self.ctd_preview.xview)
        self.ctd_preview.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        self.ctd_preview.grid(row=0,column=0,sticky='nsew')
        vsb.grid(row=0,column=1,sticky='ns')
        hsb.grid(row=1,column=0,sticky='ew')
        ptv.grid_rowconfigure(0,weight=1); ptv.grid_columnconfigure(0,weight=1)
        self.ctd_populated_lbl=self._lbl(lf,"",color=self.C['gray'],size=9)
        self.ctd_populated_lbl.pack(anchor='w',padx=8,pady=(0,4))
        sf2=tk.LabelFrame(inner,text=_L('ctd_sync_mode',L),bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        sf2.pack(fill='x',padx=10,pady=4)
        for txt,val in [(_L('ctd_by_time',L),'time'),(_L('ctd_by_depth',L),'depth')]:
            tk.Radiobutton(sf2,text=txt,variable=self.ctd_sync_mode,value=val,
                           bg=self.C['bg'],fg=self.C['fg'],selectcolor=self.C['entry']).pack(anchor='w',padx=10,pady=2)
        ts_lf=tk.LabelFrame(inner,text=_L('timestamp_section',L),bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        ts_lf.pack(fill='x',padx=10,pady=4)
        def ctd_ts_row(mode_val,mode_label,fields):
            r=tk.Frame(ts_lf,bg=self.C['bg']); r.pack(fill='x',padx=6,pady=3)
            tk.Radiobutton(r,text=mode_label,variable=self.ctd_ts_mode,value=mode_val,
                           width=22,anchor='w',bg=self.C['bg'],fg=self.C['fg'],
                           selectcolor=self.C['entry']).pack(side='left')
            for lbl,wfn in fields:
                self._lbl(r,lbl,size=9).pack(side='left',padx=(6,0))
                wfn(r).pack(side='left',padx=(2,0))
        ctd_ts_row('unified',_L('ts_unified',L),[
            (_L('col_label',L),lambda p:self._ctd_dd(p,self.ctd_ts_col_uni,28)),
            (_L('format_label',L),lambda p:self._entry(p,self.ctd_ts_fmt_uni,22)),])
        ctd_ts_row('split',_L('ts_split',L),[
            (_L('col_date',L),lambda p:self._ctd_dd(p,self.ctd_ts_col_date,24)),
            (_L('fmt_date',L),lambda p:self._combo(p,self.ctd_ts_fmt_date,['DD/MM/YYYY','YYYYMMDD','MM/DD/YYYY','%Y-%m-%d'],14)),
            (_L('col_time',L),lambda p:self._ctd_dd(p,self.ctd_ts_col_time,24)),
            (_L('fmt_time',L),lambda p:self._combo(p,self.ctd_ts_fmt_time,['HH:MM:SS','HHMMSS.ss','HH:MM:SS.sss'],14)),])
        ctd_ts_row('unix',_L('ts_unix',L),[
            (_L('col_label',L),lambda p:self._ctd_dd(p,self.ctd_ts_col_uni,28)),])
        df_lf=tk.LabelFrame(inner,text="Depth",bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        df_lf.pack(fill='x',padx=10,pady=4)
        rd=tk.Frame(df_lf,bg=self.C['bg']); rd.pack(fill='x',padx=6,pady=4)
        self._lbl(rd,_L('ctd_depth_col',L)).pack(side='left')
        self.ctd_depth_combo=self._ctd_dd(rd,self.ctd_depth_col,28)
        self.ctd_depth_combo.pack(side='left',padx=4)
        cl=tk.LabelFrame(inner,text=_L('ctd_cols_label',L),bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        cl.pack(fill='x',padx=10,pady=4)
        self.ctd_col_frame=tk.Frame(cl,bg=self.C['bg']); self.ctd_col_frame.pack(fill='x',padx=6,pady=4)
        self._lbl(cl,"Carica prima il file CTD.",color=self.C['gray'],size=9).pack(anchor='w',padx=6,pady=(0,4))
        self.ctd_preview_result=self._lbl(inner,"",color=self.C['green'])
        self.ctd_preview_result.pack(anchor='w',padx=14,pady=4)
        self._btn(inner,"✅ Valida CTD",self._validate_ctd,self.C['blue']).pack(padx=10,pady=6,anchor='w')

        # Depth profile graph (per sync 'depth')
        self.ctd_depth_lf=tk.LabelFrame(inner,text="🌊 Profilo profondità CTD (sync per profondità)",
                                          bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        self.ctd_depth_lf.pack(fill='x',padx=10,pady=6)
        self._lbl(self.ctd_depth_lf,
                  "Trascina per selezionare la finestra (downcast / upcast / tutto):",
                  color=self.C['gray'],size=9).pack(anchor='w',padx=6,pady=2)
        self.ctd_canvas=tk.Canvas(self.ctd_depth_lf,bg=self.C['entry'],
                                   height=180,highlightthickness=0)
        self.ctd_canvas.pack(fill='x',padx=6,pady=4)
        self.ctd_canvas.bind('<Button-1>',self._ctd_canvas_click)
        self.ctd_canvas.bind('<B1-Motion>',self._ctd_canvas_drag)
        self.ctd_canvas.bind('<ButtonRelease-1>',self._ctd_canvas_release)
        self._ctd_drag_start=None
        bf=tk.Frame(self.ctd_depth_lf,bg=self.C['bg']); bf.pack(fill='x',padx=6,pady=4)
        self._btn(bf,"⬇ Auto-select downcast",self._select_downcast,self.C['blue']).pack(side='left',padx=2)
        self._btn(bf,"⬆ Auto-select upcast",self._select_upcast,self.C['blue']).pack(side='left',padx=2)
        self._btn(bf,"↺ Tutto",self._select_all_ctd,self.C['yellow']).pack(side='left',padx=2)
        self.ctd_window_lbl=self._lbl(bf,"Finestra: tutto",color=self.C['gray'],size=9)
        self.ctd_window_lbl.pack(side='left',padx=10)

    def _refresh_ctd_col_ui(self):
        for w in self.ctd_col_frame.winfo_children(): w.destroy()
        self.ctd_selected=[]
        for col in self.ctd_cols:
            var=tk.BooleanVar(value=False); self.ctd_selected.append((col,var))
            tk.Checkbutton(self.ctd_col_frame,text=col,variable=var,
                           bg=self.C['bg'],fg=self.C['fg'],selectcolor=self.C['entry'],
                           font=('Segoe UI',9)).pack(side='left',padx=4,pady=2)

    # ── Tab 4 — Custom ───────────────────────────────────────────────────────
    def _build_tab_custom(self):
        p=self.tab_custom; L=self.lang
        self._lbl(p,_L('custom_intro',L),color=self.C['gray']).pack(anchor='w',padx=10,pady=(8,2))
        self.custom_frame=tk.Frame(p,bg=self.C['bg']); self.custom_frame.pack(fill='x',padx=10)
        self._btn(p,_L('add_column',L),self._add_custom_col,self.C['blue']).pack(anchor='w',padx=10,pady=6)
        self._sep(p).pack(fill='x',padx=10,pady=6)
        self._lbl(p,_L('csv_preview_label',L),color=self.C['blue'],bold=True).pack(anchor='w',padx=10)
        self.csv_preview=tk.Text(p,height=4,bg=self.C['entry'],fg=self.C['green'],
                                  font=('Courier New',9),relief='flat',bd=4)
        self.csv_preview.pack(fill='x',padx=10,pady=4)
        self._btn(p,_L('update_preview',L),self._update_csv_preview).pack(anchor='w',padx=10)

    def _add_custom_col(self,name='',val=''):
        f=tk.Frame(self.custom_frame,bg=self.C['bg']); f.pack(fill='x',pady=2)
        nv=tk.StringVar(value=name); vv=tk.StringVar(value=val)
        self._lbl(f,_L('col_name',self.lang)).pack(side='left')
        self._entry(f,nv,14).pack(side='left',padx=3)
        self._lbl(f,_L('col_value',self.lang)).pack(side='left',padx=(8,0))
        self._entry(f,vv,22).pack(side='left',padx=3)
        row=(f,nv,vv); self.custom_col_rows.append(row)
        self._btn(f,"✕",lambda r=row:self._remove_custom_col(r),self.C['red']).pack(side='left',padx=4)

    def _remove_custom_col(self,row):
        row[0].destroy()
        if row in self.custom_col_rows: self.custom_col_rows.remove(row)

    def _update_csv_preview(self):
        cols=['image','dive','time_video','UNIXtime_video','depth_USBL','Lat_USBL','Long_USBL','time_USBL','dt_USBL_s']
        sample=['image0001.png',self.dive_name.get()]
        if self.usbl_df is not None and len(self.usbl_df):
            t0=self.usbl_df['unix_ts'].iloc[0]; dt=datetime.fromtimestamp(t0,tz=timezone.utc)
            d=self.usbl_df['depth'].iloc[0]
            sample+=[dt.strftime('%Y-%m-%dT%H:%M:%S'),str(int(t0)),
                     str(round(float(d),2)) if not np.isnan(d) else '—',
                     str(round(self.usbl_df['lat_dd'].iloc[0],6)),
                     str(round(self.usbl_df['lon_dd'].iloc[0],6)),
                     dt.strftime('%Y-%m-%dT%H:%M:%S'),'0.0']
        else:
            sample+=['—','—','—','—','—','—','—']
        for _,n,v in self.custom_col_rows:
            if n.get(): cols.append(n.get()); sample.append(v.get())
        self.csv_preview.delete('1.0','end')
        self.csv_preview.insert('end',','.join(cols)+'\n')
        self.csv_preview.insert('end',','.join(sample))

    # ── Tab 5 — Sync & Estrazione ────────────────────────────────────────────
    def _build_tab_extraction(self):
        p=self.tab_ext; L=self.lang; inner=self._scrollable(p)
        sync_lf=tk.LabelFrame(inner,text=_L('sync_panel',L),bg=self.C['bg'],
                              fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        sync_lf.pack(fill='x',padx=10,pady=6)

        # VIDEO
        vf=tk.LabelFrame(sync_lf,text="🎬 Video",bg=self.C['bg'],
                         fg=self.C['purple'],font=('Segoe UI',10,'bold'))
        vf.pack(fill='x',padx=8,pady=4)

        rm=tk.Frame(vf,bg=self.C['bg']); rm.pack(fill='x',padx=6,pady=(6,2))
        lbl_meta=self._lbl(rm,"Timestamp creazione video:",size=9,color=self.C['gray'])
        lbl_meta.pack(side='left')
        self._attach_tooltip(lbl_meta, _L('tip_video_meta_ts', L))
        self.lbl_video_ts_sync=self._lbl(rm,"—",color=self.C['yellow'])
        self.lbl_video_ts_sync.pack(side='left',padx=8)
        self._attach_tooltip(self.lbl_video_ts_sync, _L('tip_video_meta_ts', L))
        self.lbl_video_src_sync=self._lbl(rm,"",color=self.C['gray'],size=9)
        self.lbl_video_src_sync.pack(side='left')

        # Slider
        sp=tk.Frame(vf,bg=self.C['bg']); sp.pack(fill='x',padx=6,pady=2)
        lbl_pos=self._lbl(sp,"Posizione video (s):",size=9)
        lbl_pos.pack(side='left')
        self._attach_tooltip(lbl_pos, _L('tip_video_slider', L))
        # Entry editabile in secondi (più rapido del solo slider)
        self.video_pos_entry=self._entry(sp,self.video_pos_var,9)
        self.video_pos_entry.pack(side='left',padx=4)
        self._attach_tooltip(self.video_pos_entry,
            "Tempo (secondi dall'inizio del video). Modificalo e premi Invio\n"
            "per saltare a quel punto senza dover trascinare lo slider.")
        self.video_pos_entry.bind('<Return>',
            lambda e: self._goto_video_seconds(self.video_pos_var.get()))
        self.lbl_video_pos=self._lbl(sp,"0.0 s",color=self.C['purple'])
        self.lbl_video_pos.pack(side='left',padx=6)
        # Tempo assoluto UTC (HH:MM:SS) — calcolato da video_ts_offset + slider
        lbl_t_abs=self._lbl(sp,"  Time UTC:",size=9,color=self.C['gray'])
        lbl_t_abs.pack(side='left',padx=(10,0))
        self.video_pos_time=tk.StringVar(value='—')
        self.video_pos_time_entry=self._entry(sp,self.video_pos_time,21)
        self.video_pos_time_entry.pack(side='left',padx=4)
        self._attach_tooltip(self.video_pos_time_entry,
            "Tempo UTC corrispondente alla posizione attuale del video,\n"
            "calcolato come 'video start timestamp' + 'Posizione video'.\n\n"
            "Modifica e premi Invio per saltare a quel timestamp:\n"
            "es. 2020-10-25T11:55:00 → l'app calcola i secondi e si\n"
            "posiziona direttamente, senza scorrere tutto il video.")
        self.video_pos_time_entry.bind('<Return>',
            lambda e: self._goto_video_time(self.video_pos_time.get()))
        btn_go=self._btn(sp,"⏎ Go",
            lambda: self._goto_video_time(self.video_pos_time.get()),
            self.C['blue'])
        btn_go.pack(side='left',padx=2)

        self.video_slider=tk.Scale(vf,from_=0,to=100,resolution=0.1,
                                   orient='horizontal',variable=self.video_pos_var,
                                   bg=self.C['bg'],fg=self.C['fg'],
                                   troughcolor=self.C['entry'],highlightthickness=0,
                                   length=500,showvalue=False,
                                   command=self._on_video_slider)
        self.video_slider.pack(fill='x',padx=6,pady=2)
        self._attach_tooltip(self.video_slider, _L('tip_video_slider', L))
        nf=tk.Frame(vf,bg=self.C['bg']); nf.pack(padx=6,pady=2,anchor='w')
        for label,delta in [('◀◀ -10s',-10),('◀ -1s',-1),('◀ -1f',-1/25),
                             ('▶ +1f',1/25),('▶ +1s',1),('▶▶ +10s',10)]:
            btn=self._btn(nf,label,lambda d=delta:self._step_video(d))
            btn.pack(side='left',padx=2)
            self._attach_tooltip(btn, _L('tip_video_slider', L))

        # Frame preview
        self.frame_preview_lbl=tk.Label(vf,bg='#0a0a0a',
                                        text="[ load video → use slider ]",
                                        fg=self.C['gray'],font=('Segoe UI',9,'italic'),
                                        width=64,height=12)
        self.frame_preview_lbl.pack(padx=6,pady=4)

        # Touchdown sync
        sw=tk.LabelFrame(vf,text="🎯 Touchdown synchronisation",bg=self.C['bg'],
                         fg=self.C['green'],font=('Segoe UI',10,'bold'))
        sw.pack(fill='x',padx=6,pady=4)
        lbl_step1=self._lbl(sw,"1️⃣ Position slider at touchdown (frame when ROV touches the seafloor)",
                  size=9,color=self.C['gray'])
        lbl_step1.pack(anchor='w',padx=6,pady=2)
        self._attach_tooltip(lbl_step1, _L('tip_video_slider', L))
        rd=tk.Frame(sw,bg=self.C['bg']); rd.pack(fill='x',padx=6,pady=2)
        lbl_td_depth=self._lbl(rd,"Touchdown depth (read from video):",size=9)
        lbl_td_depth.pack(side='left')
        self._attach_tooltip(lbl_td_depth, _L('tip_touchdown_depth', L))
        ent_td=self._entry(rd,self.video_depth_manual,8)
        ent_td.pack(side='left',padx=4)
        self._attach_tooltip(ent_td, _L('tip_touchdown_depth', L))
        self._lbl(rd,"m",color=self.C['gray'],size=9).pack(side='left')

        # 🎯 Sync action buttons (Video↔USBL): spostati qui in alto, tra Video e USBL
        sa=tk.Frame(sync_lf,bg=self.C['bg']); sa.pack(fill='x',padx=8,pady=(6,2))
        btn_sync=self._btn(sa,"🎯 Synchronise with these two points",
                  self._sync_with_touchdown,self.C['green'])
        btn_sync.pack(side='left',padx=2)
        self._attach_tooltip(btn_sync, _L('tip_sync_btn', L))
        btn_reset=self._btn(sa,"↺ Reset",self._reset_sync,self.C['yellow'])
        btn_reset.pack(side='left',padx=2)
        self._attach_tooltip(btn_reset, _L('tip_reset_btn', L))
        btn_upd=self._btn(sa,"▶ Update preview",self._apply_sync,self.C['blue'])
        btn_upd.pack(side='left',padx=2)
        self._attach_tooltip(btn_upd, _L('tip_update_preview', L))

        # USBL depth plot
        up=tk.LabelFrame(sync_lf,text="📡 USBL — depth profile",bg=self.C['bg'],
                         fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        up.pack(fill='x',padx=8,pady=4)
        lbl_step2=self._lbl(up,"2️⃣ Click on the plot at the USBL touchdown point (maximum stable depth)",
                  color=self.C['gray'],size=9)
        lbl_step2.pack(anchor='w',padx=6,pady=2)
        self._attach_tooltip(lbl_step2, _L('tip_usbl_plot', L))
        self.usbl_canvas=tk.Canvas(up,bg=self.C['entry'],height=180,highlightthickness=0)
        self.usbl_canvas.pack(fill='x',padx=6,pady=4)
        self.usbl_canvas.bind('<Button-1>',self._usbl_canvas_click)
        self._attach_tooltip(self.usbl_canvas, _L('tip_usbl_plot', L))
        self._usbl_touchdown_unix=None
        self.lbl_usbl_touchdown=self._lbl(up,"USBL touchdown: not yet selected",
                                          color=self.C['gray'],size=9)
        self.lbl_usbl_touchdown.pack(anchor='w',padx=6,pady=2)

        # 🌊 CTD ↔ USBL depth overlay (drag interattivo)
        ov=tk.LabelFrame(sync_lf,
                         text="🌊 CTD ↔ USBL depth overlay — drag the red curve to align",
                         bg=self.C['bg'],fg=self.C['blue'],
                         font=('Segoe UI',10,'bold'))
        ov.pack(fill='x',padx=8,pady=4)
        self._lbl(ov,
                  "Trascina la curva rossa (CTD) lungo l'asse X (tempo) per "
                  "sovrapporla a quella blu (USBL). L'asse Y (profondità) resta fissa.",
                  color=self.C['gray'],size=9).pack(anchor='w',padx=6,pady=2)
        self.depth_overlay_canvas=tk.Canvas(ov,bg=self.C['entry'],height=260,
                                            highlightthickness=0)
        self.depth_overlay_canvas.pack(fill='x',padx=6,pady=4)
        self.depth_overlay_canvas.bind('<Button-1>',  self._overlay_press)
        self.depth_overlay_canvas.bind('<B1-Motion>', self._overlay_drag)
        self.depth_overlay_canvas.bind('<ButtonRelease-1>', self._overlay_release)
        # Configurabile: ridisegna se la finestra cambia dimensione
        self.depth_overlay_canvas.bind('<Configure>',
            lambda e: self._draw_depth_overlay())
        rsv=tk.Frame(ov,bg=self.C['bg']); rsv.pack(fill='x',padx=6,pady=2)
        self.lbl_overlay_status=self._lbl(rsv,
            "shift: 0.0 s   |ΔD| median: —   (drag the red CTD curve)",
            color=self.C['fg'],size=9)
        self.lbl_overlay_status.pack(side='left',padx=4)
        rbtn=tk.Frame(ov,bg=self.C['bg']); rbtn.pack(fill='x',padx=6,pady=4)
        btn_ov_apply=self._btn(rbtn,"✅ Apply drag shift",
                               self._apply_overlay_shift, self.C['green'])
        btn_ov_apply.pack(side='left',padx=2)
        self._attach_tooltip(btn_ov_apply,
            "Conferma lo shift trascinato e lo applica permanentemente alla\n"
            "serie CTD (modifica unix_ts del df validato).")
        btn_ov_reset=self._btn(rbtn,"↺ Reset drag",
                               self._reset_overlay_shift, self.C['yellow'])
        btn_ov_reset.pack(side='left',padx=2)
        self._attach_tooltip(btn_ov_reset,
            "Annulla lo shift trascinato (non ancora applicato) e ridisegna\n"
            "la curva CTD nella sua posizione attuale.")
        btn_ov_auto=self._btn(rbtn,"🤖 Auto-align (depth match)",
                              self._auto_fix_ctd_time_from_depth, self.C['blue'])
        btn_ov_auto.pack(side='left',padx=2)
        self._attach_tooltip(btn_ov_auto,
            "Calcola automaticamente lo shift CTD→USBL allineando la profondità\n"
            "del primo frame (utile come punto di partenza, poi puoi raffinare\n"
            "trascinando manualmente).")

        # Manual override
        mo=tk.LabelFrame(sync_lf,text="✏ Manual correction (optional)",bg=self.C['bg'],
                         fg=self.C['gray'],font=('Segoe UI',10,'bold'))
        mo.pack(fill='x',padx=8,pady=4)
        rm2=tk.Frame(mo,bg=self.C['bg']); rm2.pack(fill='x',padx=6,pady=4)
        lbl_vts=self._lbl(rm2,"Corrected video start timestamp:",size=9)
        lbl_vts.pack(side='left')
        self._attach_tooltip(lbl_vts, _L('tip_video_ts_corrected', L))
        ent_vts=self._entry(rm2,self.video_ts_corrected,22)
        ent_vts.pack(side='left',padx=4)
        self._attach_tooltip(ent_vts, _L('tip_video_ts_corrected', L))
        rm3=tk.Frame(mo,bg=self.C['bg']); rm3.pack(fill='x',padx=6,pady=4)
        lbl_cts=self._lbl(rm3,"Corrected CTD start timestamp:",size=9)
        lbl_cts.pack(side='left')
        self._attach_tooltip(lbl_cts, _L('tip_ctd_ts_corrected', L))
        ent_cts=self._entry(rm3,self.ctd_ts_corrected,22)
        ent_cts.pack(side='left',padx=4)
        self._attach_tooltip(ent_cts, _L('tip_ctd_ts_corrected', L))
        # ✨ Apply CTD time only (non tocca video sync)
        btn_cts_apply=self._btn(rm3,"⏱ Apply CTD time only",
                                self._apply_ctd_time_only, self.C['blue'])
        btn_cts_apply.pack(side='left',padx=6)
        self._attach_tooltip(btn_cts_apply,
            "Aggiorna SOLO il time della CTD nella tabella di anteprima.\n"
            "Usa il valore del campo 'Corrected CTD start timestamp' come nuovo t0\n"
            "della serie CTD (lo shift è la differenza con il primo timestamp letto).\n"
            "Non modifica la sincronizzazione video↔USBL.")
        # 🌊 Auto-fix CTD time da depth USBL (per CTD by_time)
        btn_cts_auto=self._btn(rm3,"🌊 Auto-fix from USBL depth",
                               self._auto_fix_ctd_time_from_depth, self.C['green'])
        btn_cts_auto.pack(side='left',padx=2)
        self._attach_tooltip(btn_cts_auto,
            "Calcola automaticamente lo shift temporale CTD→USBL allineando\n"
            "le profondità: per il primo frame trova nella CTD il punto in cui\n"
            "depth_CTD ≈ depth_USBL e shifta tutta la serie CTD di conseguenza.\n"
            "Utile quando la CTD ha l'orologio sballato di ore.")

        rm4=tk.Frame(mo,bg=self.C['bg']); rm4.pack(fill='x',padx=6,pady=4)
        lbl_cdl=self._lbl(rm4,"CTD shift (s):",size=9)
        lbl_cdl.pack(side='left')
        self._attach_tooltip(lbl_cdl,
            "Shift live in secondi applicato alla serie CTD validata, in tempo reale.\n"
            "• Trascinando la curva rossa nel grafico CTD↔USBL questo numero si aggiorna.\n"
            "• Scrivilo a mano e premi Invio per spostare la curva CTD di quella quantità.\n"
            "• 🤖 Auto-fix from USBL depth lo riempie automaticamente.\n"
            "• ✅ Apply consolida lo shift nel df validato e azzera il campo.\n"
            "• In estrazione il valore corrente viene applicato anche se non hai premuto Apply.")
        ent_cdl=self._entry(rm4,self.ctd_ts_offset,8)
        ent_cdl.pack(side='left',padx=4)
        self._attach_tooltip(ent_cdl,
            "Shift CTD in secondi (positivo = sposta CTD in avanti nel tempo).")
        # Live redraw quando l'utente scrive il numero
        ent_cdl.bind('<Return>', lambda e: self._on_ctd_shift_changed())
        ent_cdl.bind('<FocusOut>', lambda e: self._on_ctd_shift_changed())
        # Tasto Apply / Reset accanto al campo
        self._btn(rm4,"✅ Apply", self._apply_overlay_shift,
                  self.C['green']).pack(side='left',padx=2)
        self._btn(rm4,"↺ Reset", self._reset_overlay_shift,
                  self.C['yellow']).pack(side='left',padx=2)
        # Tolleranza profondità CTD vs USBL
        lbl_dtol=self._lbl(rm4,"Max |Δdepth CTD−USBL| (m):",size=9)
        lbl_dtol.pack(side='left',padx=(12,0))
        ent_dtol=self._entry(rm4,self.ctd_depth_tol,6)
        ent_dtol.pack(side='left',padx=4)
        self._attach_tooltip(lbl_dtol,
            "Soglia massima per |depth_CTD − depth_USBL| nei frame campione.\n"
            "Se la mediana supera questo valore l'estrazione viene bloccata\n"
            "(per CTD by_time → la sincronizzazione tempo è errata;\n"
            "per CTD by_depth → la finestra CTD è sbagliata o un'altra dive).")
        # Etichetta status validazione depth
        rm5=tk.Frame(mo,bg=self.C['bg']); rm5.pack(fill='x',padx=6,pady=2)
        self.lbl_ctd_depth_status=self._lbl(rm5,"",color=self.C['gray'],size=9)
        self.lbl_ctd_depth_status.pack(side='left',padx=4)

        # Allineamento preview
        al_lf=tk.LabelFrame(sync_lf,text="📊 Anteprima allineamento (10 frame campione)",
                            bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        al_lf.pack(fill='x',padx=8,pady=4)
        cols=('frame','time_video','time_usbl','dt_usbl','depth_usbl',
              'time_ctd','dt_ctd','depth_ctd','dd_ctd')
        self.align_tree=ttk.Treeview(al_lf,columns=cols,show='headings',height=10)
        for col,lbl,w in [('frame','#',40),('time_video','Time Video',155),
                           ('time_usbl','Time USBL',155),('dt_usbl','ΔT USBL',65),
                           ('depth_usbl','Depth USBL',80),('time_ctd','Time CTD',155),
                           ('dt_ctd','ΔT CTD',65),('depth_ctd','Depth CTD',80),
                           ('dd_ctd','Δdepth (m)',85)]:
            self.align_tree.heading(col,text=lbl)
            self.align_tree.column(col,width=w,anchor='center')
        self.align_tree.tag_configure('warn',foreground=self.C['yellow'])
        self.align_tree.tag_configure('bad', foreground=self.C['red'])
        self.align_tree.tag_configure('ok',  foreground=self.C['green'])
        sb_al=ttk.Scrollbar(al_lf,orient='horizontal',command=self.align_tree.xview)
        self.align_tree.configure(xscrollcommand=sb_al.set)
        self.align_tree.pack(fill='x',padx=4,pady=4); sb_al.pack(fill='x',padx=4)

        # Porzione video
        pv=tk.LabelFrame(inner,text="✂ Video portion to extract",
                         bg=self.C['bg'],fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        pv.pack(fill='x',padx=10,pady=4)
        # Riga 1: secondi
        rp=tk.Frame(pv,bg=self.C['bg']); rp.pack(fill='x',padx=8,pady=6)
        lbl_from=self._lbl(rp,"From (s):")
        lbl_from.pack(side='left')
        self._attach_tooltip(lbl_from, _L('tip_extract_from', L))
        ent_from=self._entry(rp,self.extract_from,8)
        ent_from.pack(side='left',padx=4)
        self._attach_tooltip(ent_from, _L('tip_extract_from', L))
        ent_from.bind('<Return>', lambda e: self._sync_extract_time_from_secs('from'))
        lbl_to=self._lbl(rp,"To (s):")
        lbl_to.pack(side='left',padx=(12,0))
        self._attach_tooltip(lbl_to, _L('tip_extract_to', L))
        ent_to=self._entry(rp,self.extract_to,8)
        ent_to.pack(side='left',padx=4)
        self._attach_tooltip(ent_to, _L('tip_extract_to', L))
        ent_to.bind('<Return>', lambda e: self._sync_extract_time_from_secs('to'))
        self._lbl(rp,"(0 = end of video)",color=self.C['gray'],size=9).pack(side='left',padx=4)
        btn_from=self._btn(rp,"📍 From current pos.",
                  lambda:[self.extract_from.set(round(self.video_pos_var.get(),1)),
                          self._sync_extract_time_from_secs('from')],
                  self.C['blue'])
        btn_from.pack(side='left',padx=8)
        self._attach_tooltip(btn_from, _L('tip_extract_from', L))
        btn_to=self._btn(rp,"📍 To current pos.",
                  lambda:[self.extract_to.set(round(self.video_pos_var.get(),1)),
                          self._sync_extract_time_from_secs('to')],
                  self.C['blue'])
        btn_to.pack(side='left',padx=4)
        self._attach_tooltip(btn_to, _L('tip_extract_to', L))

        # Riga 2: tempi UTC (HH:MM:SS) — interscambiabili con i secondi
        rpt=tk.Frame(pv,bg=self.C['bg']); rpt.pack(fill='x',padx=8,pady=(0,6))
        self._lbl(rpt,"From (UTC):",size=9,color=self.C['gray']).pack(side='left')
        self.extract_from_time=tk.StringVar(value='—')
        ent_from_t=self._entry(rpt,self.extract_from_time,21)
        ent_from_t.pack(side='left',padx=4)
        self._attach_tooltip(ent_from_t,
            "Tempo UTC di inizio estrazione. Modificalo e premi Invio:\n"
            "verrà calcolato il corrispondente 'From (s)'.")
        ent_from_t.bind('<Return>', lambda e: self._sync_extract_secs_from_time('from'))
        self._lbl(rpt,"To (UTC):",size=9,color=self.C['gray']).pack(side='left',padx=(12,0))
        self.extract_to_time=tk.StringVar(value='—')
        ent_to_t=self._entry(rpt,self.extract_to_time,21)
        ent_to_t.pack(side='left',padx=4)
        self._attach_tooltip(ent_to_t,
            "Tempo UTC di fine estrazione. Modificalo e premi Invio:\n"
            "verrà calcolato il corrispondente 'To (s)'.\n"
            "Lascia '—' o vuoto per usare la fine del video.")
        ent_to_t.bind('<Return>', lambda e: self._sync_extract_secs_from_time('to'))

        # Estrazione
        ef=tk.LabelFrame(inner,text=_L('extraction_section',L),bg=self.C['bg'],
                         fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        ef.pack(fill='x',padx=10,pady=4)
        re=tk.Frame(ef,bg=self.C['bg']); re.pack(fill='x',padx=8,pady=4)
        lbl_ivl=self._lbl(re,_L('every_n_sec',L))
        lbl_ivl.pack(side='left')
        self._attach_tooltip(lbl_ivl, _L('tip_interval', L))
        ent_ivl=self._entry(re,self.interval_sec,6)
        ent_ivl.pack(side='left',padx=4)
        self._attach_tooltip(ent_ivl, _L('tip_interval', L))
        lbl_tol=self._lbl(re,_L('assoc_window',L))
        lbl_tol.pack(side='left',padx=(12,0))
        self._attach_tooltip(lbl_tol, _L('assoc_window_tip', L))
        ent_tol=self._entry(re,self.assoc_window,5)
        ent_tol.pack(side='left',padx=4)
        self._attach_tooltip(ent_tol, _L('assoc_window_tip', L))
        info_btn=self._lbl(re,"ⓘ",color=self.C['blue'],bold=True)
        info_btn.pack(side='left',padx=(2,8))
        self._attach_tooltip(info_btn, _L('assoc_window_tip', L))
        lbl_fmt=self._lbl(re,_L('format_label2',L))
        lbl_fmt.pack(side='left')
        self._attach_tooltip(lbl_fmt, _L('tip_img_format', L))
        cmb_fmt=self._combo(re,self.img_fmt,['PNG','JPEG','TIFF'],7)
        cmb_fmt.pack(side='left',padx=4)
        self._attach_tooltip(cmb_fmt, _L('tip_img_format', L))
        lbl_jq=self._lbl(re,_L('jpeg_quality',L))
        lbl_jq.pack(side='left',padx=(8,0))
        self._attach_tooltip(lbl_jq, _L('tip_jpeg_quality', L))
        ent_jq=self._entry(re,self.img_quality,4)
        ent_jq.pack(side='left',padx=4)
        self._attach_tooltip(ent_jq, _L('tip_jpeg_quality', L))

        # Qualità
        qf=tk.LabelFrame(inner,text=_L('quality_section',L),bg=self.C['bg'],
                         fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        qf.pack(fill='x',padx=10,pady=4)
        rq=tk.Frame(qf,bg=self.C['bg']); rq.pack(fill='x',padx=8,pady=4)
        for lk,var,tip_key in [('blur_thresh',self.blur_thresh,'tip_blur_thresh'),
                                ('dark_thresh',self.dark_thresh,'tip_dark_thresh'),
                                ('bright_thresh',self.bright_thresh,'tip_bright_thresh')]:
            lbl=self._lbl(rq,_L(lk,L)); lbl.pack(side='left')
            self._attach_tooltip(lbl, _L(tip_key, L))
            ent=self._entry(rq,var,6); ent.pack(side='left',padx=(2,8))
            self._attach_tooltip(ent, _L(tip_key, L))
        self._lbl(qf,_L('quality_hint',L),color=self.C['yellow'],size=9).pack(anchor='w',padx=8,pady=(0,4))

        # Overlay
        of=tk.LabelFrame(inner,text=_L('overlay_section',L),bg=self.C['bg'],
                         fg=self.C['blue'],font=('Segoe UI',10,'bold'))
        of.pack(fill='x',padx=10,pady=4)
        cb_ovl=tk.Checkbutton(of,text=_L('overlay_enable',L),variable=self.ovl_enabled,
                       bg=self.C['bg'],fg=self.C['fg'],selectcolor=self.C['entry'])
        cb_ovl.pack(anchor='w',padx=8,pady=2)
        self._attach_tooltip(cb_ovl, _L('tip_ovl_enable', L))
        og=tk.Frame(of,bg=self.C['bg']); og.pack(fill='x',padx=8,pady=2)
        for tk_,var in [('ovl_time',self.ovl_time),('ovl_depth',self.ovl_depth),
                        ('ovl_latlon',self.ovl_latlon),('ovl_dive',self.ovl_dive)]:
            cb=tk.Checkbutton(og,text=_L(tk_,L),variable=var,
                           bg=self.C['bg'],fg=self.C['fg'],selectcolor=self.C['entry'])
            cb.pack(side='left',padx=5)
            self._attach_tooltip(cb, _L('tip_ovl_fields', L))
        oo=tk.Frame(of,bg=self.C['bg']); oo.pack(fill='x',padx=8,pady=2)
        lbl_op=self._lbl(oo,_L('ovl_position',L)); lbl_op.pack(side='left')
        self._attach_tooltip(lbl_op, _L('tip_ovl_pos', L))
        cmb_op=self._combo(oo,self.ovl_pos,['bottom_left','bottom_right','top_left','top_right'],13)
        cmb_op.pack(side='left',padx=4)
        self._attach_tooltip(cmb_op, _L('tip_ovl_pos', L))
        lbl_fs=self._lbl(oo,_L('ovl_fontsize',L)); lbl_fs.pack(side='left',padx=(8,0))
        self._attach_tooltip(lbl_fs, _L('tip_ovl_fontsize', L))
        ent_fs=self._entry(oo,self.ovl_fontsize,4); ent_fs.pack(side='left',padx=4)
        self._attach_tooltip(ent_fs, _L('tip_ovl_fontsize', L))
        lbl_oc=self._lbl(oo,_L('ovl_color',L)); lbl_oc.pack(side='left',padx=(8,0))
        self._attach_tooltip(lbl_oc, _L('tip_ovl_color', L))
        cmb_oc=self._combo(oo,self.ovl_color,['white','yellow','cyan','black'],7)
        cmb_oc.pack(side='left',padx=4)
        self._attach_tooltip(cmb_oc, _L('tip_ovl_color', L))
        lbl_bg=self._lbl(oo,_L('ovl_bg',L)); lbl_bg.pack(side='left',padx=(8,0))
        self._attach_tooltip(lbl_bg, _L('tip_ovl_bg', L))
        cmb_bg=self._combo(oo,self.ovl_bg,['rect','shadow','none'],7)
        cmb_bg.pack(side='left',padx=4)
        self._attach_tooltip(cmb_bg, _L('tip_ovl_bg', L))

        # Progress & log
        self.progress=ttk.Progressbar(inner,orient='horizontal',mode='determinate')
        self.progress.pack(fill='x',padx=10,pady=(8,2))
        self.status_lbl=self._lbl(inner,_L('ready',self.lang),color=self.C['gray'])
        self.status_lbl.pack(anchor='w',padx=10)
        self.log_box=tk.Text(inner,height=7,bg=self.C['entry'],fg=self.C['fg'],
                              font=('Courier New',9),relief='flat',bd=4,state='disabled')
        self.log_box.pack(fill='x',padx=10,pady=4)
        for tag,col in [('ok',self.C['green']),('warn',self.C['yellow']),
                        ('err',self.C['red']),('info',self.C['blue'])]:
            self.log_box.tag_config(tag,foreground=col)
        bf2=tk.Frame(inner,bg=self.C['bg']); bf2.pack(fill='x',padx=10,pady=4)
        self._btn(bf2,_L('btn_start',L),self._start_extraction,self.C['green']).pack(side='left',padx=4)
        self._btn(bf2,_L('btn_pause',L),self._toggle_pause).pack(side='left',padx=4)
        self._btn(bf2,_L('btn_stop',L),self._stop_extraction,self.C['red']).pack(side='left',padx=4)

    # ── Tab 6 — Samples / Sample frame extraction ────────────────────────────
    # ── Sync logic ────────────────────────────────────────────────────────────
    def _sync_with_touchdown(self):
        """Calcola video_ts_corrected da: pos. video + touchdown USBL selezionato."""
        if self._usbl_touchdown_unix is None:
            messagebox.showwarning("Sync","Seleziona prima il punto touchdown nel grafico USBL.")
            return
        # Touchdown USBL = momento in cui il video corrente corrisponde al touchdown reale
        # quindi video_ts_offset = ts_USBL_touchdown - posizione_slider_attuale
        video_ts_offset = self._usbl_touchdown_unix - self.video_pos_var.get()
        dt = datetime.fromtimestamp(video_ts_offset, tz=timezone.utc)
        self.video_ts_corrected.set(dt.strftime('%Y-%m-%dT%H:%M:%S'))
        self._log('ok',f'✅ Sincronizzazione applicata: video inizia a {dt.strftime("%Y-%m-%dT%H:%M:%S")}')
        self._apply_sync()

    def _apply_sync(self):
        self._show_frame_at(self.video_pos_var.get())
        self._build_alignment_table()
        self._draw_usbl_depth_plot()
        self._draw_depth_overlay()
        # Aggiorna le entry tempo UTC (slider video + estrazione)
        self._refresh_video_pos_time(self.video_pos_var.get())
        if hasattr(self,'extract_from_time'):
            self._sync_extract_time_from_secs('from')
            self._sync_extract_time_from_secs('to')

    # ── 🌊 Depth overlay (USBL vs CTD, drag interattivo) ─────────────────────
    def _on_ctd_shift_changed(self):
        """Callback: l'utente ha modificato manualmente CTD shift (s)."""
        try: self._draw_depth_overlay()
        except Exception: pass
        try: self._build_alignment_table()
        except Exception: pass

    def _draw_depth_overlay(self):
        """Disegna le due curve depth(time): USBL blu fissa + CTD rossa
        spostata di self.ctd_ts_offset secondi (solo asse X)."""
        if not hasattr(self,'depth_overlay_canvas'): return
        c=self.depth_overlay_canvas
        c.delete('all')
        W=c.winfo_width() or 700; H=c.winfo_height() or 260
        mg_l=55; mg_r=14; mg_t=22; mg_b=32
        plot_w=max(50, W-mg_l-mg_r); plot_h=max(50, H-mg_t-mg_b)

        if self.usbl_df is None or len(self.usbl_df)==0:
            c.create_text(W//2,H//2,text="Carica e valida USBL per vedere l'overlay",
                          fill=self.C['gray'],font=('Segoe UI',9))
            return

        usbl_t=self.usbl_df['unix_ts'].values
        usbl_d_raw=self.usbl_df['depth'].values
        # Usa abs(depth) per il plot e il confronto: gestisce automaticamente
        # i casi in cui USBL e CTD adottano segno opposto (altitudine negativa
        # vs profondità positiva).
        usbl_d=np.abs(usbl_d_raw)
        valid_u=~(np.isnan(usbl_t)|np.isnan(usbl_d))
        if not np.any(valid_u):
            c.create_text(W//2,H//2,text="USBL: nessun depth valido",
                          fill=self.C['yellow'],font=('Segoe UI',9))
            return

        # CTD shifted (preview during drag) — shift_now SEMPRE definito
        have_ctd=False; ctd_t_sh=None; ctd_d=None; valid_c=None
        try: shift_now = float(self.ctd_ts_offset.get())
        except Exception: shift_now = 0.0
        # Diagnostica segno: se USBL median < 0 e CTD median > 0 (o viceversa),
        # avvisiamo nella legenda che stiamo confrontando |depth|
        sign_mismatch=False
        if (self.ctd_df_validated is not None
                and 'unix_ts' in self.ctd_df_validated.columns
                and '_depth_key' in self.ctd_df_validated.columns):
            ctd_t=self.ctd_df_validated['unix_ts'].values
            ctd_d_raw=self.ctd_df_validated['_depth_key'].values
            ctd_d=np.abs(ctd_d_raw)
            try:
                u_med=np.nanmedian(usbl_d_raw); c_med=np.nanmedian(ctd_d_raw)
                if not np.isnan(u_med) and not np.isnan(c_med):
                    if (u_med<0 and c_med>0) or (u_med>0 and c_med<0):
                        sign_mismatch=True
            except Exception: pass
            ctd_t_sh=ctd_t+shift_now
            valid_c=~(np.isnan(ctd_t_sh)|np.isnan(ctd_d))
            if np.any(valid_c):
                have_ctd=True

        # Range tempo: include sia USBL che CTD shiftata, con piccolo padding
        t_min=float(np.nanmin(usbl_t[valid_u]))
        t_max=float(np.nanmax(usbl_t[valid_u]))
        if have_ctd:
            t_min=min(t_min,float(np.nanmin(ctd_t_sh[valid_c])))
            t_max=max(t_max,float(np.nanmax(ctd_t_sh[valid_c])))
        if t_max-t_min<1: t_max=t_min+1.0
        pad=(t_max-t_min)*0.02
        t_min-=pad; t_max+=pad

        # Range profondità (sempre positivo perché abbiamo applicato abs())
        all_d=list(usbl_d[valid_u])
        if have_ctd: all_d+=list(ctd_d[valid_c])
        d_max=max(all_d)*1.05 if all_d else 100.0
        d_min=0.0

        def t2x(t): return mg_l+(t-t_min)/(t_max-t_min)*plot_w
        def d2y(d): return mg_t+(d-d_min)/(d_max-d_min)*plot_h

        # Cornice
        c.create_rectangle(mg_l,mg_t,mg_l+plot_w,mg_t+plot_h,
                           outline=self.C['border'])
        # Asse Y: gridlines depth ogni ~50m o suddivisione automatica
        d_step=max(10, int(round((d_max-d_min)/8/10))*10)
        if d_step==0: d_step=10
        d=0
        while d<=d_max:
            y=d2y(d)
            c.create_line(mg_l,y,mg_l+plot_w,y,fill=self.C['panel'])
            c.create_text(mg_l-4,y,text=f"{int(d)}m",anchor='e',
                          fill=self.C['gray'],font=('Segoe UI',8))
            d+=d_step
        # Asse X: 6-7 ticks tempo
        n_ticks=6
        for i in range(n_ticks+1):
            t=t_min+(t_max-t_min)*i/n_ticks
            x=t2x(t)
            c.create_line(x,mg_t+plot_h,x,mg_t+plot_h+4,fill=self.C['border'])
            try:
                lbl=datetime.fromtimestamp(t,tz=timezone.utc).strftime('%H:%M:%S')
            except Exception:
                lbl='—'
            c.create_text(x,mg_t+plot_h+6,text=lbl,anchor='n',
                          fill=self.C['gray'],font=('Segoe UI',8))

        # Curva USBL (blu)
        pts=[(t2x(usbl_t[i]),d2y(usbl_d[i]))
             for i in range(len(usbl_t)) if valid_u[i]]
        if len(pts)>=2:
            flat=[v for p in pts for v in p]
            c.create_line(flat,fill=self.C['blue'],width=2,smooth=True,tags='usbl')

        # Curva CTD (rossa, shiftata)
        if have_ctd:
            pts=[(t2x(ctd_t_sh[i]),d2y(ctd_d[i]))
                 for i in range(len(ctd_t_sh)) if valid_c[i]]
            if len(pts)>=2:
                flat=[v for p in pts for v in p]
                c.create_line(flat,fill=self.C['red'],width=2,smooth=True,
                              tags='ctd_curve')

        # Legenda — sempre quella USBL; CTD solo se la curva è effettivamente disegnata
        c.create_rectangle(mg_l+6,mg_t-16,mg_l+18,mg_t-8,
                           fill=self.C['blue'],outline='')
        c.create_text(mg_l+22,mg_t-12,text='USBL',anchor='w',
                      fill=self.C['fg'],font=('Segoe UI',9,'bold'))
        if have_ctd:
            c.create_rectangle(mg_l+70,mg_t-16,mg_l+82,mg_t-8,
                               fill=self.C['red'],outline='')
            c.create_text(mg_l+86,mg_t-12,
                          text=f"CTD (shift {shift_now:+.1f}s)",
                          anchor='w',fill=self.C['fg'],font=('Segoe UI',9,'bold'))
            if sign_mismatch:
                c.create_text(mg_l+plot_w-8, mg_t-12,
                              text="⚠ depth segno opposto USBL/CTD → confronto su |depth|",
                              anchor='e', fill=self.C['yellow'],
                              font=('Segoe UI',8,'italic'))
        else:
            c.create_text(mg_l+70,mg_t-12,
                          text="(no CTD loaded)",
                          anchor='w',fill=self.C['gray'],font=('Segoe UI',9,'italic'))

        # Salva stato per drag
        self._overlay_t_min=t_min
        self._overlay_t_max=t_max
        self._overlay_pix_per_sec=plot_w/(t_max-t_min)
        self._overlay_plot_box=(mg_l,mg_t,mg_l+plot_w,mg_t+plot_h)

        # Aggiorna status (residuo)
        self._update_overlay_status()

    def _update_overlay_status(self):
        if not hasattr(self,'lbl_overlay_status'): return
        try: shift = float(self.ctd_ts_offset.get())
        except Exception: shift = 0.0
        if (self.usbl_df is None or self.ctd_df_validated is None
                or '_depth_key' not in self.ctd_df_validated.columns
                or 'unix_ts' not in self.ctd_df_validated.columns):
            self.lbl_overlay_status.config(
                text=f"shift: {shift:+.2f} s   |ΔD| median: — (CTD non disponibile)",
                fg=self.C['gray'])
            return
        usbl_t=self.usbl_df['unix_ts'].values
        # Confronto sempre su |depth| per gestire il caso in cui USBL e CTD
        # adottino segno opposto (es. USBL altitudine negativa, CTD positivo)
        usbl_d=np.abs(self.usbl_df['depth'].values)
        ctd_t=self.ctd_df_validated['unix_ts'].values+shift
        ctd_d=np.abs(self.ctd_df_validated['_depth_key'].values)
        # Campiona sull'intersezione temporale
        t_lo=max(float(np.nanmin(usbl_t)), float(np.nanmin(ctd_t)))
        t_hi=min(float(np.nanmax(usbl_t)), float(np.nanmax(ctd_t)))
        if not np.isfinite(t_lo) or not np.isfinite(t_hi) or t_hi<=t_lo:
            self.lbl_overlay_status.config(
                text=f"shift: {shift:+.2f} s   |ΔD| median: — (no overlap)",
                fg=self.C['yellow'])
            return
        # Ordina per searchsorted
        order_c=np.argsort(ctd_t)
        ctd_ts_sorted=ctd_t[order_c]; ctd_dp_sorted=ctd_d[order_c]
        diffs=[]
        for ti in np.linspace(t_lo,t_hi,40):
            iu=int(np.searchsorted(usbl_t,ti)); iu=min(iu,len(usbl_t)-1)
            ic=int(np.searchsorted(ctd_ts_sorted,ti)); ic=min(ic,len(ctd_ts_sorted)-1)
            if not (np.isnan(usbl_d[iu]) or np.isnan(ctd_dp_sorted[ic])):
                diffs.append(abs(float(usbl_d[iu])-float(ctd_dp_sorted[ic])))
        if diffs:
            med=float(np.median(diffs)); mx=float(np.max(diffs))
            tol=self.ctd_depth_tol.get()
            col=self.C['green'] if med<=tol else (self.C['yellow'] if med<=tol*2 else self.C['red'])
            self.lbl_overlay_status.config(
                text=(f"shift: {shift:+.2f} s   |ΔD| median: {med:.2f} m   "
                      f"max: {mx:.2f} m   (tolerance: {tol:.1f} m)"),
                fg=col)
        else:
            self.lbl_overlay_status.config(
                text=f"shift: {shift:+.2f} s   |ΔD| median: —",
                fg=self.C['yellow'])

    def _overlay_press(self,e):
        if (self.ctd_df_validated is None
                or '_depth_key' not in self.ctd_df_validated.columns
                or 'unix_ts' not in self.ctd_df_validated.columns):
            return
        if hasattr(self,'_overlay_plot_box'):
            x0,y0,x1,y1=self._overlay_plot_box
            if not (x0<=e.x<=x1 and y0<=e.y<=y1): return
        self._overlay_drag_active=True
        self._overlay_drag_x0=e.x
        try: self._overlay_shift_at_press = float(self.ctd_ts_offset.get())
        except Exception: self._overlay_shift_at_press = 0.0
        try: self.depth_overlay_canvas.config(cursor='fleur')
        except Exception: pass

    def _overlay_drag(self,e):
        if not self._overlay_drag_active: return
        if self._overlay_pix_per_sec<=0: return
        dx=e.x-self._overlay_drag_x0
        delta_sec=dx/self._overlay_pix_per_sec
        # Aggiorna direttamente l'entry CTD shift (s) — l'utente lo vede live
        self.ctd_ts_offset.set(round(self._overlay_shift_at_press+delta_sec, 2))
        self._draw_depth_overlay()

    def _overlay_release(self,e):
        self._overlay_drag_active=False
        try: self.depth_overlay_canvas.config(cursor='')
        except Exception: pass
        # Non applico permanentemente: l'utente preme "✅ Apply" se vuole consolidare
        try: self._build_alignment_table()
        except Exception: pass

    def _apply_overlay_shift(self):
        """Consolida lo shift corrente nel df CTD validato e azzera il campo,
        così il valore visualizzato torna a 0 come nuova baseline."""
        try: delta = float(self.ctd_ts_offset.get())
        except Exception: delta = 0.0
        if abs(delta)<0.01:
            self._log('info','CTD shift già 0 — niente da consolidare.')
            return
        if (self.ctd_df_validated is None
                or 'unix_ts' not in self.ctd_df_validated.columns):
            messagebox.showwarning("CTD","CTD non valida o senza timestamp."); return
        self.ctd_df_validated['unix_ts']=self.ctd_df_validated['unix_ts']+delta
        if self.ctd_df is not None and 'unix_ts' in self.ctd_df.columns:
            self.ctd_df['unix_ts']=self.ctd_df['unix_ts']+delta
        # Aggiorna anche il campo "Corrected CTD start timestamp"
        try:
            new_t0=datetime.fromtimestamp(
                float(self.ctd_df_validated['unix_ts'].iloc[0]),
                tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            self.ctd_ts_corrected.set(new_t0)
        except Exception: pass
        self._log('ok',f"✅ CTD shift consolidato: {delta:+.2f}s (baseline aggiornata)")
        self.ctd_ts_offset.set(0.0)
        self._build_alignment_table()
        self._draw_depth_overlay()

    def _reset_overlay_shift(self):
        """Azzera il campo CTD shift senza modificare il df validato."""
        self.ctd_ts_offset.set(0.0)
        self._draw_depth_overlay()
        self._build_alignment_table()

    def _apply_ctd_time_only(self):
        """Calcola lo shift necessario perché il primo record CTD corrisponda
        al timestamp digitato nel campo 'Corrected CTD start timestamp', e lo
        scrive in 'CTD shift (s)' (live, non baked). L'utente può poi raffinare
        col drag/manual edit e premere ✅ Apply per consolidare."""
        if self.ctd_df_validated is None:
            messagebox.showwarning("CTD","Valida prima la CTD nella scheda 3."); return
        if 'unix_ts' not in self.ctd_df_validated.columns:
            messagebox.showwarning("CTD",
                "La CTD è in modalità 'depth' o non ha unix_ts. "
                "Questo pulsante è utile solo per CTD sincronizzata 'by time'."); return
        ts_str=self.ctd_ts_corrected.get().strip()
        if not ts_str:
            messagebox.showwarning("CTD",
                "Inserisci un timestamp valido in 'Corrected CTD start timestamp'\n"
                "(formato YYYY-MM-DDTHH:MM:SS)."); return
        try:
            dt_c=datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
        except Exception as e:
            messagebox.showerror("CTD",f"Timestamp non valido: {e}"); return
        ctd_ts=self.ctd_df_validated['unix_ts'].dropna()
        if not len(ctd_ts):
            messagebox.showerror("CTD","La CTD non ha timestamp validi parsati."); return
        raw_t0=float(ctd_ts.iloc[0])
        delta=dt_c.timestamp()-raw_t0
        # Scrive nel campo "CTD shift (s)" (preview live)
        self.ctd_ts_offset.set(round(delta, 2))
        self._log('ok',f"⏱ CTD shift impostato a {delta:+.1f} s (premi ✅ Apply per consolidare)")
        self._build_alignment_table()
        self._draw_depth_overlay()

    def _auto_fix_ctd_time_from_depth(self):
        """Per CTD 'by_time': trova lo shift che allinea l'INTERA curva depth_CTD
        a depth_USBL, e lo scrive in 'CTD shift (s)' come preview live (non bake
        permanente).
        Nota: non usa più un singolo punto/frame come riferimento. Un match su un
        solo punto è ambiguo quando il profilo di profondità torna su valori
        simili più volte (es. vicino a 0 sia all'inizio in discesa che alla fine
        in risalita): in quel caso il punto più vicino può trovarsi a ore di
        distanza nel tempo, producendo uno shift enorme e sbagliato (la causa
        dell'effetto "allontana invece di avvicinare"). Confrontando tutta la
        forma delle due curve con una ricerca a griglia (grossolana poi fine)
        l'ambiguità si risolve, perché il punto giusto è quello dove l'INTERO
        profilo combacia, non solo un valore isolato."""
        if self.ctd_df_validated is None or self.usbl_df is None:
            messagebox.showwarning("CTD","Carica/valida USBL e CTD prima."); return
        if self.ctd_sync_mode.get()!='time':
            messagebox.showinfo("CTD",
                "Auto-fix funziona solo con CTD sincronizzata 'by time'.\n"
                "(In modalità 'by depth' il tempo CTD è ignorato per costruzione.)"); return
        if 'unix_ts' not in self.ctd_df_validated.columns or '_depth_key' not in self.ctd_df_validated.columns:
            messagebox.showwarning("CTD",
                "La CTD necessita di colonna timestamp e di colonna depth."); return

        # Serie USBL (riferimento, baseline) e CTD (baseline, da correggere),
        # pulite da NaN e ordinate per tempo crescente.
        usbl_clean=self.usbl_df[['unix_ts','depth']].dropna()
        ctd_clean=self.ctd_df_validated[['unix_ts','_depth_key']].dropna()
        if len(usbl_clean)<5 or len(ctd_clean)<5:
            messagebox.showwarning("CTD","Dati USBL/CTD insufficienti (depth/tempo) per l'auto-fix."); return
        usbl_ts=usbl_clean['unix_ts'].values.astype(float)
        usbl_depth=np.abs(usbl_clean['depth'].values.astype(float))
        order=np.argsort(usbl_ts); usbl_ts=usbl_ts[order]; usbl_depth=usbl_depth[order]
        ctd_ts=ctd_clean['unix_ts'].values.astype(float)
        ctd_depth=np.abs(ctd_clean['_depth_key'].values.astype(float))
        order=np.argsort(ctd_ts); ctd_ts=ctd_ts[order]; ctd_depth=ctd_depth[order]

        def score(shift, min_overlap_frac=0.3):
            """Errore mediano |depth_CTD(shift) - depth_USBL| sulla sovrapposizione
            temporale. Scarta gli shift con sovrapposizione insufficiente, altrimenti
            uno shift enorme basato su 2-3 punti casuali potrebbe vincere a torto."""
            t_sh=ctd_ts+shift
            lo,hi=t_sh[0],t_sh[-1]
            mask=(usbl_ts>=lo)&(usbl_ts<=hi)
            if mask.sum()<max(5, min_overlap_frac*len(usbl_ts)):
                return np.inf
            interp_d=np.interp(usbl_ts[mask], t_sh, ctd_depth)
            return float(np.nanmedian(np.abs(interp_d-usbl_depth[mask])))

        # Range di ricerca: tutta la finestra in cui le due serie possono sovrapporsi
        lo_shift=usbl_ts[0]-ctd_ts[-1]
        hi_shift=usbl_ts[-1]-ctd_ts[0]
        if hi_shift<=lo_shift:
            messagebox.showerror("CTD","Le due serie temporali non hanno una sovrapposizione possibile."); return

        # STEP 1: ricerca grossolana su tutto il range plausibile
        coarse_step=10.0
        coarse_shifts=np.arange(lo_shift, hi_shift, coarse_step)
        coarse_scores=np.array([score(s) for s in coarse_shifts])
        if np.all(np.isinf(coarse_scores)):
            messagebox.showerror("CTD","Auto-fix non ha trovato una sovrapposizione utile tra USBL e CTD."); return
        best_coarse=float(coarse_shifts[int(np.nanargmin(coarse_scores))])

        # STEP 2: ricerca fine attorno al miglior candidato grossolano
        fine_shifts=np.arange(best_coarse-coarse_step, best_coarse+coarse_step, 0.2)
        fine_scores=np.array([score(s) for s in fine_shifts])
        best_idx=int(np.nanargmin(fine_scores))
        best_shift=float(fine_shifts[best_idx]); best_err=float(fine_scores[best_idx])

        # Scrive lo shift ASSOLUTO nel campo live (non si somma a uno shift già
        # pendente: stessa convenzione usata da drag manuale e "Imposta da data/ora",
        # dove self.ctd_ts_offset è sempre lo spostamento totale rispetto alla
        # baseline, non un incremento).
        new_shift=round(best_shift, 2)
        self.ctd_ts_offset.set(new_shift)
        self._log('ok',
            f"🌊 Auto-fix CTD (match su tutta la curva depth): shift {new_shift:+.1f}s "
            f"(errore mediano residuo {best_err:.2f} m) "
            f"(live, premi ✅ Apply per consolidare)")
        self._build_alignment_table()
        self._draw_depth_overlay()

    def _reset_sync(self):
        self.video_delay.set(0.0); self.ctd_ts_offset.set(0.0)
        self.ctd_ts_corrected.set('')
        if self._video_meta_unix is not None:
            dt=datetime.fromtimestamp(self._video_meta_unix,tz=timezone.utc)
            self.video_ts_corrected.set(dt.strftime('%Y-%m-%dT%H:%M:%S'))
        else:
            self.video_ts_corrected.set('')
        self._usbl_touchdown_unix=None
        self.lbl_usbl_touchdown.config(text="Touchdown USBL: non ancora selezionato",fg=self.C['gray'])
        # Ricarica CTD dal disco per annullare gli shift manuali
        if self.ctd_df_validated is not None and self.ctd_path.get():
            try:
                self.ctd_df_validated=load_ctd(
                    self.ctd_path.get(),
                    sep=self.ctd_sep.get() if self.ctd_sep.get()!='Auto' else None,
                    has_header=self.ctd_header.get(),
                    ts_params=self._build_ctd_ts_params(),
                    depth_col=self.ctd_depth_col.get(),
                    param_cols=[c for c,v in self.ctd_selected if v.get()],
                    sync_mode=self.ctd_sync_mode.get(),
                    ctd_ts_offset=0.0)
                self._ctd_manual_unix_shift=0.0
                self._log('info','↺ CTD ricaricata (shifts manuali azzerati)')
            except Exception as e:
                self._log('warn',f'Reset CTD: {e}')
        self._apply_sync()
        self._log('info','↺ Reset sincronizzazione')

    def _get_video_ts_offset(self):
        ts_str=self.video_ts_corrected.get().strip()
        if ts_str:
            try: return datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc).timestamp()
            except Exception: pass
        if self._video_meta_unix is not None: return self._video_meta_unix
        if self.usbl_df is not None and len(self.usbl_df): return self.usbl_df['unix_ts'].iloc[0]
        return 0.0

    def _build_alignment_table(self):
        self.align_tree.delete(*self.align_tree.get_children())
        if self.usbl_df is None: return

        # Aggiorna intestazioni colonne CTD in base alla modalità di sync
        ctd_by_depth = (self.ctd_sync_mode.get() == 'depth')
        self.align_tree.heading('time_ctd', text='Depth CTD ref' if ctd_by_depth else 'Time CTD')
        self.align_tree.heading('dt_ctd',   text='Δdepth CTD'   if ctd_by_depth else 'ΔT CTD')
        self.align_tree.heading('depth_ctd', text='Depth CTD')
        self.align_tree.heading('dd_ctd', text='|ΔD vs USBL|')

        video_ts_offset=self._get_video_ts_offset()
        t_start=self.extract_from.get()
        t_end=self.extract_to.get() if self.extract_to.get()>0 else self._video_duration
        if t_end<=t_start: t_end=self._video_duration
        n_samples=10
        sample_times=np.linspace(t_start,min(t_end,t_start+self.interval_sec.get()*n_samples),n_samples)

        depth_diffs=[]   # per status finale
        any_ctd=False
        ctd_t_window=self.assoc_window.get()
        for i,t_video in enumerate(sample_times):
            t_abs=video_ts_offset+t_video
            dt_video=datetime.fromtimestamp(t_abs,tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            usbl_vals=interpolate_usbl(self.usbl_df,t_abs,[],window_sec=9999)
            if usbl_vals is None:
                self.align_tree.insert('','end',
                    values=(i+1,dt_video,'—','—','—','—','—','—','—'),tags=('bad',))
                continue
            ts_arr=self.usbl_df['unix_ts'].values; idx=np.searchsorted(ts_arr,t_abs)
            if idx>=len(ts_arr): idx=len(ts_arr)-1
            dt_usbl_str=datetime.fromtimestamp(ts_arr[idx],tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            delta_usbl=round(abs(t_abs-ts_arr[idx]),1)
            d_usbl=usbl_vals['depth']
            depth_usbl=f"{d_usbl:.1f} m" if not np.isnan(d_usbl) else '—'

            dt_ctd_str='—'; delta_ctd='—'; depth_ctd_str='—'; dd_str='—'
            d_ctd=np.nan
            ctd_idx=None
            # Live CTD shift dal campo "CTD shift (s)"
            try: ctd_shift_live = float(self.ctd_ts_offset.get())
            except Exception: ctd_shift_live = 0.0
            if self.ctd_df_validated is not None:
                any_ctd=True
                dc=self.ctd_depth_col.get()
                if self.ctd_sync_mode.get()=='time' and 'unix_ts' in self.ctd_df_validated.columns:
                    # Aggiungi lo shift live alla serie temporale CTD
                    ctd_ts=self.ctd_df_validated['unix_ts'].values + ctd_shift_live
                    if len(ctd_ts):
                        ctd_idx=int(np.searchsorted(ctd_ts,t_abs))
                        if ctd_idx>=len(ctd_ts): ctd_idx=len(ctd_ts)-1
                        if not np.isnan(ctd_ts[ctd_idx]):
                            dt_ctd_str=datetime.fromtimestamp(ctd_ts[ctd_idx],
                                           tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
                            delta_ctd=round(abs(t_abs-ctd_ts[ctd_idx]),1)
                elif self.ctd_sync_mode.get()=='depth' and '_depth_key' in self.ctd_df_validated.columns:
                    if not np.isnan(d_usbl):
                        ctd_depths=self.ctd_df_validated['_depth_key'].values
                        if len(ctd_depths) and not np.isnan(ctd_depths).all():
                            # Match su |depth| per gestire segno opposto USBL/CTD
                            ctd_idx=int(np.nanargmin(np.abs(np.abs(ctd_depths)-abs(d_usbl))))
                            delta_ctd=round(abs(abs(d_usbl)-abs(ctd_depths[ctd_idx])),2)
                            dt_ctd_str=f"d={ctd_depths[ctd_idx]:.1f}"

                # Depth CTD: SEMPRE visualizzata se ctd_idx è valido
                if ctd_idx is not None and dc and dc in self.ctd_df_validated.columns:
                    try:
                        d_ctd=float(self.ctd_df_validated.iloc[ctd_idx].get(dc,np.nan))
                        if not np.isnan(d_ctd):
                            depth_ctd_str=f"{d_ctd:.1f} m"
                    except Exception:
                        pass
                # Δdepth CTD vs USBL — sempre, basato su |depth| (gestisce segno opposto)
                if not np.isnan(d_ctd) and not np.isnan(d_usbl):
                    dd=abs(abs(d_usbl)-abs(d_ctd))
                    dd_str=f"{dd:.2f}"
                    depth_diffs.append(dd)

            # Tag riga: priorità errore depth > errore time
            tag='ok'
            if isinstance(delta_usbl,(int,float)) and delta_usbl>self.assoc_window.get(): tag='bad'
            elif isinstance(delta_usbl,(int,float)) and delta_usbl>self.assoc_window.get()/2: tag='warn'
            # Override con stato CTD: depth fuori soglia → bad
            if isinstance(dd_str,str) and dd_str!='—':
                try:
                    if float(dd_str)>self.ctd_depth_tol.get(): tag='bad'
                    elif float(dd_str)>self.ctd_depth_tol.get()/2 and tag=='ok': tag='warn'
                except Exception: pass
            # Override con ΔT CTD se sync_mode='time': fuori finestra → bad
            if (self.ctd_sync_mode.get()=='time' and self.ctd_df_validated is not None
                    and isinstance(delta_ctd,(int,float)) and delta_ctd>ctd_t_window):
                tag='bad'
            self.align_tree.insert('','end',
                values=(i+1,dt_video,dt_usbl_str,f"{delta_usbl}s",depth_usbl,
                        dt_ctd_str, delta_ctd, depth_ctd_str, dd_str),tags=(tag,))

        # Aggiorna status validazione depth CTD
        self._update_ctd_depth_status(depth_diffs, any_ctd)

    def _update_ctd_depth_status(self, depth_diffs, any_ctd):
        """Aggiorna l'etichetta status e la flag _ctd_depth_ok."""
        if not hasattr(self,'lbl_ctd_depth_status'): return
        if not any_ctd:
            self.lbl_ctd_depth_status.config(
                text="(nessuna CTD caricata — depth check non applicabile)",
                fg=self.C['gray'])
            self._ctd_depth_ok=True
            return
        if not depth_diffs:
            self.lbl_ctd_depth_status.config(
                text="⚠ depth CTD/USBL non calcolabile (manca depth in uno dei due)",
                fg=self.C['yellow'])
            self._ctd_depth_ok=False
            return
        med=float(np.median(depth_diffs)); mx=float(np.max(depth_diffs))
        tol=self.ctd_depth_tol.get()
        if med<=tol and mx<=tol*2:
            self.lbl_ctd_depth_status.config(
                text=f"✅ depth CTD≈USBL  (mediana ΔD={med:.2f} m, max={mx:.2f} m, soglia={tol:.1f} m)",
                fg=self.C['green'])
            self._ctd_depth_ok=True
        else:
            self.lbl_ctd_depth_status.config(
                text=(f"❌ depth CTD ≠ USBL  (mediana ΔD={med:.2f} m, max={mx:.2f} m, "
                      f"soglia={tol:.1f} m)  → estrazione bloccata"),
                fg=self.C['red'])
            self._ctd_depth_ok=False

    # ── USBL depth plot ───────────────────────────────────────────────────────
    def _draw_usbl_depth_plot(self):
        c=self.usbl_canvas; c.delete('all')
        W=c.winfo_width() or 700; H=180; mg=30
        if self.usbl_df is None or len(self.usbl_df)==0:
            c.create_text(W//2,H//2,text="Carica e valida USBL per vedere il profilo depth",
                          fill=self.C['gray'],font=('Segoe UI',9)); return
        ts=self.usbl_df['unix_ts'].values; depths=self.usbl_df['depth'].values
        valid=~np.isnan(depths)
        if valid.sum()<2:
            c.create_text(W//2,H//2,text="Profondità non disponibile",fill=self.C['gray'],font=('Segoe UI',9)); return
        ts_v=ts[valid]; d_v=depths[valid]
        t_min,t_max=ts_v.min(),ts_v.max(); span=max(t_max-t_min,1)
        d_min,d_max=d_v.min(),d_v.max(); d_span=max(d_max-d_min,1)
        def tx(t): return mg+(t-t_min)/span*(W-2*mg)
        def ty(d): return mg+(d-d_min)/d_span*(H-2*mg)  # depth aumenta verso il basso
        # Linea profilo
        pts=[(tx(t),ty(d)) for t,d in zip(ts_v,d_v)]
        for i in range(len(pts)-1):
            c.create_line(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=self.C['blue'],width=1.5)
        # Etichette assi
        c.create_text(mg-5,mg,text=f"{d_min:.0f}m",fill=self.C['gray'],font=('Segoe UI',8),anchor='e')
        c.create_text(mg-5,H-mg,text=f"{d_max:.0f}m",fill=self.C['gray'],font=('Segoe UI',8),anchor='e')
        c.create_text(mg,H-10,text=datetime.fromtimestamp(t_min,tz=timezone.utc).strftime('%H:%M:%S'),
                      fill=self.C['gray'],font=('Segoe UI',8),anchor='w')
        c.create_text(W-mg,H-10,text=datetime.fromtimestamp(t_max,tz=timezone.utc).strftime('%H:%M:%S'),
                      fill=self.C['gray'],font=('Segoe UI',8),anchor='e')
        # Marker touchdown selezionato
        if self._usbl_touchdown_unix is not None:
            x=tx(self._usbl_touchdown_unix)
            c.create_line(x,5,x,H-15,fill=self.C['green'],width=2)
            c.create_text(x,H-25,text='▲ touchdown',fill=self.C['green'],font=('Segoe UI',8))
        # Marker posizione video corrente
        vt=self._get_video_ts_offset()+self.video_pos_var.get()
        if t_min<=vt<=t_max:
            x=tx(vt)
            c.create_line(x,5,x,H-15,fill=self.C['yellow'],width=1,dash=(3,2))
            c.create_text(x,8,text='▼ video',fill=self.C['yellow'],font=('Segoe UI',8))

    def _usbl_canvas_click(self,e):
        if self.usbl_df is None or len(self.usbl_df)==0: return
        c=self.usbl_canvas; W=c.winfo_width() or 700; mg=30
        ts=self.usbl_df['unix_ts'].values; depths=self.usbl_df['depth'].values
        valid=~np.isnan(depths)
        if valid.sum()<2: return
        ts_v=ts[valid]; t_min,t_max=ts_v.min(),ts_v.max()
        span=max(t_max-t_min,1)
        # Inverso di tx
        if e.x<mg or e.x>W-mg: return
        t_clicked=t_min+(e.x-mg)/(W-2*mg)*span
        # Trova punto USBL più vicino e prendi quello
        idx=np.argmin(np.abs(ts_v-t_clicked))
        self._usbl_touchdown_unix=ts_v[idx]
        d_at=depths[valid][idx]
        dt=datetime.fromtimestamp(ts_v[idx],tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        self.lbl_usbl_touchdown.config(
            text=f"Touchdown USBL: {dt}  |  depth: {d_at:.1f} m",fg=self.C['green'])
        self._draw_usbl_depth_plot()

    # ── CTD depth plot (per sync_mode=depth) ──────────────────────────────────
    def _draw_ctd_depth_plot(self):
        c=self.ctd_canvas; c.delete('all')
        W=c.winfo_width() or 700; H=180; mg=30
        if self.ctd_df_validated is None or '_depth_key' not in self.ctd_df_validated.columns:
            c.create_text(W//2,H//2,text="Valida CTD per vedere il profilo",
                          fill=self.C['gray'],font=('Segoe UI',9)); return
        depths=self.ctd_df_validated['_depth_key'].values
        valid=~np.isnan(depths)
        if valid.sum()<2:
            c.create_text(W//2,H//2,text="Depth non disponibile",fill=self.C['gray'],font=('Segoe UI',9)); return
        # Plot depth vs index (tempo se disponibile, sennò index)
        if 'unix_ts' in self.ctd_df_validated.columns:
            x_arr=self.ctd_df_validated['unix_ts'].values
            x_label_left=datetime.fromtimestamp(x_arr[0],tz=timezone.utc).strftime('%H:%M:%S')
            x_label_right=datetime.fromtimestamp(x_arr[-1],tz=timezone.utc).strftime('%H:%M:%S')
        else:
            x_arr=np.arange(len(depths))
            x_label_left='0'; x_label_right=str(len(depths))
        x_min,x_max=x_arr.min(),x_arr.max(); x_span=max(x_max-x_min,1)
        d_min,d_max=np.nanmin(depths),np.nanmax(depths); d_span=max(d_max-d_min,1)
        def tx(x): return mg+(x-x_min)/x_span*(W-2*mg)
        def ty(d): return mg+(d-d_min)/d_span*(H-2*mg)
        pts=[(tx(x_arr[i]),ty(depths[i])) for i in range(len(depths)) if not np.isnan(depths[i])]
        for i in range(len(pts)-1):
            c.create_line(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=self.C['green'],width=1.5)
        c.create_text(mg-5,mg,text=f"{d_min:.0f}m",fill=self.C['gray'],font=('Segoe UI',8),anchor='e')
        c.create_text(mg-5,H-mg,text=f"{d_max:.0f}m",fill=self.C['gray'],font=('Segoe UI',8),anchor='e')
        c.create_text(mg,H-10,text=x_label_left,fill=self.C['gray'],font=('Segoe UI',8),anchor='w')
        c.create_text(W-mg,H-10,text=x_label_right,fill=self.C['gray'],font=('Segoe UI',8),anchor='e')
        # Mostra finestra selezionata
        f_idx,t_idx=self.ctd_depth_window_idx
        if f_idx is not None and t_idx is not None:
            xf=tx(x_arr[f_idx]); xt=tx(x_arr[t_idx])
            if xf>xt: xf,xt=xt,xf
            c.create_rectangle(xf,5,xt,H-5,fill=self.C['purple'],outline='',stipple='gray25')

    def _ctd_canvas_click(self,e):
        self._ctd_drag_start=e.x
    def _ctd_canvas_drag(self,e):
        if self._ctd_drag_start is None: return
        c=self.ctd_canvas; c.delete('drag')
        c.create_rectangle(self._ctd_drag_start,5,e.x,c.winfo_height()-5,
                           fill=self.C['purple'],outline='',stipple='gray25',tags=('drag',))
    def _ctd_canvas_release(self,e):
        if self._ctd_drag_start is None or self.ctd_df_validated is None: return
        c=self.ctd_canvas; W=c.winfo_width() or 700; mg=30
        x0,x1=sorted([self._ctd_drag_start,e.x])
        if 'unix_ts' in self.ctd_df_validated.columns:
            x_arr=self.ctd_df_validated['unix_ts'].values
        else:
            x_arr=np.arange(len(self.ctd_df_validated))
        x_min,x_max=x_arr.min(),x_arr.max(); x_span=max(x_max-x_min,1)
        v0=x_min+(x0-mg)/(W-2*mg)*x_span
        v1=x_min+(x1-mg)/(W-2*mg)*x_span
        f_idx=int(np.argmin(np.abs(x_arr-v0))); t_idx=int(np.argmin(np.abs(x_arr-v1)))
        if f_idx>t_idx: f_idx,t_idx=t_idx,f_idx
        self.ctd_depth_window_idx=(f_idx,t_idx)
        self.ctd_window_lbl.config(
            text=f"Finestra: {f_idx}–{t_idx} ({t_idx-f_idx+1} righe)",fg=self.C['green'])
        self._draw_ctd_depth_plot()
        self._ctd_drag_start=None

    def _select_downcast(self):
        if self.ctd_df_validated is None or '_depth_key' not in self.ctd_df_validated.columns: return
        depths=self.ctd_df_validated['_depth_key'].values
        # Downcast = da inizio fino al massimo depth
        valid=~np.isnan(depths)
        if valid.sum()<2: return
        max_idx=int(np.nanargmax(depths))
        self.ctd_depth_window_idx=(0,max_idx)
        self.ctd_window_lbl.config(text=f"Downcast: 0–{max_idx} ({max_idx+1} righe)",fg=self.C['green'])
        self._draw_ctd_depth_plot()

    def _select_upcast(self):
        if self.ctd_df_validated is None or '_depth_key' not in self.ctd_df_validated.columns: return
        depths=self.ctd_df_validated['_depth_key'].values
        valid=~np.isnan(depths)
        if valid.sum()<2: return
        max_idx=int(np.nanargmax(depths))
        self.ctd_depth_window_idx=(max_idx,len(depths)-1)
        self.ctd_window_lbl.config(text=f"Upcast: {max_idx}–{len(depths)-1}",fg=self.C['green'])
        self._draw_ctd_depth_plot()

    def _select_all_ctd(self):
        if self.ctd_df_validated is None: return
        self.ctd_depth_window_idx=(0,len(self.ctd_df_validated)-1)
        self.ctd_window_lbl.config(text="Finestra: tutto",fg=self.C['gray'])
        self._draw_ctd_depth_plot()

    # ── Video navigation ──────────────────────────────────────────────────────
    def _on_video_slider(self,val):
        t=float(val); self.lbl_video_pos.config(text=f"{t:.1f} s")
        # Aggiorna anche il tempo UTC corrispondente
        self._refresh_video_pos_time(t)
        self._show_frame_at(t)

    def _refresh_video_pos_time(self,t_sec):
        """Aggiorna l'entry 'Time UTC' in base a t_sec (secondi nel video)."""
        if not hasattr(self,'video_pos_time'): return
        try:
            offset=self._get_video_ts_offset()
            if offset and offset>0:
                dt=datetime.fromtimestamp(offset+float(t_sec),tz=timezone.utc)
                self.video_pos_time.set(dt.strftime('%Y-%m-%dT%H:%M:%S'))
            else:
                self.video_pos_time.set('—')
        except Exception:
            self.video_pos_time.set('—')

    def _goto_video_seconds(self,t_sec):
        """Salta a una posizione (secondi) e ridisegna."""
        try:
            t=float(t_sec)
            t=max(0.0, min(t, max(self._video_duration,0.0)))
            self.video_pos_var.set(round(t,2))
            self.lbl_video_pos.config(text=f"{t:.1f} s")
            self._refresh_video_pos_time(t)
            self._show_frame_at(t)
            self._build_alignment_table()
        except Exception as e:
            self._log('warn',f'Posizione non valida: {e}')

    def _goto_video_time(self,ts_str):
        """Salta a un timestamp UTC (HH:MM:SS o YYYY-MM-DDTHH:MM:SS).
        Calcola i secondi come (target_unix - video_ts_offset)."""
        if not ts_str or ts_str.strip() in ('','—','-'):
            return
        try:
            offset=self._get_video_ts_offset()
            if not offset or offset<=0:
                messagebox.showwarning("Time seek",
                    "Imposta prima un 'video start timestamp' valido\n"
                    "(scheda 1 o campo 'Corrected video start timestamp').")
                return
            s=ts_str.strip()
            target=None
            # Tentativi di parsing: ISO completo, poi solo HH:MM:SS combinato col giorno del start
            for fmt in ('%Y-%m-%dT%H:%M:%S','%Y-%m-%d %H:%M:%S','%Y-%m-%dT%H:%M','%Y-%m-%d %H:%M'):
                try:
                    dt=datetime.strptime(s,fmt).replace(tzinfo=timezone.utc)
                    target=dt.timestamp(); break
                except Exception: continue
            if target is None:
                # Solo ora HH:MM:SS → eredita la data dal video_ts_offset
                m=re.match(r'^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$',s)
                if m:
                    base_d=datetime.fromtimestamp(offset,tz=timezone.utc).date()
                    h=int(m.group(1)); mm=int(m.group(2)); ss=int(m.group(3) or 0)
                    target=datetime(base_d.year,base_d.month,base_d.day,h,mm,ss,
                                    tzinfo=timezone.utc).timestamp()
            if target is None:
                messagebox.showerror("Time seek",
                    f"Timestamp non interpretabile: '{ts_str}'.\n"
                    "Esempi validi: 2020-10-25T11:55:00  oppure  11:55:00")
                return
            t_sec=target-offset
            if t_sec<0 or t_sec>self._video_duration+1:
                messagebox.showwarning("Time seek",
                    f"Il tempo richiesto è fuori dalla durata del video.\n"
                    f"Durata: {self._video_duration:.1f}s — Calcolato: {t_sec:.1f}s")
                return
            self._goto_video_seconds(t_sec)
        except Exception as e:
            self._log('warn',f'Time seek fallito: {e}')

    # ── Sincronizzazione tempo↔secondi per extract_from / extract_to ─────────
    def _sync_extract_time_from_secs(self, which):
        """Aggiorna l'entry tempo UTC partendo dai secondi."""
        try:
            offset=self._get_video_ts_offset()
            if not offset or offset<=0: return
            sec=self.extract_from.get() if which=='from' else self.extract_to.get()
            target=offset+float(sec)
            ts=datetime.fromtimestamp(target,tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            (self.extract_from_time if which=='from' else self.extract_to_time).set(ts)
            self._build_alignment_table()
        except Exception:
            pass

    def _sync_extract_secs_from_time(self, which):
        """Aggiorna i secondi partendo dall'entry tempo UTC."""
        try:
            offset=self._get_video_ts_offset()
            if not offset or offset<=0:
                messagebox.showwarning("Time", "Imposta prima un timestamp di start del video.")
                return
            ts_str=(self.extract_from_time if which=='from' else self.extract_to_time).get().strip()
            if ts_str in ('','—','-'):
                if which=='to': self.extract_to.set(0.0)  # 0 = end of video
                self._build_alignment_table(); return
            target=None
            for fmt in ('%Y-%m-%dT%H:%M:%S','%Y-%m-%d %H:%M:%S','%Y-%m-%dT%H:%M','%Y-%m-%d %H:%M'):
                try:
                    target=datetime.strptime(ts_str,fmt).replace(tzinfo=timezone.utc).timestamp(); break
                except Exception: continue
            if target is None:
                m=re.match(r'^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$',ts_str)
                if m:
                    base_d=datetime.fromtimestamp(offset,tz=timezone.utc).date()
                    h=int(m.group(1)); mm=int(m.group(2)); ss=int(m.group(3) or 0)
                    target=datetime(base_d.year,base_d.month,base_d.day,h,mm,ss,
                                    tzinfo=timezone.utc).timestamp()
            if target is None:
                messagebox.showerror("Time","Formato non valido.\n"
                    "Esempi: 2020-10-25T11:55:00  oppure  11:55:00")
                return
            sec=max(0.0, target-offset)
            (self.extract_from if which=='from' else self.extract_to).set(round(sec,1))
            self._build_alignment_table()
        except Exception as e:
            self._log('warn',f'Time→secs fallito: {e}')

    def _step_video(self,delta_sec):
        cur=self.video_pos_var.get()
        new=max(0.0,min(self._video_duration,cur+delta_sec))
        self.video_pos_var.set(new); self._show_frame_at(new)

    def _show_frame_at(self,t_sec):
        if not self.video_path.get(): return
        try:
            cap=cv2.VideoCapture(self.video_path.get())
            fps=cap.get(cv2.CAP_PROP_FPS) or self._video_fps
            cap.set(cv2.CAP_PROP_POS_FRAMES,max(0,int(t_sec*fps)))
            ret,frame=cap.read(); cap.release()
            if not ret: return
            h,w=frame.shape[:2]; scale=min(560/w,315/h)
            frame=cv2.resize(frame,(int(w*scale),int(h*scale)))
            frame=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
            img=ImageTk.PhotoImage(Image.fromarray(frame))
            self.frame_preview_lbl.config(image=img,text='',width=0,height=0)
            self.frame_preview_lbl._img=img
            self._draw_usbl_depth_plot()
        except Exception as e:
            self.frame_preview_lbl.config(text=f"Errore: {e}")

    # ── All-timestamps picker ─────────────────────────────────────────────────
    def _gather_all_video_timestamps(self, video_path):
        """Restituisce una lista di dict con tutti i timestamp disponibili:
            {'key': str, 'source': str, 'ts': float|None, 'tc': (h,m,s)|None,
             'pretty': str, 'reliability': 'high'|'med'|'low'}
        Reliability = 'high' solo per sorgenti che dovrebbero riflettere
        la data di registrazione effettiva (encoded_date, tagged_date,
        Time code, ecc.). 'file_creation_date' e simili sono 'low' perché
        spesso coincidono col file system, non con la registrazione."""
        out = []
        # Lista dei nomi attributo che, anche se vengono dal container, sono
        # in realtà di livello filesystem (cambiano se copi il file).
        FS_LIKE = ('file_creation_date', 'file_last_modification_date',
                   'file_modified_date', 'file_creation', 'last_modification')

        # ── Filesystem ────────────────────────────────────────────────────────
        try:
            st = os.stat(video_path)
            for label, attr in (('FS — modification time (mtime)', 'st_mtime'),
                                ('FS — last access time (atime)', 'st_atime'),
                                ('FS — change/inode time (ctime)', 'st_ctime')):
                v = getattr(st, attr, None)
                if v:
                    out.append({'key': f'fs_{attr}', 'source': label,
                                'ts': float(v), 'tc': None, 'reliability': 'low',
                                'pretty': datetime.fromtimestamp(float(v),
                                            tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')})
            # Su Windows st_birthtime non è disponibile sempre — provalo
            bt = getattr(st, 'st_birthtime', None)
            if bt:
                out.append({'key': 'fs_btime', 'source': 'FS — birth time (creation)',
                            'ts': float(bt), 'tc': None, 'reliability': 'low',
                            'pretty': datetime.fromtimestamp(float(bt),
                                        tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')})
        except Exception as e:
            self._log('warn', f'[ts] FS stat failed: {e}')

        # ── Sidecar .mov.txt ──────────────────────────────────────────────────
        base, _ = os.path.splitext(video_path)
        sidecar_candidates = [video_path+'.txt', base+'.txt',
                              base+'.mediainfo.txt', base+'.MediaInfo.txt']
        sidecar_used = None; sidecar_count = 0
        for sc in sidecar_candidates:
            try:
                exists = os.path.isfile(sc)
            except Exception: exists = False
            if exists:
                sidecar_used = sc
                txt = _read_text_any_encoding(sc)
                if not txt:
                    self._log('warn', f'[ts] sidecar trovato ma non decodificabile: {sc}')
                    continue
                # Tutte le date
                for key_lbl in ('Encoded date','Tagged date','Recorded date',
                                'File creation date','File last modification date',
                                'Mastered date','Original source form creation date'):
                    rel = ('low' if any(x in key_lbl.lower().replace(' ','_')
                                        for x in FS_LIKE) else 'high')
                    for m in re.finditer(rf'{re.escape(key_lbl)}\s*:\s*([^\r\n]+)',
                                         txt, re.IGNORECASE):
                        ts = _parse_dt_string(m.group(1))
                        if ts is not None:
                            out.append({'key': f'sidecar_{key_lbl.lower().replace(" ","_")}',
                                        'source': f'sidecar — {key_lbl}',
                                        'ts': ts, 'tc': None, 'reliability': rel,
                                        'pretty': datetime.fromtimestamp(ts,
                                                    tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')})
                            sidecar_count += 1
                            break
                # QuickTime TC (HH:MM:SS:FF)
                for key_lbl in ('Time code of first frame','Starting Time code',
                                'Starting timecode'):
                    m = re.search(rf'{re.escape(key_lbl)}\s*:\s*([^\r\n]+)',
                                  txt, re.IGNORECASE)
                    if m:
                        tc = _parse_tc_string(m.group(1))
                        if tc:
                            out.append({'key': f'sidecar_tc',
                                        'source': f'sidecar — {key_lbl} (HH:MM:SS, no date)',
                                        'ts': None, 'tc': tc, 'reliability': 'high',
                                        'pretty': f'{tc[0]:02d}:{tc[1]:02d}:{tc[2]:02d}'})
                            sidecar_count += 1
                            break
                break
        # Diagnostica
        if sidecar_used:
            self._log('info', f'[ts] sidecar usato: {os.path.basename(sidecar_used)} ({sidecar_count} entries)')
        else:
            self._log('info', f'[ts] nessun sidecar .mov.txt trovato. Cercati: '
                              + ', '.join(os.path.basename(p) for p in sidecar_candidates))

        # ── pymediainfo ───────────────────────────────────────────────────────
        pymi_count = 0
        if HAS_MEDIAINFO:
            try:
                mi = MediaInfo.parse(video_path)
                for track in mi.tracks:
                    if (track.track_type or '').lower() == 'general':
                        d = track.to_data() if hasattr(track,'to_data') else {}
                        for k, v in (d or {}).items():
                            kl = k.lower()
                            if any(x in kl for x in ('encoded_date','tagged_date',
                                    'recorded_date','file_creation','mastered_date',
                                    'last_modification')):
                                ts = _parse_dt_string(v)
                                if ts is not None:
                                    # file_creation_date / last_modification = livello filesystem
                                    rel = 'low' if any(x in kl for x in FS_LIKE) else 'high'
                                    out.append({'key': f'pymi_{k}',
                                                'source': f'pymediainfo — {k}',
                                                'ts': ts, 'tc': None, 'reliability': rel,
                                                'pretty': datetime.fromtimestamp(ts,
                                                  tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')})
                                    pymi_count += 1
                    tt = (track.track_type or '').lower()
                    if tt in ('other','time code','time_code'):
                        d = track.to_data() if hasattr(track,'to_data') else {}
                        for k, v in (d or {}).items():
                            if not isinstance(v, str): continue
                            kl = k.lower()
                            if 'time' not in kl and 'tc' not in kl: continue
                            tc = _parse_tc_string(v)
                            if tc:
                                out.append({'key': f'pymi_tc_{k}',
                                            'source': f'pymediainfo — {k} (HH:MM:SS, no date)',
                                            'ts': None, 'tc': tc, 'reliability': 'high',
                                            'pretty': f'{tc[0]:02d}:{tc[1]:02d}:{tc[2]:02d}'})
                                pymi_count += 1
                self._log('info', f'[ts] pymediainfo: {pymi_count} entries')
            except Exception as e:
                self._log('warn', f'[ts] pymediainfo error: {e}')
        else:
            self._log('warn', '[ts] pymediainfo non installato (pip install pymediainfo)')

        # ── MediaInfo CLI subprocess (sempre, non solo come fallback) ─────────
        try:
            txt = _try_mediainfo_cli(video_path)
            if txt:
                res = _parse_mediainfo_text(txt)
                if res[0] is not None:
                    ts = res[0]
                    out.append({'key':'cli_dt','source': 'mediainfo CLI — '+(res[2] or 'date'),
                                'ts': ts, 'tc': None, 'reliability': 'high',
                                'pretty': datetime.fromtimestamp(ts,
                                            tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')})
                if res[1] is not None:
                    h,mm,ss = res[1]
                    out.append({'key':'cli_tc','source': 'mediainfo CLI — '+(res[2] or 'TC'),
                                'ts': None, 'tc': (h,mm,ss), 'reliability': 'high',
                                'pretty': f'{h:02d}:{mm:02d}:{ss:02d}'})
                self._log('info', '[ts] mediainfo CLI: ok')
            else:
                self._log('info', '[ts] mediainfo CLI: non disponibile o nessun output')
        except Exception as e:
            self._log('warn', f'[ts] mediainfo CLI error: {e}')

        # ── Binary tmcd parser (last resort) ──────────────────────────────────
        try:
            tc = _parse_mov_timecode(video_path)
            if tc:
                out.append({'key':'binary_tc','source': 'binary tmcd parser (HH:MM:SS, no date)',
                            'ts': None, 'tc': tc, 'reliability': 'med',
                            'pretty': f'{tc[0]:02d}:{tc[1]:02d}:{tc[2]:02d}'})
        except Exception:
            pass

        # ── Filename: rilevamento generico (sempre presente) ──────────────────
        # ① detection automatica con regex generiche
        try:
            ts_auto, txt, fmt = detect_filename_timestamp(video_path)
            if ts_auto is not None:
                out.append({'key':'fn_auto',
                            'source': f"filename (auto: {fmt})",
                            'ts': float(ts_auto), 'tc': None, 'reliability': 'high',
                            'pretty': datetime.fromtimestamp(ts_auto,
                                        tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')})
        except Exception:
            pass
        # ② pattern utente (se l'ha definito) — vince se è diverso dall'auto
        try:
            ts_pat, src_pat = parse_filename_pattern(video_path, self.fn_pattern.get())
            if ts_pat is not None:
                out.append({'key':'fn_pattern','source': f'filename user pattern',
                            'ts': float(ts_pat), 'tc': None, 'reliability': 'med',
                            'pretty': datetime.fromtimestamp(ts_pat,
                                        tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')})
        except Exception:
            pass
        # ③ entry "filename grezzo" sempre presente (per dare un punto in cui
        #    cliccare anche quando nessuna detection ha funzionato; selezionandolo
        #    si apre un dialogo per impostare il pattern)
        if not any(e['key'] in ('fn_auto','fn_pattern') for e in out):
            base_no_ext = os.path.splitext(os.path.basename(video_path))[0]
            out.append({'key':'fn_manual',
                        'source': 'filename (no timestamp recognised — click to set pattern)',
                        'ts': None, 'tc': None, 'reliability': 'low',
                        'pretty': base_no_ext})

        # Niente dedup: ogni sorgente è informativa anche se il valore coincide
        # (es. file_creation_date di pymediainfo coincide spesso col mtime).
        # Dedup leggero solo per chiavi identiche (stessa sorgente registrata 2x)
        seen_keys = set(); uniq = []
        for e in out:
            if e['key'] in seen_keys: continue
            seen_keys.add(e['key']); uniq.append(e)
        # Ordina: prima entry HIGH con data piena, poi HIGH con TC,
        # poi MED, poi LOW. All'interno di ogni gruppo, mantiene ordine stabile.
        rel_order = {'high':0,'med':1,'low':2}
        uniq.sort(key=lambda e: (rel_order.get(e['reliability'],3),
                                  0 if e['ts'] is not None else 1))
        return uniq

    def _refresh_ts_picker(self):
        """Ridisegna i radio button con tutti i timestamp del video corrente."""
        if not hasattr(self,'ts_picker_frame'): return
        for w in self.ts_picker_frame.winfo_children(): w.destroy()
        path = self.video_path.get()
        if not path:
            self._lbl(self.ts_picker_frame,
                "Carica un video per vedere i timestamp disponibili.",
                color=self.C['gray'], size=9).pack(anchor='w')
            return
        ts_list = self._gather_all_video_timestamps(path)
        if not ts_list:
            self._lbl(self.ts_picker_frame,
                "Nessun timestamp trovato.",
                color=self.C['yellow'], size=9).pack(anchor='w')
            return
        self._ts_list_cached = ts_list
        # Default: il primo (high reliability + ts non None)
        if not self.video_ts_choice.get() or self.video_ts_choice.get() not in [e['key'] for e in ts_list]:
            self.video_ts_choice.set(ts_list[0]['key'])
        for e in ts_list:
            color = (self.C['green'] if e['reliability']=='high'
                     else self.C['yellow'] if e['reliability']=='med'
                     else self.C['red'])
            txt = f"{e['source']}  →  {e['pretty']}"
            rb = tk.Radiobutton(self.ts_picker_frame, text=txt,
                                variable=self.video_ts_choice, value=e['key'],
                                bg=self.C['bg'], fg=color, selectcolor=self.C['entry'],
                                activebackground=self.C['bg'], activeforeground=color,
                                font=('Segoe UI', 9), anchor='w')
            rb.pack(anchor='w', padx=4, pady=1, fill='x')

    def _apply_selected_video_ts(self):
        """Applica al campo video_ts_corrected il timestamp scelto coi radio."""
        if not hasattr(self,'_ts_list_cached'):
            messagebox.showwarning("Timestamp",
                "Carica un video e premi 'Detect timestamp' prima."); return
        key = self.video_ts_choice.get()
        entry = next((e for e in self._ts_list_cached if e['key']==key), None)
        if entry is None:
            messagebox.showwarning("Timestamp","Selezione non valida."); return
        # Caso speciale: filename senza timestamp riconosciuto → chiedi pattern
        if key == 'fn_manual':
            base = os.path.splitext(os.path.basename(self.video_path.get()))[0]
            ans = simpledialog.askstring("Filename pattern",
                f"Nessun timestamp riconosciuto in:\n  {base}\n\n"
                "Inserisci un pattern usando i segnaposti YYYY MM DD HH MM SS\n"
                "(es. YYYYMMDD-HHMMSS-* oppure *_YYYYMMDD_HHMMSS*).\n"
                "Il pattern verrà salvato e ri-applicato.",
                initialvalue=self.fn_pattern.get())
            if not ans: return
            self.fn_pattern.set(ans)
            ts_pat, src_pat = parse_filename_pattern(self.video_path.get(), ans)
            if ts_pat is None:
                messagebox.showerror("Filename pattern",
                    f"Pattern '{ans}' non corrisponde al nome file.\n"
                    f"Riprova oppure usa una sorgente diversa dal picker.")
                return
            ts_str = datetime.fromtimestamp(ts_pat,tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            self._video_meta_unix = ts_pat
            self.video_ts_corrected.set(ts_str)
            self.lbl_video_meta_ts.config(text=ts_str, fg=self.C['yellow'])
            self.lbl_video_meta_src.config(text=f"✓ filename (pattern: {ans})",
                                           fg=self.C['yellow'])
            if hasattr(self,'lbl_video_ts_sync'):
                self.lbl_video_ts_sync.config(text=ts_str)
                self.lbl_video_src_sync.config(text=f"(filename pattern)")
            self._log('ok',f"⏱ Video start = {ts_str}  (filename pattern: {ans})")
            try: self._refresh_video_pos_time(self.video_pos_var.get())
            except Exception: pass
            try: self._build_alignment_table()
            except Exception: pass
            try: self._detect_video_ts()  # ricostruisce il picker col nuovo pattern
            except Exception: pass
            return
        if entry['ts'] is not None:
            ts = entry['ts']
            self._video_meta_unix = ts
            ts_str = datetime.fromtimestamp(ts,tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            self.video_ts_corrected.set(ts_str)
            self.lbl_video_meta_ts.config(text=ts_str, fg=self.C['green'])
            self.lbl_video_meta_src.config(text=f"✓ {entry['source']}", fg=self.C['green'])
            if hasattr(self,'lbl_video_ts_sync'):
                self.lbl_video_ts_sync.config(text=ts_str)
                self.lbl_video_src_sync.config(text=f"({entry['source']})")
            self._log('ok',f"⏱ Video start = {ts_str}  ({entry['source']})")
        elif entry['tc'] is not None:
            h,m,s = entry['tc']
            tc_str = f"{h:02d}:{m:02d}:{s:02d}"
            if self.usbl_df is not None and len(self.usbl_df):
                d = datetime.fromtimestamp(self.usbl_df['unix_ts'].iloc[0],
                                           tz=timezone.utc).date()
                dt = datetime(d.year,d.month,d.day,h,m,s,tzinfo=timezone.utc)
                ts_str = dt.strftime('%Y-%m-%dT%H:%M:%S')
                self._video_meta_unix = dt.timestamp()
                self.video_ts_corrected.set(ts_str)
                self.lbl_video_meta_ts.config(text=ts_str, fg=self.C['green'])
                self.lbl_video_meta_src.config(text=f"✓ {entry['source']} (date from USBL)",
                                               fg=self.C['green'])
                if hasattr(self,'lbl_video_ts_sync'):
                    self.lbl_video_ts_sync.config(text=ts_str)
                    self.lbl_video_src_sync.config(text=f"({entry['source']} + USBL date)")
                self._log('ok',f"⏱ Video start = {ts_str}  ({entry['source']} + USBL date)")
            else:
                # Chiedi una data all'utente
                ans = simpledialog.askstring("Date",
                    f"Il timecode è {tc_str} ma manca la data.\n"
                    "Inserisci la data UTC della dive (YYYY-MM-DD):")
                if not ans: return
                try:
                    yy,mo,dd = ans.split('-')
                    dt = datetime(int(yy),int(mo),int(dd),h,m,s,tzinfo=timezone.utc)
                    ts_str = dt.strftime('%Y-%m-%dT%H:%M:%S')
                    self._video_meta_unix = dt.timestamp()
                    self.video_ts_corrected.set(ts_str)
                    self.lbl_video_meta_ts.config(text=ts_str, fg=self.C['green'])
                    self.lbl_video_meta_src.config(text=f"✓ {entry['source']} (manual date)",
                                                   fg=self.C['green'])
                    if hasattr(self,'lbl_video_ts_sync'):
                        self.lbl_video_ts_sync.config(text=ts_str)
                        self.lbl_video_src_sync.config(text=f"({entry['source']} + manual date)")
                except Exception as e:
                    messagebox.showerror("Date",f"Data non valida: {e}")
                    return
        # Aggiorna le entry tempo nella scheda Sync
        try: self._refresh_video_pos_time(self.video_pos_var.get())
        except Exception: pass
        try: self._build_alignment_table()
        except Exception: pass

    # ── Browse / Load ─────────────────────────────────────────────────────────
    def _browse_video(self):
        p=filedialog.askopenfilename(
            filetypes=[("Video","*.mp4 *.mov *.avi *.mkv *.mts *.m2ts *.mpg"),("Tutti","*.*")])
        if not p: return
        self.video_path.set(p)
        cap=cv2.VideoCapture(p)
        fps=cap.get(cv2.CAP_PROP_FPS); tot=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        dur=tot/fps if fps else 0; w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)); cap.release()
        self._video_fps=fps; self._video_duration=dur
        self.video_slider.config(to=max(dur,1))
        self.extract_to.set(0.0)
        self.video_info.config(
            text=f"{fps:.2f} fps  |  {w}×{h}  |  {int(dur//3600)}h {int((dur%3600)//60)}m {dur%60:.0f}s")
        self._detect_video_ts()

    def _detect_video_ts(self):
        """Rileva i timestamp del video usando la stessa lista del picker.
        Sceglie automaticamente il primo entry HIGH affidabile, preferendo
        date complete (sidecar/pymediainfo encoded_date), poi TC + data USBL,
        poi pattern del nome file, infine mtime (in rosso, non affidabile)."""
        if not self.video_path.get(): return
        ts_list = self._gather_all_video_timestamps(self.video_path.get())
        self._ts_list_cached = ts_list

        # Aggiorna il picker (radio buttons)
        try: self._refresh_ts_picker()
        except Exception as e: self._log('warn', f'TS picker: {e}')

        if not ts_list:
            self.lbl_video_meta_ts.config(text='—', fg=self.C['red'])
            self.lbl_video_meta_src.config(text="impossibile leggere", fg=self.C['red'])
            return

        # Strategia di selezione automatica (in ordine di preferenza):
        #   1) HIGH + ts non None  → data piena affidabile (sidecar / pymediainfo encoded_date / CLI)
        #   2) HIGH + tc           → timecode QuickTime; combinato con data USBL se disponibile
        #   3) MED                 → pattern nome file, parser binario
        #   4) LOW                 → fallback FS (mtime/ctime/atime/file_creation_date)
        def pick(level, with_ts=None):
            for e in ts_list:
                if e['reliability'] != level: continue
                if with_ts is True and e['ts'] is None: continue
                if with_ts is False and e['ts'] is not None: continue
                return e
            return None

        chosen = pick('high', with_ts=True) or pick('high', with_ts=False) \
                 or pick('med', with_ts=True) or pick('med', with_ts=False) \
                 or pick('low', with_ts=True) or pick('low', with_ts=False) \
                 or ts_list[0]

        # Aggiorna selezione del radio button con quello scelto
        self.video_ts_choice.set(chosen['key'])
        self._refresh_ts_picker()

        # Determina il timestamp finale + colore badge
        if chosen['ts'] is not None:
            ts = chosen['ts']
            self._video_meta_unix = ts
            ts_str = datetime.fromtimestamp(ts,tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            col = (self.C['green'] if chosen['reliability']=='high'
                   else self.C['yellow'] if chosen['reliability']=='med'
                   else self.C['red'])
            self.lbl_video_meta_ts.config(text=ts_str, fg=col)
            self.lbl_video_meta_src.config(text=f"✓ {chosen['source']}", fg=col)
            if hasattr(self,'lbl_video_ts_sync'):
                self.lbl_video_ts_sync.config(text=ts_str)
                self.lbl_video_src_sync.config(text=f"({chosen['source']})")
            if not self.video_ts_corrected.get():
                self.video_ts_corrected.set(ts_str)
        elif chosen['tc'] is not None:
            h,m,s = chosen['tc']
            tc_str = f"{h:02d}:{m:02d}:{s:02d}"
            if self.usbl_df is not None and len(self.usbl_df):
                d = datetime.fromtimestamp(self.usbl_df['unix_ts'].iloc[0],
                                           tz=timezone.utc).date()
                dt = datetime(d.year,d.month,d.day,h,m,s,tzinfo=timezone.utc)
                ts_str = dt.strftime('%Y-%m-%dT%H:%M:%S')
                self._video_meta_unix = dt.timestamp()
                self.lbl_video_meta_ts.config(text=ts_str, fg=self.C['green'])
                self.lbl_video_meta_src.config(text=f"✓ {chosen['source']} (date from USBL)",
                                               fg=self.C['green'])
                if hasattr(self,'lbl_video_ts_sync'):
                    self.lbl_video_ts_sync.config(text=ts_str)
                    self.lbl_video_src_sync.config(text=f"({chosen['source']} + USBL date)")
                if not self.video_ts_corrected.get():
                    self.video_ts_corrected.set(ts_str)
            else:
                self.lbl_video_meta_ts.config(text=f"TC {tc_str} (data mancante)",
                                              fg=self.C['yellow'])
                self.lbl_video_meta_src.config(text=f"⚠ {chosen['source']}",
                                               fg=self.C['yellow'])
                if not self.video_ts_corrected.get():
                    self.video_ts_corrected.set(f"YYYY-MM-DDT{tc_str}")

        # Aggiorna l'entry "Time UTC" della scheda Sync con la nuova base
        try: self._refresh_video_pos_time(self.video_pos_var.get())
        except Exception: pass

    def _browse_usbl(self):
        p=filedialog.askopenfilename(filetypes=[("Testo","*.txt *.csv *.asc *.dat *.pos"),("Tutti","*.*")])
        if p: self.usbl_path.set(p)

    def _browse_ctd(self):
        p=filedialog.askopenfilename(filetypes=[("Testo","*.cnv *.csv *.txt *.dat"),("Tutti","*.*")])
        if p: self.ctd_path.set(p)

    def _browse_output(self):
        p=filedialog.askdirectory()
        if p: self.output_dir.set(p)

    def _load_usbl_preview(self):
        sep=self.usbl_sep.get()
        if sep=='Auto': sep=None
        try:
            header=0 if self.usbl_header.get() else None
            # Preview: leggi 50 righe per popolare la treeview, poi scansiona le
            # prime 200 righe del file completo per identificare quelle "popolate".
            df_preview=pd.read_csv(self.usbl_path.get(),sep=sep,header=header,
                                   engine='python',on_bad_lines='skip',nrows=50)
            if not self.usbl_header.get(): df_preview.columns=[f"col_{i}" for i in range(len(df_preview.columns))]
            else: df_preview.columns=[str(c).strip() for c in df_preview.columns]
            self.usbl_cols=list(df_preview.columns)
            self._populate_treeview(self.usbl_preview,df_preview)
            # Summary delle righe popolate sulle prime 200 righe del file completo
            try:
                df_scan=pd.read_csv(self.usbl_path.get(),sep=sep,header=header,
                                    engine='python',on_bad_lines='skip',nrows=200)
                if not self.usbl_header.get(): df_scan.columns=[f"col_{i}" for i in range(len(df_scan.columns))]
                else: df_scan.columns=[str(c).strip() for c in df_scan.columns]
                summary=self._populated_rows_summary(df_scan)
            except Exception: summary=""
            if hasattr(self,'usbl_populated_lbl') and summary:
                col=self.C['green'] if summary.startswith('✓') else self.C['yellow']
                self.usbl_populated_lbl.config(text=summary, fg=col)
            self.usbl_info.config(text=_L('usbl_loaded',self.lang,n=len(df_preview),cols=', '.join(self.usbl_cols)),fg=self.C['green'])
            df=df_preview  # alias per non rompere il resto della funzione
            for combo in self._usbl_combos:
                try: combo['values']=self.usbl_cols
                except Exception: pass
            self._refresh_exclude_ui()
            full=pd.read_csv(self.usbl_path.get(),sep=sep,header=header,engine='python',on_bad_lines='skip')
            if not self.usbl_header.get(): full.columns=[f"col_{i}" for i in range(len(full.columns))]
            else: full.columns=[str(c).strip() for c in full.columns]
            self._raw_usbl_df=full
            for col in self.usbl_cols:
                try:
                    sample=full[col].dropna().iloc[0]; fmt=detect_coord_format(sample)
                    if fmt in ['NMEA','UTM','DM','DMS']:
                        self.coord_fmt.set(fmt); self._coord_fmt_changed(); break
                except Exception: pass
        except Exception as e:
            self.usbl_info.config(text=f"Errore: {e}",fg=self.C['red'])

    def _load_ctd_preview(self):
        sep=self.ctd_sep.get()
        if sep=='Auto': sep=None
        try:
            header=0 if self.ctd_header.get() else None
            # Preview di 50 righe scrollabili
            df=pd.read_csv(self.ctd_path.get(),sep=sep,header=header,engine='python',
                           on_bad_lines='skip',nrows=50,comment='#')
            if not self.ctd_header.get(): df.columns=[f"col_{i}" for i in range(len(df.columns))]
            else: df.columns=[str(c).strip() for c in df.columns]
            self.ctd_cols=list(df.columns)
            self._populate_treeview(self.ctd_preview,df)
            # Summary delle righe popolate sulle prime 200 righe
            try:
                df_scan=pd.read_csv(self.ctd_path.get(),sep=sep,header=header,
                                    engine='python',on_bad_lines='skip',nrows=200,comment='#')
                if not self.ctd_header.get(): df_scan.columns=[f"col_{i}" for i in range(len(df_scan.columns))]
                else: df_scan.columns=[str(c).strip() for c in df_scan.columns]
                summary=self._populated_rows_summary(df_scan)
            except Exception: summary=""
            if hasattr(self,'ctd_populated_lbl') and summary:
                col=self.C['green'] if summary.startswith('✓') else self.C['yellow']
                self.ctd_populated_lbl.config(text=summary, fg=col)
            self._refresh_ctd_col_ui()
            for combo in self._ctd_combos:
                try: combo['values']=self.ctd_cols
                except Exception: pass
            self.ctd_info.config(text=f"✓ {len(df)} righe anteprima  |  Colonne: {', '.join(self.ctd_cols)}",fg=self.C['green'])
            full=pd.read_csv(self.ctd_path.get(),sep=sep,header=header,engine='python',on_bad_lines='skip',comment='#')
            if not self.ctd_header.get(): full.columns=[f"col_{i}" for i in range(len(full.columns))]
            else: full.columns=[str(c).strip() for c in full.columns]
            self.ctd_df=full
            for col in self.ctd_cols:
                try:
                    sample=str(full[col].dropna().iloc[0])
                    pd.to_datetime(sample,utc=True)
                    self.ctd_ts_col_uni.set(col); self.ctd_ts_mode.set('unified'); break
                except Exception: pass
        except Exception as e:
            self.ctd_info.config(text=f"Errore CTD: {e}",fg=self.C['red'])

    def _populate_treeview(self,tv,df):
        tv.delete(*tv.get_children()); tv['columns']=list(df.columns); tv['show']='headings'
        for col in df.columns:
            tv.heading(col,text=col); tv.column(col,width=max(70,len(str(col))*9))
        # Mostra l'indice di riga come prima colonna virtuale (tag)
        for ridx,row in df.iterrows():
            tv.insert('','end',values=list(row))

    def _populated_rows_summary(self, df, max_scan=200, threshold=0.5):
        """Scansiona le prime max_scan righe e ritorna una stringa che indica
        gli indici delle prime righe 'popolate' (>= threshold di campi non-NaN/'').
        Usata per aiutare l'utente a capire dove iniziano i dati validi quando
        il file ha molte righe iniziali vuote."""
        try:
            sub = df.head(max_scan)
            if len(sub) == 0: return ""
            # Frazione di campi non-vuoti per riga
            def frac_nonempty(row):
                vals = [v for v in row.values
                        if pd.notna(v) and str(v).strip() not in ('','nan','NaN')]
                return len(vals) / max(1, len(row))
            fracs = sub.apply(frac_nonempty, axis=1)
            populated_idx = list(sub.index[fracs >= threshold])
            if not populated_idx:
                return (f"⚠ Nelle prime {len(sub)} righe nessuna sembra popolata "
                        f"(soglia {int(threshold*100)}% colonne non vuote). "
                        "Scrolla nella preview per ispezionare manualmente.")
            first_few = populated_idx[:6]
            extra = "" if len(populated_idx) <= 6 else f" … (+{len(populated_idx)-6})"
            if first_few[0] == 0:
                return f"✓ Dati popolati a partire dalla riga 0  (prime righe popolate: {first_few}{extra})."
            else:
                return (f"⚠ Prime {first_few[0]} righe poco/non popolate. "
                        f"Prime righe popolate: {first_few}{extra}. "
                        "Scrolla la preview per vedere i dati buoni.")
        except Exception as e:
            return f"(impossibile calcolare summary: {e})"

    # ── Validate ──────────────────────────────────────────────────────────────
    def _validate_usbl(self):
        L=self.lang
        if not self.usbl_path.get():
            self.coord_preview.config(text="❌ Carica prima il file USBL.",fg=self.C['red']); return
        if not self.lat_col.get() or not self.lon_col.get():
            self.coord_preview.config(text="❌ Seleziona le colonne Lat e Lon.",fg=self.C['red']); return
        if self._raw_usbl_df is not None:
            try:
                s_lat=float(str(self._raw_usbl_df[self.lat_col.get()].iloc[0]).replace('N','').replace('S','').replace(',','.').strip())
                s_lon=float(str(self._raw_usbl_df[self.lon_col.get()].iloc[0]).replace('E','').replace('W','').replace(',','.').strip())
                if self.coord_fmt.get()=='DD':
                    if abs(s_lat)>18000 or abs(s_lon)>18000:
                        self.coord_preview.config(text=f"⚠ ({s_lat:.1f},{s_lon:.1f}): potrebbero essere UTM.",fg=self.C['yellow']); return
                    if abs(s_lat)>180 or abs(s_lon)>180:
                        self.coord_preview.config(text=f"⚠ ({s_lat:.2f},{s_lon:.2f}): formato NMEA?",fg=self.C['yellow']); return
            except Exception: pass
        try:
            sep=self.usbl_sep.get()
            df=load_usbl(self.usbl_path.get(),sep=sep if sep!='Auto' else None,
                         has_header=self.usbl_header.get(),ts_params=self._build_ts_params(),
                         lat_col=self.lat_col.get(),lon_col=self.lon_col.get(),
                         coord_fmt=self.coord_fmt.get(),depth_col=self.depth_col.get(),
                         extra_cols=[],
                         utm_zone=self.utm_zone.get() if self.coord_fmt.get()=='UTM' else None,
                         utm_north=self.utm_north.get())
            if len(df)==0:
                self.coord_preview.config(text="❌ Nessuna riga valida.",fg=self.C['red']); return
            self.usbl_df=df
            # Trova la prima riga "valida" (lat/lon parseabili, range plausibile)
            valid_mask = (df['lat_dd'].between(-90,90)) & (df['lon_dd'].between(-180,180))
            n_valid = int(valid_mask.sum())
            if n_valid == 0:
                # Nessuna riga valida → errore esplicito
                r0 = df.iloc[0]
                lat0 = r0.get('lat_dd', np.nan); lon0 = r0.get('lon_dd', np.nan)
                if np.isnan(lat0) or np.isnan(lon0):
                    self.coord_preview.config(
                        text="❌ Tutte le righe hanno lat/lon vuoti o non parseabili. "
                             "Controlla mapping colonne e formato.",
                        fg=self.C['red'])
                else:
                    self.coord_preview.config(
                        text=f"⚠ Coordinate fuori range: ({lat0:.2f},{lon0:.2f}). "
                             "Controlla il formato (NMEA/DD/DM/DMS/UTM).",
                        fg=self.C['yellow'])
                return
            # Prima riga valida (anche se non è la prima del file)
            first_idx = int(np.argmax(valid_mask.values))
            r = df.iloc[first_idx]
            d = r['depth'] if not np.isnan(r['depth']) else 0.0
            skipped_msg = ""
            if first_idx > 0:
                skipped_msg = f"  (skipped {first_idx} leading invalid rows)"
            n_invalid = len(df) - n_valid
            extra_msg = f"  [{n_invalid} invalid rows mixed in]" if n_invalid > 0 else ""
            self.coord_preview.config(
                text=_L('usbl_ok',L,lat=r['lat_dd'],lon=r['lon_dd'],depth=d,n=len(df))
                     + skipped_msg + extra_msg,
                fg=self.C['green'])
            self._build_alignment_table()
            self._draw_usbl_depth_plot()
            self._draw_depth_overlay()
        except Exception as e:
            self.coord_preview.config(text=f"❌ {e}",fg=self.C['red'])

    def _validate_ctd(self):
        if not self.ctd_path.get():
            self.ctd_preview_result.config(text="❌ Carica prima il file CTD.",fg=self.C['red']); return
        try:
            ctd_param_cols=[col for col,var in self.ctd_selected if var.get()]
            sep=self.ctd_sep.get()
            df=load_ctd(self.ctd_path.get(),sep=sep if sep!='Auto' else None,
                        has_header=self.ctd_header.get(),
                        ts_params=self._build_ctd_ts_params(),depth_col=self.ctd_depth_col.get(),
                        param_cols=ctd_param_cols,sync_mode=self.ctd_sync_mode.get(),
                        ctd_ts_offset=self.ctd_ts_offset.get())
            if len(df)==0:
                self.ctd_preview_result.config(text="❌ Nessuna riga valida.",fg=self.C['red']); return
            # Trova la prima riga "valida" per il sample
            dc = self.ctd_depth_col.get()
            if self.ctd_sync_mode.get()=='time' and 'unix_ts' in df.columns:
                # Riga valida = unix_ts non NaN; preferisco anche depth non NaN
                ts_ok = df['unix_ts'].notna()
                depth_ok = df[dc].apply(lambda x: pd.notna(pd.to_numeric(x, errors='coerce'))) \
                           if dc and dc in df.columns else pd.Series([True]*len(df))
                full_ok = ts_ok & depth_ok
                if int(full_ok.sum()) > 0:
                    first_idx = int(np.argmax(full_ok.values))
                elif int(ts_ok.sum()) > 0:
                    first_idx = int(np.argmax(ts_ok.values))
                else:
                    self.ctd_preview_result.config(
                        text="❌ Nessun timestamp parsato in nessuna riga della CTD. "
                             "Verifica colonne e formato.",
                        fg=self.C['red']); return
            else:
                first_idx = 0
                if '_depth_key' in df.columns and df['_depth_key'].notna().any():
                    first_idx = int(np.argmax(df['_depth_key'].notna().values))
            r = df.iloc[first_idx]
            skipped_msg = f"  (skipped {first_idx} leading invalid rows)" if first_idx > 0 else ""
            if self.ctd_sync_mode.get()=='time' and 'unix_ts' in df.columns:
                dt_str=datetime.fromtimestamp(r['unix_ts'],tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
                depth_str=''
                if dc and dc in df.columns:
                    try: depth_str=f"  |  Depth: {float(r.get(dc,np.nan)):.1f} m"
                    except: pass
                params=[]
                for col in ctd_param_cols[:4]:
                    if col in df.columns:
                        try: params.append(f"{col}: {r[col]:.3f}")
                        except: params.append(f"{col}: {r[col]}")
                p_str=("  |  "+"  ".join(params)) if params else ''
                self.ctd_preview_result.config(text=f"✅ OK → {dt_str}{depth_str}{p_str}  |  {len(df)} righe{skipped_msg}",fg=self.C['green'])
            else:
                if '_depth_key' in df.columns:
                    self.ctd_preview_result.config(
                        text=f"✅ OK → Depth {df['_depth_key'].min():.1f}–{df['_depth_key'].max():.1f} m  |  {len(df)} righe",fg=self.C['green'])
                else:
                    self.ctd_preview_result.config(text=f"✅ OK → {len(df)} righe",fg=self.C['green'])
            self.ctd_df_validated=df
            # Auto-select all per default
            self.ctd_depth_window_idx=(0,len(df)-1)
            self.ctd_window_lbl.config(text=f"Finestra: tutto ({len(df)} righe)",fg=self.C['gray'])
            self._build_alignment_table()
            self._draw_ctd_depth_plot()
            self._draw_depth_overlay()
        except Exception as e:
            self.ctd_preview_result.config(text=f"❌ {e}",fg=self.C['red'])

    def _build_ts_params(self):
        return dict(mode=self.ts_mode.get(),col_date=self.ts_col_date.get(),
                    col_time=self.ts_col_time.get(),fmt_date=self.ts_fmt_date.get(),
                    fmt_time=self.ts_fmt_time.get(),col_unified=self.ts_col_uni.get(),
                    fmt_unified=self.ts_fmt_uni.get() or None)

    def _build_ctd_ts_params(self):
        return dict(mode=self.ctd_ts_mode.get(),col_date=self.ctd_ts_col_date.get(),
                    col_time=self.ctd_ts_col_time.get(),fmt_date=self.ctd_ts_fmt_date.get(),
                    fmt_time=self.ctd_ts_fmt_time.get(),col_unified=self.ctd_ts_col_uni.get(),
                    fmt_unified=self.ctd_ts_fmt_uni.get() or None)

    # ── Profili ───────────────────────────────────────────────────────────────
    def _save_profile(self):
        path=self.profile_path.get() or filedialog.asksaveasfilename(
            defaultextension='.json',filetypes=[("JSON","*.json")])
        if not path: return
        keys_str=['video_path','usbl_path','ctd_path','output_dir','dive_name',
                  'usbl_sep','ctd_sep','fn_pattern',
                  'ts_mode','ts_col_uni','ts_fmt_uni','ts_col_date','ts_fmt_date','ts_col_time','ts_fmt_time',
                  'coord_fmt','lat_col','lon_col','depth_col','utm_zone','img_fmt',
                  'ovl_pos','ovl_color','ovl_bg','ctd_ts_mode','ctd_ts_col_uni','ctd_ts_fmt_uni',
                  'ctd_ts_col_date','ctd_ts_fmt_date','ctd_ts_col_time','ctd_ts_fmt_time',
                  'video_ts_corrected','ctd_depth_col','ctd_sync_mode']
        keys_bool=['usbl_header','ctd_header','utm_north','ovl_enabled','ovl_time',
                   'ovl_depth','ovl_latlon','ovl_dive','use_cuda']
        keys_num=['video_delay','interval_sec','assoc_window','ctd_ts_offset',
                  'blur_thresh','dark_thresh','bright_thresh','ovl_fontsize','img_quality',
                  'extract_from','extract_to']
        pr={}
        for k in keys_str+keys_bool+keys_num:
            try: pr[k]=getattr(self,k).get()
            except: pass
        pr['custom_cols']=[(n.get(),v.get()) for _,n,v in self.custom_col_rows if n.get()]
        pr['excluded_usbl']=list(self.excluded_usbl)
        with open(path,'w') as f: json.dump(pr,f,indent=2)
        self.profile_path.set(path)
        self._log('ok',_L('log_profile_saved',self.lang,path=path))

    def _load_profile(self):
        path=filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if not path: return
        with open(path) as f: pr=json.load(f)
        for k,v in pr.items():
            if k in ('custom_cols','excluded_usbl'): continue
            try: getattr(self,k).set(v)
            except: pass
        for f,_,_ in self.custom_col_rows: f.destroy()
        self.custom_col_rows.clear()
        for n,v in pr.get('custom_cols',[]): self._add_custom_col(n,v)
        self.excluded_usbl=set(pr.get('excluded_usbl',[]))
        self.profile_path.set(path)
        self._log('ok',_L('log_profile_loaded',self.lang,path=path))

    # ── Extraction ────────────────────────────────────────────────────────────
    def _start_extraction(self):
        L=self.lang
        if not self.video_path.get():
            messagebox.showerror(_L('error_title',L),_L('err_no_video',L)); return
        if not self.output_dir.get():
            messagebox.showerror(_L('error_title',L),_L('err_no_output',L)); return

        # USBL è opzionale per estrazione semplice
        if self.usbl_path.get() and self.usbl_df is None:
            messagebox.showerror(_L('error_title',L),_L('err_validate_first',L)); return
        try:
            extra=[]
            if self.usbl_df is not None:
                extra=[c for c in self.usbl_cols
                       if c not in [self.lat_col.get(),self.lon_col.get(),self.depth_col.get()]
                       and c not in self.excluded_usbl]
                sep=self.usbl_sep.get()
                self.usbl_df=load_usbl(self.usbl_path.get(),
                                       sep=sep if sep!='Auto' else None,
                                       has_header=self.usbl_header.get(),ts_params=self._build_ts_params(),
                                       lat_col=self.lat_col.get(),lon_col=self.lon_col.get(),
                                       coord_fmt=self.coord_fmt.get(),depth_col=self.depth_col.get(),
                                       extra_cols=extra,
                                       utm_zone=self.utm_zone.get() if self.coord_fmt.get()=='UTM' else None,
                                       utm_north=self.utm_north.get(),
                                       excluded_cols=list(self.excluded_usbl))
                self.usbl_extra=extra
        except Exception as e:
            messagebox.showerror(_L('error_title',L),str(e)); return

        video_ts_offset=self._get_video_ts_offset()
        ctd_df_out=None; ctd_param_cols=[]
        if self.ctd_path.get() and self.ctd_df is not None:
            try:
                ctd_param_cols=[col for col,var in self.ctd_selected if var.get()]
                # Usa il df validato (che ha gli shift già consolidati tramite
                # ✅ Apply). Se non è validato, ricaricalo SENZA offset (l'offset
                # è gestito dopo come shift live).
                if self.ctd_df_validated is not None:
                    ctd_df_out=self.ctd_df_validated.copy()
                else:
                    ctd_df_out=load_ctd(
                        self.ctd_path.get(),sep=None,has_header=self.ctd_header.get(),
                        ts_params=self._build_ctd_ts_params(),depth_col=self.ctd_depth_col.get(),
                        param_cols=ctd_param_cols,sync_mode=self.ctd_sync_mode.get(),
                        ctd_ts_offset=0.0)
                # Applica il shift LIVE corrente (ctd_ts_offset) anche se l'utente
                # non ha premuto ✅ Apply: così l'estrazione usa esattamente la
                # curva visibile nell'overlay.
                try: live_shift = float(self.ctd_ts_offset.get())
                except Exception: live_shift = 0.0
                if abs(live_shift) > 0.01 and 'unix_ts' in ctd_df_out.columns:
                    ctd_df_out['unix_ts'] = ctd_df_out['unix_ts'] + live_shift
                    self._log('info',
                        f"CTD shift live applicato in estrazione: {live_shift:+.2f}s")
            except Exception as e:
                self._log('warn',_L('log_ctd_warn',self.lang,e=e))

        # 🚧 Validazione depth CTD vs USBL: blocca estrazione se CTD presente e depth divergono
        if ctd_df_out is not None:
            # Ricostruisci la tabella per ottenere lo stato aggiornato
            try:
                self._build_alignment_table()
            except Exception:
                pass
            if not getattr(self, '_ctd_depth_ok', True):
                ans=messagebox.askyesno(
                    "CTD depth check",
                    f"La profondità CTD non corrisponde a quella USBL "
                    f"(soglia {self.ctd_depth_tol.get():.1f} m).\n\n"
                    "Possibili cause:\n"
                    " • CTD by_time → la sincronizzazione temporale è ancora sbagliata.\n"
                    "   Usa '🌊 Auto-fix from USBL depth' o riallinea il timestamp CTD.\n"
                    " • CTD by_depth → la finestra CTD selezionata in scheda 3 non è\n"
                    "   quella della discesa attuale.\n"
                    " • Stai usando una CTD di una dive diversa.\n\n"
                    "Vuoi proseguire comunque?  (Sconsigliato: i parametri CTD nei frame\n"
                    "potrebbero corrispondere ad altre profondità.)")
                if not ans:
                    self._log('err','❌ Estrazione annullata: depth CTD/USBL non allineate.')
                    return
                self._log('warn','⚠ Estrazione forzata nonostante la divergenza depth CTD/USBL.')

        custom={n.get():v.get() for _,n,v in self.custom_col_rows if n.get()}
        color_map={'white':(255,255,255),'yellow':(0,255,255),'cyan':(255,255,0),'black':(0,0,0)}
        overlay_cfg=dict(enabled=self.ovl_enabled.get(),show_time=self.ovl_time.get(),
                         show_depth=self.ovl_depth.get(),show_latlon=self.ovl_latlon.get(),
                         show_dive=self.ovl_dive.get(),position=self.ovl_pos.get(),
                         font_size=self.ovl_fontsize.get(),
                         color=color_map.get(self.ovl_color.get(),(255,255,255)),
                         bg_style=self.ovl_bg.get(),ctd_params=ctd_param_cols[:2])
        # Controllo qualità CTD: avvisa se ha NaN nel timestamp
        if ctd_df_out is not None and self.ctd_sync_mode.get()=='time':
            if 'unix_ts' in ctd_df_out.columns:
                nan_frac = ctd_df_out['unix_ts'].isna().mean()
                if nan_frac > 0.5:
                    ans = messagebox.askyesno(
                        "CTD Warning",
                        f"The CTD file has {nan_frac*100:.0f}% unparsed timestamps.\n"
                        f"This usually means the CTD date/time is wrong or the timestamp\n"
                        f"column was not correctly mapped.\n\n"
                        f"CTD data will be skipped for frames where lookup fails.\n\n"
                        f"Proceed anyway?")
                    if not ans:
                        return
                    # Filtra righe NaN per evitare crash
                    ctd_df_out = ctd_df_out.dropna(subset=['unix_ts']).reset_index(drop=True)
                    self._log('warn', f'CTD: removed {int(nan_frac*len(ctd_df_out))} rows with invalid timestamps')
                elif nan_frac > 0:
                    ctd_df_out = ctd_df_out.dropna(subset=['unix_ts']).reset_index(drop=True)
                    self._log('info', f'CTD: {int(nan_frac*100)}% rows with invalid timestamps removed automatically')

        self.stop_event.clear(); self.progress['value']=0
        threading.Thread(target=extract_frames,kwargs=dict(
            video_path=self.video_path.get(),output_dir=self.output_dir.get(),
            dive_name=self.dive_name.get(),video_ts_offset=video_ts_offset,
            extract_from=self.extract_from.get(),extract_to=self.extract_to.get(),
            usbl_df=self.usbl_df,usbl_extra_cols=self.usbl_extra if self.usbl_df is not None else [],
            excluded_usbl_cols=list(self.excluded_usbl),
            ctd_df=ctd_df_out,ctd_sync_mode=self.ctd_sync_mode.get(),
            ctd_param_cols=ctd_param_cols,
            # ctd_ts_offset=0.0 perché il shift live è già stato applicato a ctd_df_out
            ctd_ts_offset=0.0,
            ctd_depth_window=self.ctd_depth_window_idx,
            custom_cols=custom,interval_sec=self.interval_sec.get(),
            assoc_window=self.assoc_window.get(),img_fmt=self.img_fmt.get(),
            img_quality=self.img_quality.get(),overlay_cfg=overlay_cfg,
            blur_thresh=self.blur_thresh.get(),dark_thresh=self.dark_thresh.get(),
            bright_thresh=self.bright_thresh.get(),use_cuda=self.use_cuda.get(),
            lang=self.lang,progress_q=self.progress_q,log_q=self.log_q,
            stop_event=self.stop_event),daemon=True).start()
        self._poll_queues()

    def _toggle_pause(self): self._log('info',_L('pause_info',self.lang))
    def _stop_extraction(self): self.stop_event.set(); self._log('warn',_L('stop_requested',self.lang))

    def _poll_queues(self):
        try:
            while True:
                pct=self.progress_q.get_nowait()
                self.progress['value']=pct
                self.status_lbl.config(text=_L('progress_label',self.lang,pct=pct))
        except queue.Empty: pass
        try:
            while True:
                level,msg=self.log_q.get_nowait(); self._log(level,msg)
        except queue.Empty: pass
        if self.progress['value']<100 and not self.stop_event.is_set():
            self.after(200,self._poll_queues)

    def _log(self,level,msg):
        self.log_box.config(state='normal')
        self.log_box.insert('end',f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n",level)
        self.log_box.see('end'); self.log_box.config(state='disabled')

    def _update_hw_label(self):
        cuda=f"CUDA ✓ ({CUDA_COUNT} GPU)" if HAS_CUDA else "CPU only"
        self.hw_label.config(text=f"{cuda}  |  {os.cpu_count()} core  |  OpenCV {cv2.__version__}")


if __name__=='__main__':
    app=ROVSyncTool()
    app.mainloop()
