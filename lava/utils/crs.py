from pathlib import Path

from pyproj import CRS


def save_crs(crs: CRS, path: str | Path) -> None:
    wkt_path = Path(path)
    wkt_path.write_text(crs.to_wkt(), encoding="utf-8")
    wkt_path.with_suffix(".tag").write_text(crs_tag(crs), encoding="utf-8")


def load_crs(path: str | Path) -> CRS:
    return CRS.from_wkt(Path(path).read_text(encoding="utf-8"))


def crs_tag(crs: CRS, path: str | Path | None = None) -> str:
    if path is not None:
        wkt_crs = load_crs(path)
        tag_path = Path(path).with_suffix(".tag")
        if crs.equals(wkt_crs) and tag_path.exists():
            return tag_path.read_text(encoding="utf-8").strip()

    authority = crs.to_authority()
    return "".join(authority) if authority else crs.to_string().replace(":", "_")
