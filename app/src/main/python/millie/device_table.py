import math
import threading
import time
from collections import deque
from .config.ouis import match_oui, get_camera_type, is_router_ssid

RANGE_BAND_FT = 3.0
MAX_RANGE_FT = 50.0
CONCURRENT_WINDOW_S = 15
MOVEMENT_HISTORY_LEN = 20
MOVEMENT_MIN_SAMPLES = 5
MOVEMENT_MIN_DELTA_FT = 2.0
MOVEMENT_SLOPE_THRESHOLD = 0.8
MOVEMENT_MAX_AGE_S = 30
STALE_SECONDS = 300
ANOMALY_RSSI_DROP = 20

TX_POWER_1M = -45.0
PATH_LOSS_N = 3.0
M_TO_FT = 3.28084

def rssi_to_feet(rssi):
    if rssi is None:
        return None
    try:
        meters = 10 ** ((TX_POWER_1M - float(rssi)) / (10 * PATH_LOSS_N))
    except Exception:
        return None
    meters = max(0.15, min(meters, 600))
    return round(meters * M_TO_FT, 1)

class DeviceTable:
    def __init__(self, stale_seconds=STALE_SECONDS):
        self.lock = threading.Lock()
        self.devices = {}
        self.stale_seconds = stale_seconds

    def _enrich_device(self, d):
        if d is None:
            return d
        hidden = d.get("hidden", False)
        is_camera = d.get("is_camera", False)
        is_police = d.get("is_police", False)
        is_whitelisted = d.get("is_whitelisted", False)
        camera_type = d.get("camera_type", None)
        is_router = d.get("is_router", False)

        moving = False
        history = d.get("movement_history", [])
        now = time.time()
        recent = [(ts, dist) for ts, dist in history if (now - ts) <= MOVEMENT_MAX_AGE_S]
        if len(recent) >= MOVEMENT_MIN_SAMPLES:
            t0 = recent[0][0]
            xs = [ts - t0 for ts, _ in recent]
            ys = [dist for _, dist in recent]
            n = len(xs)
            sum_x = sum(xs)
            sum_y = sum(ys)
            sum_xx = sum(x * x for x in xs)
            sum_xy = sum(x * y for x, y in zip(xs, ys))
            denom = n * sum_xx - sum_x * sum_x
            if denom != 0:
                slope = (n * sum_xy - sum_x * sum_y) / denom
                total_delta = ys[-1] - ys[0]
                if abs(total_delta) >= MOVEMENT_MIN_DELTA_FT and abs(slope) >= MOVEMENT_SLOPE_THRESHOLD:
                    moving = True

        anomaly = False
        rssi_history = d.get("rssi_history", deque(maxlen=10))
        if len(rssi_history) >= 3:
            last_rssi = rssi_history[-1]
            prev_rssi = rssi_history[-2]
            if (prev_rssi - last_rssi) >= ANOMALY_RSSI_DROP:
                anomaly = True

        if is_whitelisted or is_router:
            suspicious = False
            score = 0.0
        else:
            indicators = (1 if hidden else 0) + (1 if is_camera else 0) + (1 if is_police else 0) + (1 if moving else 0) + (1 if anomaly else 0)
            suspicious = indicators >= 2
            score = indicators / 5.0

        if isinstance(history, deque):
            history = list(history)
        if isinstance(rssi_history, deque):
            rssi_history = list(rssi_history)

        d["is_camera"] = is_camera
        d["is_police"] = is_police
        d["is_whitelisted"] = is_whitelisted
        d["is_router"] = is_router
        d["is_moving"] = moving
        d["is_anomaly"] = anomaly
        d["suspicion_score"] = round(score, 2)
        d["suspicious"] = suspicious
        d["movement_history"] = history
        d["rssi_history"] = rssi_history
        d["indicators"] = {
            "hidden": hidden,
            "camera": is_camera,
            "police": is_police,
            "moving": moving,
            "anomaly": anomaly
        }
        d["camera_type"] = camera_type
        return d

    def ingest(self, mac, kind, rssi=None, name="", ssid="", ftype="", oui_flock=False, gps=None, flock_conf=None, source="phone"):
        mac = (mac or "").upper()
        if not mac:
            return None
        now = time.time()
        dist_ft = rssi_to_feet(rssi)
        oui_result = match_oui(mac) if mac else None
        is_camera = False
        is_police = False
        is_whitelisted = False
        camera_type = None
        if oui_result:
            label, is_camera, is_whitelisted = oui_result
            if label == "Police Equipment":
                is_police = True
            prefix = mac.lower()[:8]
            camera_type = get_camera_type(prefix)
        is_router = is_router_ssid(ssid)

        with self.lock:
            d = self.devices.get(mac)
            if d is None:
                d = {
                    "mac": mac,
                    "kind": kind,
                    "first_seen": now,
                    "last_seen": now,
                    "rssi": rssi,
                    "dist_ft": dist_ft,
                    "name": name,
                    "ssid": ssid,
                    "ftype": ftype,
                    "oui_flock": oui_flock,
                    "flock_conf": flock_conf,
                    "gps_samples": [],
                    "suspicious": False,
                    "sightings": 0,
                    "source": source,
                    "hidden": (kind == "wifi" and not ssid),
                    "is_camera": is_camera,
                    "is_police": is_police,
                    "is_whitelisted": is_whitelisted,
                    "is_router": is_router,
                    "is_moving": False,
                    "is_anomaly": False,
                    "suspicion_score": 0.0,
                    "movement_history": deque(maxlen=MOVEMENT_HISTORY_LEN),
                    "rssi_history": deque(maxlen=10),
                    "camera_type": camera_type,
                }
                self.devices[mac] = d
            d["last_seen"] = now
            d["sightings"] += 1
            d["source"] = source
            if rssi is not None:
                d["rssi"] = rssi
                d["dist_ft"] = dist_ft
                d["rssi_history"].append(rssi)
            if name:
                d["name"] = name
            if ssid:
                d["ssid"] = ssid
                d["hidden"] = False
                d["is_router"] = is_router_ssid(ssid)
            elif kind == "wifi" and not d.get("ssid"):
                d["hidden"] = True
            if ftype:
                d["ftype"] = ftype
            if oui_flock:
                d["oui_flock"] = True
            if flock_conf:
                d["flock_conf"] = flock_conf
            if gps and gps.get("lat") is not None:
                d["gps_samples"].append({"lat": gps["lat"], "lon": gps["lon"], "rssi": rssi, "ts": now})
                d["gps_samples"] = d["gps_samples"][-200:]
            oui_result2 = match_oui(mac) if mac else None
            if oui_result2:
                label2, is_cam2, is_white2 = oui_result2
                d["is_camera"] = is_cam2
                d["is_police"] = (label2 == "Police Equipment")
                d["is_whitelisted"] = is_white2
                prefix2 = mac.lower()[:8]
                d["camera_type"] = get_camera_type(prefix2)
            if dist_ft is not None:
                d["movement_history"].append((now, dist_ft))
            return self._enrich_device(dict(d))

    def set_verdict(self, mac, flock_conf, bearing=None, dist=None):
        mac = (mac or "").upper()
        with self.lock:
            d = self.devices.get(mac)
            if d:
                d["flock_conf"] = flock_conf
                if bearing is not None:
                    d["bearing"] = bearing
                if dist is not None:
                    d["dist"] = dist

    def _prune(self, now):
        cutoff = now - self.stale_seconds
        dead = [m for m, d in self.devices.items() if d["last_seen"] < cutoff]
        for m in dead:
            del self.devices[m]

    def view(self, which, source=None):
        now = time.time()
        with self.lock:
            self._prune(now)
            items = [dict(d) for d in self.devices.values()]
        items = [self._enrich_device(d) for d in items]
        if source:
            items = [d for d in items if d.get("source") == source]
        if which == "flock":
            return [d for d in items if d.get("flock_conf") in ("H", "M", "HIGH", "MEDIUM")]
        if which == "ble":
            return [d for d in items if d["kind"] == "ble"]
        if which == "all":
            return items
        return items

    def snapshot(self, source=None):
        all_devs = self.view("all", source)
        ble_devs = self.view("ble", source)
        flock_devs = self.view("flock", source)
        return {"all": all_devs, "ble": ble_devs, "flock": flock_devs, "clusters": {}}
