import io
import os
import csv
import time
import threading
from collections import deque, defaultdict
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from .. import storage, estimator
from .. import location as loc
from ..scanners import wifi_scanner
from ..device_table import DeviceTable

TEMPLATES_DIR = Path(__file__).parent / "templates"
app = Flask(__name__, template_folder=str(TEMPLATES_DIR))

_devices = DeviceTable()
_state = {
    "scanning": False,
    "interval": 20,
    "last_scan": None,
    "flock_active": [],
    "flock_count": 0,
    "log": deque(maxlen=200),
    "gps": None,
}
_seen_flock_bssids = set()
_samples = defaultdict(lambda: deque(maxlen=200))
_labels = {}
_lock = threading.Lock()

def _push_log(msg, source="PHONE"):
    ts = time.strftime("%H:%M:%S")
    _state["log"].appendleft({"t": ts, "msg": msg, "source": source})

def _ingest_hit(conn, label, confidence, bssid, ssid, rssi, cur_gps, source):
    bssid = (bssid or "").upper()
    storage.record_detection(conn, source, label, "flock", bssid, rssi, None, confidence, None)
    _labels[bssid] = (label, confidence, ssid or "<hidden>")
    _samples[bssid].append({
        "lat": cur_gps["lat"] if cur_gps else None,
        "lon": cur_gps["lon"] if cur_gps else None,
        "rssi": rssi,
        "ts": time.time()
    })
    if bssid not in _seen_flock_bssids:
        _seen_flock_bssids.add(bssid)
        _push_log(f"NEW {confidence} hit [{source}]: {bssid} ({ssid or 'hidden'}) rssi={rssi}")
    with _lock:
        _state["flock_count"] = len(_seen_flock_bssids)
    return {
        "label": label,
        "confidence": confidence,
        "bssid": bssid,
        "ssid": ssid or "<hidden>",
        "rssi": rssi,
        "is_flock": True
    }

def _scan_loop():
    conn, _ = storage.get_connection()
    while _state["scanning"]:
        try:
            fix = loc.get_fix_any(timeout=8)
            if fix:
                with _lock:
                    _state["gps"] = fix
            cur_gps = _state["gps"]
            hits = wifi_scanner.scan(force=True)
            active = []
            for label, confidence, bssid, ssid, rssi, is_flock in hits:
                if is_flock:
                    entry = _ingest_hit(conn, label, confidence, bssid, ssid, rssi, cur_gps, "WIFI")
                    active.append(entry)
            with _lock:
                _state["flock_active"] = active
                _state["last_scan"] = time.strftime("%H:%M:%S")
            all_nets = wifi_scanner.scan_all(force=True)
            for net in all_nets:
                _devices.ingest(
                    net["mac"], "wifi", rssi=net.get("rssi"),
                    ssid=net.get("ssid", ""), oui_flock=net.get("oui_flock", False),
                    gps=cur_gps, source="phone"
                )
        except Exception as e:
            _push_log(f"Scan error: {e}")
        time.sleep(_state["interval"])

@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/api/devices")
def api_devices():
    source = request.args.get("source")
    snap = _devices.snapshot(source=source)
    return jsonify({
        "all": snap["all"],
        "ble": snap["ble"],
        "flock": snap["flock"],
        "clusters": {},
    })

