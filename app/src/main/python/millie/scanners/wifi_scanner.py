import json
import subprocess
import time
from ..config.ouis import match_oui
from ..config.ssid_patterns import FLOCK_SSID_RE

MIN_POLL_INTERVAL_SECONDS = 30
_last_poll = 0.0

def _run_scaninfo():
    try:
        out = subprocess.run(["termux-wifi-scaninfo"], capture_output=True, text=True, timeout=15)
        return json.loads(out.stdout or "[]")
    except Exception:
        return []

def scan(force=False):
    global _last_poll
    now = time.time()
    if not force and now - _last_poll < MIN_POLL_INTERVAL_SECONDS:
        return []
    _last_poll = now
    detections = []
    for net in _run_scaninfo():
        ssid = (net.get("ssid") or "").strip()
        bssid = net.get("bssid") or ""
        rssi = net.get("rssi") or net.get("level")
        oui_match = match_oui(bssid)
        if not oui_match:
            continue
        label_oui, _, _ = oui_match
        ssid_is_flock = bool(ssid and FLOCK_SSID_RE.search(ssid))
        hidden = (ssid == "")
        if ssid_is_flock:
            detections.append(("FLOCK ALPR camera (OUI + Flock SSID)", "HIGH", bssid, ssid, rssi, True))
        elif hidden:
            detections.append(("Likely Flock camera (Flock OUI, hidden SSID)", "MEDIUM", bssid, ssid, rssi, True))
        else:
            detections.append((f"Possible target device ({label_oui}) — weak", "LOW", bssid, ssid, rssi, False))
    return detections

def scan_all(force=False):
    global _last_poll
    now = time.time()
    if not force and now - _last_poll < MIN_POLL_INTERVAL_SECONDS:
        return []
    networks = _run_scaninfo()
    out = []
    for net in networks:
        ssid = (net.get("ssid") or "").strip()
        bssid = net.get("bssid") or ""
        rssi = net.get("rssi") or net.get("level")
        if not bssid:
            continue
        oui_match = match_oui(bssid)
        out.append({"mac": bssid, "ssid": ssid, "rssi": rssi, "oui_flock": bool(oui_match)})
    return out
