import math

TX_POWER_1M = -45.0
PATH_LOSS_N = 3.0
EARTH_R = 6371000.0

def rssi_to_distance(rssi):
    if rssi is None:
        return None
    try:
        d = 10 ** ((TX_POWER_1M - float(rssi)) / (10 * PATH_LOSS_N))
    except Exception:
        return None
    return round(max(0.5, min(d, 2000)), 1)

def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))

def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360

def estimate_position(samples):
    gps_samples = [s for s in samples if s.get("lat") is not None and s.get("rssi") is not None]
    if not gps_samples:
        return {"method": "none", "confidence": "unknown"}
    if len(gps_samples) == 1:
        s = gps_samples[0]
        return {
            "method": "distance_ring",
            "confidence": "low",
            "ring_center": {"lat": s["lat"], "lon": s["lon"]},
            "distance_m": rssi_to_distance(s["rssi"])
        }
    total_w = 0.0
    wlat = wlon = 0.0
    for s in gps_samples:
        w = max(0.01, (float(s["rssi"]) + 100.0)) ** 2
        wlat += s["lat"] * w
        wlon += s["lon"] * w
        total_w += w
    est_lat = wlat / total_w
    est_lon = wlon / total_w
    lats = [s["lat"] for s in gps_samples]
    lons = [s["lon"] for s in gps_samples]
    spread_m = haversine(min(lats), min(lons), max(lats), max(lons))
    n = len(gps_samples)
    if n >= 5 and spread_m > 30:
        conf = "good"
    elif n >= 3:
        conf = "medium"
    else:
        conf = "low"
    return {
        "method": "weighted_centroid",
        "confidence": conf,
        "estimate": {"lat": round(est_lat, 6), "lon": round(est_lon, 6)},
        "samples": n,
        "spread_m": round(spread_m, 1)
    }
