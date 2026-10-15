import os
import json
import re
import time
import requests
from pathlib import Path

def get_cache_file() -> Path:
    millie_home = os.environ.get("MILLIE_HOME")
    if millie_home:
        d = Path(millie_home)
    else:
        d = Path(__file__).parent
    d.mkdir(parents=True, exist_ok=True)
    return d / "oui_cache.json"

CACHE_TTL = 86400  # 24 hours

FLOCK_FALLBACK = [
    "70:c9:4e", "3c:91:80", "d8:f3:bc", "80:30:49", "b8:35:32",
    "14:5a:fc", "74:4c:a1", "08:3a:88", "9c:2f:9d", "c0:35:32",
    "94:08:53", "e4:aa:ea", "f4:6a:dd", "f8:a2:d6", "24:b2:b9",
    "00:f4:8d", "d0:39:57", "e8:d0:fc", "e0:4f:43", "b8:1e:a4",
    "70:08:94", "58:8e:81", "ec:1b:bd", "3c:71:bf", "58:00:e3",
    "90:35:ea", "5c:93:a2", "64:6e:69", "48:27:ea", "a4:cf:12",
    "82:6b:f2",
]
RING = [
    "00:b4:63", "18:7f:88", "24:2b:d6", "34:3e:a4", "50:e4:67",
    "54:e0:19", "5c:47:5e", "64:9a:63", "90:48:6c", "9c:76:13",
    "ac:9f:c3", "c4:db:ad", "cc:3b:fb",
]
BLINK = ["f0:74:c1", "3c:a0:70", "70:ad:43", "74:ab:93"]
AXON = ["00:58:28", "00:25:df", "84:70:03"]

POLICE = [
    "00:1a:2b", "00:0d:6f", "00:18:1a", "00:1e:4f", "00:1c:42",
    "00:1d:72", "00:22:64", "00:20:91", "00:25:9e", "00:30:65",
    "00:50:56", "00:0b:86", "00:1a:e1", "00:17:a4", "00:23:df",
]
POLICE.extend(AXON)

EERO = [
    "20:be:cd", "48:b4:24", "fc:3f:a6", "44:ac:85", "88:67:46",
    "68:4a:76", "00:ab:48", "08:9b:f1", "08:f0:1e", "0c:1c:1a",
    "14:22:db", "18:90:88", "20:e6:df", "24:2d:6c", "30:34:22",
    "28:ec:22", "3c:5c:f1", "d4:05:de", "30:57:8e", "5c:5a:35",
    "40:47:5e", "48:dd:0c", "4c:01:43", "50:27:a9", "5c:a5:bc",
    "60:57:7d",
]
ESPRESSIF = [
    "ac:67:b2", "84:f3:eb", "b4:e6:2d", "cc:db:a7", "24:0a:c4",
    "30:ae:a4", "94:b9:7e", "c0:49:ef", "08:3a:f2", "10:52:1c",
    "18:fe:34", "1c:bf:ce", "24:6f:28", "2c:3a:e8", "34:94:54",
    "3c:61:05", "40:f5:20", "44:17:93", "48:27:e2", "4c:11:ae",
    "50:02:91", "54:5a:a6", "58:bf:25", "5c:cf:7f", "60:55:f9",
    "64:b7:08", "68:c6:3a", "6c:19:8f", "70:03:9d", "74:da:38",
    "78:e3:6d", "7c:df:a1", "80:7d:3a", "84:0d:8e", "88:b1:e1",
    "8c:aa:ce", "90:97:d5", "94:65:2d", "98:f4:ab", "9c:9d:7e",
    "a0:76:4e", "a8:61:0a", "b0:a7:32", "b8:27:eb", "bc:dd:c2",
    "c4:4f:33", "c8:f0:9e", "d0:76:5f", "d8:a0:1d", "dc:4f:22",
    "e0:5a:1b", "e4:95:6e", "e8:68:e7", "ec:fa:bc", "f0:08:d1",
    "f4:12:fa", "f8:f0:05", "fc:f5:28",
]

ROUTER_SSID_PATTERNS = [
    "t-mobile", "xfinity", "spectrum", "att", "verizon",
    "starbucks", "googlewifi", "linksys", "netgear", "asus",
    "tp-link", "arcadyan", "sercomm",
]

def is_router_ssid(ssid):
    if not ssid:
        return False
    s = ssid.lower()
    return any(p in s for p in ROUTER_SSID_PATTERNS)

def fetch_ouis():
    try:
        url = "https://raw.githubusercontent.com/colonelpanichacks/flock-you/main/datasets/NitekryDPaul_wifi_ouis.md"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            lines = resp.text.splitlines()
            new_ouis = []
            for line in lines:
                match = re.search(r'([0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2})', line, re.I)
                if match:
                    new_ouis.append(match.group(1).lower())
            if new_ouis:
                return new_ouis
    except Exception:
        pass
    return FLOCK_FALLBACK

def get_flock_ouis():
    now = time.time()
    cache_file = get_cache_file()
    if cache_file.exists():
        try:
            with open(cache_file) as f:
                data = json.load(f)
            if (now - data.get("time", 0)) < CACHE_TTL:
                return data.get("flock", FLOCK_FALLBACK)
        except Exception:
            pass
    fresh = fetch_ouis()
    try:
        with open(cache_file, "w") as f:
            json.dump({"flock": fresh, "time": now}, f)
    except Exception:
        pass
    return fresh

FLOCK_OUIS = get_flock_ouis()
CAMERA_OUIS = set(RING + BLINK + FLOCK_OUIS + AXON)
POLICE_SET = set(POLICE)
EERO_SET = set(EERO)
ALL_OUIS = CAMERA_OUIS | POLICE_SET | EERO_SET | set(ESPRESSIF)

def get_camera_type(prefix):
    if prefix in RING:
        return "ring"
    if prefix in BLINK:
        return "blink"
    if prefix in FLOCK_OUIS:
        return "flock"
    if prefix in AXON:
        return "axon"
    return None

def match_oui(bssid):
    if not bssid or len(bssid) < 8:
        return None
    prefix = bssid.lower()[:8]
    if prefix in POLICE_SET:
        return "Police Equipment", True, False
    if prefix in EERO_SET:
        return "Eero (whitelisted)", False, True
    cam_type = get_camera_type(prefix)
    if cam_type:
        return f"{cam_type.upper()} Camera", True, False
    if prefix in ALL_OUIS:
        return "Other device", False, False
    return None
