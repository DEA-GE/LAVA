from typing import Any, Mapping, Optional

def _pick_value(entry: Any, area: Optional[str]) -> Optional[str]:
    """
    Resolve a single config entry.

    Supported entry types:
      - str: applies to all areas
      - mapping: {area -> str}

    Returns:
      - str if resolved
      - None if no match at this entry
    """
    if isinstance(entry, str):
        return entry

    if isinstance(entry, Mapping) and area is not None:
        v = entry.get(area)
        if isinstance(v, str):
            return v

    return None

# Select based on region, region set, area, with defaults in order of precedence
def resolve_selection(
    cfg: Mapping[str, Any],
    key: str,
    *,
    area: Optional[str] = None,
    region_group: Optional[str] = None,
    region: Optional[str] = None,
    normalize_area: bool = True,
) -> str:
    """
    Resolve a selection under cfg[key] using precedence:

      1) by_region[region]      (str OR {area -> str})
      2) by_region_set[set]     (str OR {area -> str})
      3) default                (str OR {area -> str})

    Also supports the legacy simplest form:
      key: "value"

    Parameters
    ----------
    cfg : mapping
        The parsed config dict.
    key : str
        The top-level selection key to resolve (e.g. "turbine").
    area, region_set, region : optional str
        Context for resolving more specific overrides.
    normalize_area : bool
        If True, converts area to lowercase (useful if YAML uses lowercase keys).

    Returns
    -------
    str
        The resolved selection value.

    Raises
    ------
    KeyError if no match and no usable default.
    TypeError for invalid config shapes.
    """
    node = cfg.get(key)

    # Legacy simplest form: key: "X"
    if isinstance(node, str):
        return node

    if not isinstance(node, Mapping):
        raise TypeError(f"cfg[{key!r}] must be a string or a mapping")

    if area is not None and normalize_area:
        area = area.lower()

    # --- 1) Region ---
    if region:
        region_entry = node.get("by_region", {}).get(region)
        v = _pick_value(region_entry, area)
        if v is not None:
            return v

    # --- 2) Region group ---
    if region_group:
        group_entry = node.get("by_region_group", {}).get(region_group)
        v = _pick_value(group_entry, area)
        if v is not None:
            return v

    # --- 3) Default ---
    default_entry = node.get("default")
    v = _pick_value(default_entry, area)
    if v is not None:
        return v

    raise KeyError(
        f"No match for {key!r} with area={area!r}, region={region!r}, region_group={region_group!r}"
    )
