"""
Central version specification for Axis Puls.
Follows Semantic Versioning (SemVer): MAJOR.MINOR.PATCH
"""

__version__ = "1.0.1"

def get_current_version() -> str:
    """Returns the current running software version."""
    return __version__

def is_newer_version(remote_ver: str, local_ver: str = __version__) -> bool:
    """
    Compares two semantic versions (e.g. 'v1.0.1' vs '1.0.0').
    Returns True if remote_ver > local_ver.
    """
    def clean_ver(v: str):
        v = str(v).strip().lstrip("vV")
        parts = []
        for x in v.split("."):
            try:
                parts.append(int(x))
            except ValueError:
                parts.append(0)
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    try:
        return clean_ver(remote_ver) > clean_ver(local_ver)
    except Exception:
        return False
