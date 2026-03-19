"""Helper functions for Snakemake workflow validation."""


def normalize_to_list(value):
    """
    Ensure a value is a list.
    
    If a string is passed, converts it to a single-item list.
    If a list is passed, returns it as-is.
    """
    if isinstance(value, str):
        return [value]
    return value


def resolve_weather_years(raw_years):
    """
    Normalise arbitrary weather-year inputs into a list.

    Supported forms:
    - Single integers/strings (2015 or "2015") -> [2015]
    - Iterables (lists/sets) -> flattened
    - Comma-separated strings ("2015,2020") -> [2015, 2020]
    - Ranges using "start*end" inclusive of start, exclusive of end,
      consistent with ``range`` semantics. Values are emitted as strings.
    """

    def _expand(value):
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            expanded = []
            for item in value:
                expanded.extend(_expand(item))
            return expanded
        if isinstance(value, (int, float)):
            return [int(value)]
        if isinstance(value, str):
            token = value.strip()
            if not token:
                return []
            if "*" in token:
                start_text, _, end_text = token.partition("*")
                try:
                    start_year = int(start_text)
                    end_year = int(end_text)
                except ValueError:
                    return [token]
                if start_year > end_year:
                    start_year, end_year = end_year, start_year
                return [str(y) for y in range(start_year, end_year)]
            if "," in token:
                expanded = []
                for part in token.split(","):
                    expanded.extend(_expand(part))
                return expanded
            try:
                return [int(token)]
            except ValueError:
                return [token]
        return [value]

    seen = set()
    normalised = []
    for entry in _expand(raw_years):
        key = str(entry)
        if not key:
            continue
        if key not in seen:
            seen.add(key)
            normalised.append(entry)
    return normalised


def validate_stage_dependencies(stages_config):
    """
    Check for workflow dependencies based on enabled stages.
    
    Execution order: 
    1) spatial_data_prep
    2) exclusion (depends on spatial_data_prep)
    3) suitability (depends on exclusion)
    4) weather_data_prep, weather_bias_adjust (can run in parallel with 3)
    5) energy_profiles (depends on suitability, weather_data_prep, weather_bias_adjust)
    
    Parameters
    ----------
    stages_config : dict
        Dictionary of stages with boolean values indicating if they are enabled.
    """
    warnings = []
    
    # Extract stage status
    do_spatial_data_prep = stages_config.get("spatial_data_prep", False)
    do_exclusion = stages_config.get("exclusion", False)
    do_suitability = stages_config.get("suitability", False)
    do_weather_data_prep = stages_config.get("weather_data_prep", False)
    do_weather_bias_adjust = stages_config.get("weather_bias_adjust", False)
    do_energy_profiles = stages_config.get("energy_profiles", False)
    
    # Check exclusion stage
    if do_exclusion and not do_spatial_data_prep:
        warnings.append(
            "[WARNING] Stage 'exclusion' is enabled but requires 'spatial_data_prep' to be enabled."
        )
    
    # Check suitability stage
    if do_suitability and not do_exclusion:
        warnings.append(
            "[WARNING] Stage 'suitability' is enabled but requires 'exclusion' to be enabled."
        )
    
    # Check energy_profiles stage
    if do_energy_profiles:
        missing_deps = []
        if not do_suitability:
            missing_deps.append("suitability")
        if not do_weather_data_prep:
            missing_deps.append("weather_data_prep")
        if not do_weather_bias_adjust:
            missing_deps.append("weather_bias_adjust")
        
        if missing_deps:
            warnings.append(
                f"[WARNING] Stage 'energy_profiles' is enabled but requires the following stages to be enabled: {', '.join(missing_deps)}."
            )
    
    # Print all warnings
    if warnings:
        for warning in warnings:
            print(warning)
