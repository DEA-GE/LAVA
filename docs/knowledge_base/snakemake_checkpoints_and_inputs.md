# Snakemake checkpoints and input resolution

LAVA uses a Snakemake checkpoint and an input function to decide whether spatial
data preparation must run before an exclusion job. This design lets Snakemake
track the real files used by `Exclusion.py` instead of relying on a generic
completion marker.

## The problem Snakemake must solve

Snakemake normally builds its directed acyclic graph (DAG) before it runs any
job. For a conventional rule, every input and output can be named while this
initial DAG is being built.

LAVA's exclusion inputs are more dynamic. The exact set depends on:

- the selected region, technology, and scenario;
- the exclusion settings enabled by that scenario;
- the configured spatial-data sources;
- the region's calculated local coordinate reference system (CRS); and
- optional inputs that are required only when a corresponding exclusion is
  enabled.

For example, a solar job can require a solar-resource raster while an onshore
wind job requires a wind-resource raster. Enabling a roads buffer adds the
roads file as a required dependency. The filename of a projected file also
contains the local CRS, which is established during spatial preparation.

A single file such as `.done` could say that a preparation command finished at
some point, but it would not tell Snakemake which rasters and vectors the next
exclusion job actually needs. It would also hide missing or outdated files from
normal dependency tracking.

## The dependency chain

The workflow follows this sequence:

```text
Final exclusion target
        |
        v
exclusion_inputs(wildcards)
        |
        v
spatial_data_prep checkpoint for the region
        |
        v
Snakemake updates the DAG after the checkpoint
        |
        v
resolve_exclusion_inputs(...)
        |
        v
Exact configuration, raster, vector, and CRS files
        |
        v
Exclusion.py
```

This separates two questions:

1. Has the region reached the point where its generated spatial information can
   be inspected?
2. Which exact files does this particular exclusion job require?

The checkpoint answers the first question. The input resolver answers the
second.

## Step 1: final targets define the requested work

The main Snakefile reads `config_snakemake.yaml` and expands the requested
regions, technologies, and scenarios into final output targets. A target has a
form such as:

```text
data/Sjaelland/available_land/Sjaelland_solar_reference_available_land.tif
```

Snakemake works backward from that target to the `exclusion` rule. Even when
the spatial-preparation stage is not selected as a final target, its checkpoint
rule is included whenever exclusion is enabled because exclusion may depend on
prepared data.

Including the checkpoint does not automatically rerun preparation. Snakemake
first evaluates whether its regional output and declared inputs are current.

## Step 2: the checkpoint prepares and validates a region

The spatial preparation checkpoint is defined once per region. Its declared
output is the real local-CRS file:

```text
data/<region>/<region>_local_CRS.pkl
```

This is not a synthetic `.done` marker. `Exclusion.py` uses the file itself, and
the input resolver reads it to determine CRS-specific filenames.

The checkpoint declares the following inputs:

- `configs/config.yaml`;
- the advanced spatial-preparation settings;
- `spatial_data_prep.py`;
- the exclusion-input resolver; and
- the spatial-preparation planner.

Consequently, Snakemake can schedule the checkpoint when the regional CRS file
is missing or when one of these preparation dependencies is newer. The UI can
also force only the affected regional checkpoints when its preflight inspection
finds a missing or incompatible prepared file.

When scheduled, the checkpoint:

1. removes the previous local-CRS output so an unsuccessful refresh cannot look
   complete;
2. runs `spatial_data_prep.py` with unbuffered Python output;
3. verifies that the real local-CRS output was recreated;
4. validates the files required by the selected exclusion jobs; and
5. removes the checkpoint output again if validation fails.

A successful process exit alone is therefore not treated as proof that the
region is ready.

## Step 3: Snakemake reevaluates the DAG

An ordinary input function is evaluated while the initial DAG is constructed.
A checkpoint changes that behavior. The exclusion input function requests the
regional checkpoint with:

```python
spatial_checkpoint = checkpoints.spatial_data_prep.get(
    region=wildcards.region
)
```

If the checkpoint has not completed, Snakemake pauses resolution of that branch
and schedules the checkpoint. After it completes, Snakemake reevaluates the
input function and updates the DAG. This is why the log says:

```text
DAG of jobs will be updated after completion.
```

During the first planning pass, checkpoint-dependent values can appear as
`<TBD>`. That is normal: Snakemake intentionally waits for the checkpoint
before resolving those values.

## Step 4: the input function returns exact files

After the checkpoint, `exclusion_inputs(wildcards)` calls
`resolve_exclusion_inputs(...)` with the region, technology, scenario, and
actual local-CRS file.

