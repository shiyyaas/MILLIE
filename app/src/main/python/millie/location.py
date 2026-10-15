import json
import subprocess

def get_fix(provider="gps", timeout=10):
    try:
        out = subprocess.run(["termux-location", "-p", provider], capture_output=True, text=True, timeout=timeout)
        data = json.loads(out.stdout or "{}")
        if "latitude" in data:
            return {
                "lat": data.get("latitude"),
                "lon": data.get("longitude"),
                "accuracy": data.get("accuracy"),
                "provider": provider
            }
    except Exception:
        pass
    return None

def get_fix_any(timeout=10):
    fix = get_fix("gps", timeout=timeout)
    if fix:
        return fix
    return get_fix("network", timeout=timeout)
