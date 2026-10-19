# Full Workflow

This guide walks through the end-to-end workflow for running the Land Availability Analysis (LAVA)
tool on a new study region.

## Overview of the full workflow

0. Complete the tool and basic data setup.
1. Create the study-region configuration files in `configs/`.
2. Run `python -m lava.spatial_data_prep` to download and prepare necessary data.
3. Inspect the pre-processed data (optional but recommended) with `data_explore.ipynb`.
4. Run `python -m lava.exclusion` for each technology to create available-land rasters.

## Configuration files

In the **configs-folder** copy the file `config_template.yaml`, rename it to `config.yaml` and fill it out. This is your main configuration file for the data download.

For the exclusion criterias copy the files `onshorewind_template.yaml` and `solar_template.yaml`. Rename them to `onshorewind.yaml` and `solar.yaml` respectively. Fill these files out in order to set the exclusion parameters.
The top-level values in each technology file define the reference scenario. Use `reference_scenario` to set its name and `additional_scenarios` to store only the changed values for additional scenarios.

## Prepare spatial data

Run `python -m lava.spatial_data_prep` from the repository root after configuring the study region. `PROJECT_ROOT` anchors config, raw-data, and output paths at the repository, while relative paths supplied in config are resolved against that root and absolute paths are preserved. It clips the raw inputs to the
study area, aligns rasters, and computes helper layers such as slope, terrain ruggedness, and
proximity rasters.
```bash
python -m lava.spatial_data_prep --region <RegionName>
```

When `landcover_source` is `openeo` the script will prompt for Copernicus Data Space
credentials the first time it runs. Outputs are written to `data/<RegionName>/` and include:

- CRS definitions (`*_global_CRS.wkt`, `*_local_CRS.wkt`) and matching `.tag` files used downstream to preserve filename tags, including for custom CRSs.
- Clipped and projected rasters for DEM, landcover, terrain ruggedness, and optional layers. Wind and solar atlas rasters are clipped in their source CRS and aligned to the suitability grid downstream.
- `derived_from_DEM/` containing slope, aspect, terrain ruggedness, and north-facing masks.
- `OSM_Infrastructure/` geopackages for each enabled infrastructure category.
- `landuses_<RegionName>.json` and `pixel_size_<RegionName>_<CRS>.json` describing the
  land-cover codes and raster resolution required by the exclusion routines.

If you have outputs from an earlier version that contain only CRS `.pkl` files, rerun spatial
preparation before running downstream workflows. The current scripts read the WKT CRS files.

## Inspect data inputs

Use `data_explore.ipynb` to verify the preprocessing results. The notebook loads data from the
`data/<RegionName>/` folder, visualises selected layers, and summarises the available land-cover
codes to support tuning of exclusion thresholds.

## Land eligibility exclusions

Create technology-specific available-land rasters by running `python -m lava.exclusion` from the repository root. The command-line
flags mirror the configuration entries so that single technologies or scenarios can be processed
independently.
```bash
python -m lava.exclusion --technology onshorewind --scenario <ScenarioName> --region <RegionName>
python -m lava.exclusion --technology solar --scenario <ScenarioName> --region <RegionName>
```

The script loads the prepared rasters and vector layers, applies the filters defined in the
technology configuration, and writes `*_available_land_*.tif` files under
`data/<RegionName>/available_land/`. A log of each scenario run is stored in the region folder
for traceability.

## Suitability and resource grades

Run `python -m lava.suitability` after both solar and wind exclusions are available. The module aligns
resource layers, applies terrain and region modifiers, and exports cost multipliers together with
thresholded resource-grade rasters in `data/<RegionName>/suitability/`.
```bash
python -m lava.suitability --region <RegionName> --scenario <ScenarioName>
```

## Energy profile simulation

Energy profiles combine the available land, suitability grades, and weather cut-outs. Ensure that
`configs/config.yaml` points `weather_data_path` to the directory that contains the prepared
atlite cut-outs. Then run:
```bash
python -m lava.energy_profiles --region <RegionName> --technology onshorewind --scenario <ScenarioName> --weather_year 2019
python -m lava.energy_profiles --region <RegionName> --technology solar --scenario <ScenarioName> --weather_year 2019
```

Outputs are written to `data/<RegionName>/energy_profiles/` and include resource-grade time series
as well as diagnostic plots documenting the available area shares.

## Batch processing with Snakemake

For large-scale studies the `snakemake/Snakefile` orchestrates all stages across multiple regions,
technologies, scenarios, and weather years. The workflow creates `snakemake_log` sentinels to prevent reruns
of completed steps. Launch it after customising `config_snakemake.yaml`, including the `scenarios` list:
```bash
snakemake --cores 4 --resources openeo_req=1
```

Use `--snakefile snakemake/Snakefile_short` or `Snakefile_short_short` for alternative presets.
The `openeo_req` resource serialises ESA WorldCover downloads to avoid rate limits while still
parallelising the remaining steps.