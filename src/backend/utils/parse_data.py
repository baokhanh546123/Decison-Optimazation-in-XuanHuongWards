from __future__ import annotations
from shapely import wkb, wkt
from shapely.geometry.base import BaseGeometry
from shapely.geometry import Point

def _parse_geometry(val) -> BaseGeometry | None:
  if val is None or isinstance(val , float) and np.isnan(val):
    return None
  if isinstance(val , BaseGeometry):
    return val
  if isinstance(val, (bytes, bytearray)):
    return wkb.loads(val)
  if isinstance(val, str):
    try:
      return wkb.loads(bytes.fromhex(val))
    except Exception:
      return wkt.loads(val)
  return None

def _parse_modes(val) -> Optional[frozenset]:
    """Chuẩn hoá allowed_modes/denied_modes lộn xộn (None, 'car', "['car' 'motorcycle']")."""
    if val is None:
        return None
    if isinstance(val, float) and np.isnan(val):
        return None
    if isinstance(val, (list, tuple, set, frozenset, np.ndarray)):
        return frozenset(str(v) for v in val)
    text = str(val).strip()
    if not text:
        return None
    tokens = re.findall(r"'([^']+)'", text)
    return frozenset(tokens) if tokens else frozenset({text})