@app.route("/api/radar")
def api_radar():
    with _lock:
        gps = _state["gps"]
        active_bssids = {e["bssid"] for e in _state["flock_active"]}
    all_devs = _devices.view("all")
    devices_out = []
    for d in all_devs:
        bssid = d["mac"]
        kind = d["kind"]
        flock_conf = d.get("flock_conf")
        label = _labels.get(bssid, ("Unknown device", "?", ""))[0]
        confidence = flock_conf if flock_conf in ("H", "M") else "LOW"
        if confidence == "H":
            confidence = "HIGH"
        elif confidence == "M":
            confidence = "MEDIUM"
        rssi = d.get("rssi")
        samples = list(_samples.get(bssid, []))
        est = estimator.estimate_position(samples)
        distance_m = estimator.rssi_to_distance(rssi) if rssi is not None else None
        bearing = None
        est_distance_m = None
        if gps and est.get("method") == "weighted_centroid":
            e = est["estimate"]
            bearing = round(estimator.bearing(gps["lat"], gps["lon"], e["lat"], e["lon"]), 1)
            est_distance_m = round(estimator.haversine(gps["lat"], gps["lon"], e["lat"], e["lon"]), 1)
        elif distance_m is not None:
            est_distance_m = distance_m
        is_camera = d.get("is_camera", False)
        is_police = d.get("is_police", False)
        camera_type = d.get("camera_type", None)

        if kind == "ble":
            color = "blue"
        elif camera_type == "flock":
            color = "red"
        elif is_camera:
            color = "yellow"
        elif is_police:
            color = "red"
        else:
            color = "green"

        dev_out = {
            "bssid": bssid,
            "label": label,
            "confidence": confidence,
            "ssid": d.get("ssid", ""),
            "rssi": rssi,
            "kind": kind,
            "flock_conf": flock_conf,
            "color": color,
            "bearing": bearing,
            "distance_m": distance_m,
            "est_distance_m": est_distance_m,
            "in_range": bssid in active_bssids,
            "last_seen": d.get("last_seen"),
            "source": d.get("source"),
            "is_camera": is_camera,
            "is_police": is_police,
            "is_whitelisted": d.get("is_whitelisted", False),
            "is_moving": d.get("is_moving", False),
            "is_anomaly": d.get("is_anomaly", False),
            "is_router": d.get("is_router", False),
            "suspicious": d.get("suspicious", False),
            "indicators": d.get("indicators", {}),
        }
        devices_out.append(dev_out)
    return jsonify({"gps": gps, "scanning": _state["scanning"], "devices": devices_out})

@app.route("/api/state")
def api_state():
    with _lock:
        return jsonify({
            "scanning": _state["scanning"],
            "interval": _state["interval"],
            "last_scan": _state["last_scan"],
            "flock_active": _state["flock_active"],
            "flock_count": _state["flock_count"],
            "log": list(_state["log"])[:60],
            "gps": _state["gps"],
        })

@app.route("/api/export")
def api_export():
    source = request.args.get("source")
    snap = _devices.snapshot(source=source)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["MAC", "Kind", "RSSI", "Distance(ft)", "SSID", "Source", "Last Seen", "Suspicious", "Camera", "Police", "Router", "Moving", "Anomaly"])
    for d in snap["all"]:
        writer.writerow([
            d.get("mac", ""), d.get("kind", ""), d.get("rssi", ""),
            d.get("dist_ft", ""), d.get("ssid", ""), d.get("source", ""),
            d.get("last_seen", ""), d.get("suspicious", False),
            d.get("is_camera", False), d.get("is_police", False),
            d.get("is_router", False), d.get("is_moving", False),
            d.get("is_anomaly", False)
        ])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='millie_export.csv'
    )

DURESS_PIN = os.environ.get("MILLIE_DURESS_PIN", "1234")

@app.route("/api/duress", methods=["POST"])
def api_duress():
    data = request.get_json() or {}
    pin = data.get("pin", "")
    if pin == DURESS_PIN:
        import sqlite3
        db_path = storage.DB_PATH
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            conn.execute("DELETE FROM detections")
            conn.commit()
            conn.close()
        _devices.devices.clear()
        _seen_flock_bssids.clear()
        _samples.clear()
        _labels.clear()
        with _lock:
            _state["flock_count"] = 0
            _state["flock_active"] = []
        _push_log("⚠️ Duress PIN activated – data wiped")
        return jsonify({"status": "wiped"})
    else:
        return jsonify({"error": "invalid pin"}), 403

def serve(host="127.0.0.1", port=8770, autostart=True):
    if autostart:
        _state["scanning"] = True
        threading.Thread(target=_scan_loop, daemon=True).start()
        _push_log("Scanning loop started")
    app.run(host=host, port=port, threaded=True)
