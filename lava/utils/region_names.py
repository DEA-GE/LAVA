"""Shared region identity and generated-filename conventions."""

from __future__ import annotations

from dataclasses import dataclass

from unidecode import unidecode


def canonical_region_name(region_name: str) -> str:
    """Return the canonical region slug used by every generated LAVA file.

    Source/display names retain their original GADM spelling.  Manual scripts,
    Snakemake, and input planners must all pass that original name through this
    function before constructing generated data paths.
    """
    cleaned = unidecode(str(region_name).strip())
    for character in (" ", ".", "'", "_"):
        cleaned = cleaned.replace(character, "")
    return cleaned.replace("(", "-").replace(")", "-")


@dataclass(frozen=True)
class RegionNames:
    """Original source identity paired with its canonical generated-file slug."""

    original: str
    canonical: str

    @classmethod
    def from_original(cls, value: str) -> "RegionNames":
        original = str(value).strip()
        return cls(original=original, canonical=canonical_region_name(original))
