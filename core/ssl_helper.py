import os
import sys
import shutil
from pathlib import Path
from .config_manager import get_base_dir

def get_permanent_ca_bundle() -> str:
    """
    Ensures a valid cacert.pem exists in a permanent Windows directory (AppData or base dir).
    This prevents PyInstaller temporary folder cleanup (when GUI window closes) from breaking
    HTTPS requests in detached background workers or subsequent processes.
    """
    candidates = []

    # 1. First priority: %LOCALAPPDATA%\AxisPuls\cacert.pem
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        try:
            app_dir = Path(local_app_data) / "AxisPuls"
            app_dir.mkdir(parents=True, exist_ok=True)
            candidates.append(app_dir / "cacert.pem")
        except Exception:
            pass

    # 2. Second priority: get_base_dir() / "cacert.pem"
    try:
        base_dir = get_base_dir()
        candidates.append(base_dir / "cacert.pem")
    except Exception:
        pass

    # Check if any candidate already exists and is non-empty (>10KB)
    for c in candidates:
        try:
            if c.exists() and c.stat().st_size > 10000:
                return str(c)
        except Exception:
            continue

    # If none exist yet, extract/copy from certifi
    src_cert = None
    try:
        import certifi
        c_where = certifi.where()
        if os.path.exists(c_where) and os.path.getsize(c_where) > 10000:
            src_cert = c_where
    except Exception:
        pass

    if src_cert:
        for c in candidates:
            try:
                shutil.copyfile(src_cert, str(c))
                if c.exists() and c.stat().st_size > 10000:
                    return str(c)
            except Exception:
                continue

    # Fallback to certifi directly or system default True
    if src_cert:
        return src_cert
    return True

def apply_ssl_fix():
    """
    Configures environment variables, requests adapters, and urllib3 to always use
    the permanent CA bundle, preventing any TLS/SSL crashes when the GUI closes.
    """
    ca = get_permanent_ca_bundle()
    if isinstance(ca, str) and os.path.exists(ca):
        os.environ["REQUESTS_CA_BUNDLE"] = ca
        os.environ["CURL_CA_BUNDLE"] = ca
        os.environ["SSL_CERT_FILE"] = ca
        try:
            import requests.adapters
            requests.adapters.DEFAULT_CA_BUNDLE_PATH = ca
        except Exception:
            pass
    else:
        for var in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE"):
            val = os.environ.get(var)
            if val and not os.path.exists(val):
                os.environ.pop(var, None)
    return ca