The resolver reads the relevant configuration and returns the concrete files
for that job. Depending on its settings, the list can contain:

- `config.yaml` and the selected technology configuration;
- global and local CRS objects;
- the prepared study-area geometry;
- pixel-size metadata;
- land-cover, elevation, slope, population, wind, or solar rasters;
- selected OpenStreetMap layers;
- protected areas and other vector constraints; and
- optional user-provided exclusion or inclusion layers when enabled.

Snakemake then records these paths as normal dependencies of the exclusion job.
If a required file is missing, the job is blocked before `Exclusion.py` starts.
If an input is regenerated and becomes newer than an existing exclusion result,
Snakemake reruns that result.

## Why both a checkpoint and exact inputs are needed

Using only the checkpoint output would serialize the tasks correctly, but it
would make Snakemake blind to the remaining files consumed by exclusion. Using
only an ordinary exact-input function would not work reliably because the local
CRS and prepared state may not exist when the initial DAG is built.

Together they provide:

- **ordering** — preparation finishes before exclusion input resolution;
- **dynamic discovery** — CRS- and scenario-dependent paths are resolved after
  preparation;
- **incremental execution** — existing compatible inputs are reused;
- **targeted reruns** — changed inputs rerun only affected downstream jobs; and
- **failure safety** — incomplete preparation cannot leave a valid-looking
  checkpoint output.

## The UI preflight planner

Before starting Snakemake, the UI performs an additional read-only check with
`utils/spatial_prep_plan.py`. It resolves the same exclusion requirements and
inspects existing files, including configuration-sensitive raster properties
such as openEO land-cover resolution.

The planner can produce three outcomes:

- **Ready:** use the normal Snakemake command and let timestamp-based dependency
  tracking apply.
- **Repairable:** add the affected regional checkpoint outputs to `--forcerun`
  so spatial preparation refreshes them before exclusion.
- **Blocked:** report an external user-supplied input that spatial preparation
  cannot create.

The preflight does not replace Snakemake. It handles compatibility information
that cannot be inferred from a filename or timestamp, while the checkpoint and
input function remain responsible for execution order and the runtime DAG.

During a dry run, forced checkpoints are shown in planning mode, but no spatial
data are downloaded or modified.

## Configuration changes and reruns

Different changes affect the workflow in different ways:

| Change | Effect |
|---|---|
| Region added | A new regional checkpoint and downstream targets are created. |
| Technology or scenario added | New exclusion targets and their exact inputs are resolved. |
| Technology exclusion setting changed | Its configuration dependency causes the affected exclusion outputs to rerun. |
| General or advanced preparation setting changed | The regional preparation checkpoint becomes eligible to rerun. |
| Prepared input missing or incompatible | UI preflight forces the affected checkpoint, or runtime validation blocks exclusion. |
| Unrelated compatible input unchanged | Snakemake reuses it. |

Changing configuration is therefore more than changing a command-line value:
the configuration files participate in the dependency graph.

## Failure behavior

If authentication, downloading, transformation, or validation fails:

1. the checkpoint fails;
2. its local-CRS output is removed;
3. Snakemake does not release the dependent exclusion branch; and
4. a later run can retry preparation rather than accepting a stale completion
   signal.

Other regions whose checkpoints and inputs are valid remain independently
trackable.

## Region names and backward compatibility

The configured original name identifies the GADM or custom source boundary,
while a shared canonical name identifies generated paths. For example,
`Sjælland` selects the original source and `Sjaelland` is used under `data/`.
Manual runs and Snakemake use the same naming function, so they address the same
generated files.

Custom study-area GeoJSON files should be grouped in named collection folders,
for example `Raw_Spatial_Data/custom_study_area/gadm_areas/SjÃ¦lland.geojson`,
and `custom_study_area_filename` should contain the relative path
`gadm_areas/{region_name}.geojson`. Older flat files and files using the
canonical cleaned filename remain accepted as fallbacks. Existing prepared
caches without the newer land-cover metadata can also be reused when their real
raster properties match the current request.

## Inspect the decision outside the UI

The preflight decision can be inspected without executing Snakemake:

```powershell
python utils/spatial_prep_plan.py
```

For machine-readable output:

```powershell
python utils/spatial_prep_plan.py --json
```

Use a Snakemake dry run to inspect the resulting job graph:

```powershell
snakemake --snakefile snakemake/Snakefile --cores 1 --resources openeo_req=1 --dry-run --printshellcmds
```

The planner explains whether existing spatial inputs are compatible. The
Snakemake dry run explains which rules and checkpoints the dependency graph
would execute.
