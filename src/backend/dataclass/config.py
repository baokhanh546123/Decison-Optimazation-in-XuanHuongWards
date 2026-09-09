from dataclasses import dataclass

@dataclass
class configs:
    WGS84 : str = "EPSG:4326"
    UTM48N : str = "EPSG:32648"  # project standard, see admin-boundary reprojection step