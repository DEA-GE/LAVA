import os

from unidecode import unidecode


def clean_region_name(region_name: str) -> str:
    """
    Cleans a region name string by:
    - Removing accents and diacritics
    - Removing spaces, periods, and apostrophes

    Parameters:
        region_name (str): The original region name

    Returns:
        str: A sanitized version of the region name
    """
    region_name_clean = unidecode(region_name)
    region_name_clean = region_name_clean.replace(" ", "")
    region_name_clean = region_name_clean.replace(".", "")
    region_name_clean = region_name_clean.replace("'", "")
    region_name_clean = region_name_clean.replace("_", "")
    region_name_clean = region_name_clean.replace("(", "-")
    region_name_clean = region_name_clean.replace(")", "-")
    return region_name_clean


def log_scenario_run(
    region: str, technology: str, scenario: str, log_dir: str = "logs"
) -> None:
    """Append a record of a scenario run to a log file.

    Parameters
    ----------
    region : str
        Name of the region.
    technology : str
        Technology used for the run.
    scenario : str
        Scenario identifier.
    log_dir : str, optional
        Directory where the log file is stored, by default ``"logs"``.
    """
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "scenario_runs.log")

    # Ensure the log file exists
    if not os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8"):
            pass

    # Read existing technology-scenario combinations
    existing = set()
    with open(log_file, "r", encoding="utf-8") as fh:
        for line in fh:
            parts = line.strip().split(",")
            if len(parts) >= 3:
                existing.add((parts[1], parts[2]))

    # Append new entry only if combination is not present
    if (technology, scenario) not in existing:
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write(f"{region},{technology},{scenario}\n")


def rel_path(path: str) -> str:
    """
    Returns a relative path from a given path.

    Parameters:
        path (str): The global path.

    Returns:
        str: The relative path if possible, otherwise the absolute path.
    """
    try:
        return os.path.relpath(path)
    except ValueError:
        return os.path.abspath(path)
