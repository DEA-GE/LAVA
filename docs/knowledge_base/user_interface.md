# User interface overview

The LAVA desktop user interface provides one place to initialize and edit the
configuration files, run individual processing scripts or a Snakemake workflow,
inspect messages and logs, aggregate results, and open generated spatial layers
in a web map. It calls the same Python scripts and uses the same YAML files as a
terminal run; it does not maintain a separate copy of the model configuration.

This page explains the purpose of each section and the basic process for using
the interface. For the scientific processing steps, also see the
[Basic Workflow](../home/basic_workflow.md) and
[Full Workflow](../home/full_workflow.md).

## Starting the interface

Activate the `lava` environment and start the application from the repository
root:

```bash
python tkinter_app/main.py
```

The main window opens maximized. The available top-level tabs are
**Configuration**, **Run**, **Results**, and **Documentation**. A **Setup** tab
is shown instead when required active configuration files have not yet been
created.

## Interface sections at a glance

| Section | Main purpose |
| --- | --- |
| Setup | Create active YAML files from templates and optionally prepare custom study-area files from GADM data. |
| Configuration | Edit, search, validate, and save the YAML configuration and Snakefile. |
| Run | Run one Python script or the configured Snakemake workflow and monitor its output. |
| Results | Aggregate result metrics, remove a scenario's generated results, and open spatial layers on a map. |
| Documentation | Read the complete local documentation and open the corresponding online page. |

## Setup

LAVA distinguishes between configuration templates and active configuration
files. If one or more required active files are missing, the configuration
editor and run controls remain unavailable until initialization is complete.

The setup dialog can:

- create the active files from the default templates;
- use an available country example as the template source;
- preserve existing files or replace them when overwrite is enabled; and
- optionally extract study areas from a GADM input file into
  `Raw_Spatial_Data/custom_study_area/`.

The preview lists the source and destination of every configuration file before
anything is created. Preparing GADM study areas is optional and does not change
the configuration templates. The original GADM area names are used consistently
so manual runs and Snakemake runs resolve the same region folders and filenames.

## Configuration tab

The Configuration tab is the shared editor for all active settings. It is
divided into the following categories:

| Category | Main document or purpose |
| --- | --- |
| General | `configs/config.yaml`, including spatial data sources and general study settings. |
| Technology exclusions | `onshorewind.yaml`, `solar.yaml`, and optional technology configuration files. |
| Suitability | `configs/suitability.yaml`. |
| Workflow | `configs/config_snakemake.yaml`, which selects batch jobs and workflow stages. |
| Advanced settings | `configs/advanced_settings/advanced_data_prep_settings.yaml`. |
| Snakefile | The Snakemake workflow definition selected by the project. |

### Visual editor and raw YAML

The visual editor presents documented settings as controls and provides help
text beneath settings where available. The raw YAML view is useful when editing
nested structures directly. Both views represent the same document; switching
views is not a second save operation.

Changes remain pending until they are saved. **Save All** writes all modified
documents after validation succeeds. Search can find a setting by key, label,
or description across the configuration documents. **Help & glossary** provides
additional explanations for configuration terms.

### Validation

Validation runs automatically when the editor is loaded and can also be started
with **Validate all configurations**. The compact results area is scrollable;
**Open larger...** displays the complete list in a larger window. Opening an
issue takes the user to its related document and setting when that location can
be resolved.

Validation levels have different consequences:

- An **error** is a configuration inconsistency that blocks saving or running.
- A **warning** is advisory and does not block a run.

For example, scenario selections for a technology that is not selected in the
workflow are warnings because they do not affect the requested jobs. A requested
scenario that is absent from a selected technology configuration is an error,
because the exclusion rule would have no parameter definition to use.

### Regions, technologies, and scenarios

The Workflow configuration determines which combinations Snakemake requests.
Study-region choices are discovered from
`Raw_Spatial_Data/custom_study_area/`. The editor supports adding one region,
removing one, or adding all discovered regions.

The scenario entry in `config_snakemake.yaml` does not replace exclusion
parameters in a technology YAML file. It selects a named scenario already
defined there:

1. Each technology file defines its reference scenario and any additional
   scenario overrides.
2. The workflow selects technologies and scenario names.
3. Snakemake creates the requested region, technology, and scenario
   combinations.
4. Each selected scenario must be resolvable for each selected technology.

Consequently, one scenario name can be used for both solar and onshore wind, but
that name must be defined for both technology configurations. The actual values
may differ between technologies.

## Run tab

The Run tab has two execution modes. Both modes use the current saved files on
disk. Unsaved editor changes are not silently passed to a subprocess.

### Single Script mode

Single Script mode runs one program with Python in unbuffered mode so progress
messages appear in the interface as they are printed. The available programs
are:

| Script | Inputs selected in the interface |
| --- | --- |
| `spatial_data_prep.py` | Region |
| `Exclusion.py` | Region, technology, and scenario |
| `suitability.py` | Region and scenario |
| `weather_data_prep.py` | Region and weather year |
| `weather_bias_adjust.py` | No additional command-line selection |
| `energy_profiles.py` | Region, technology, scenario, and weather year |

Only inputs relevant to the selected script are shown. The interface builds the
documented command line and starts it from the appropriate project directory.
This mode is useful for rerunning or diagnosing one processing step. It does not
automatically run that script's upstream dependencies.

### Snakemake Workflow mode

Snakemake Workflow mode reads its execution settings from
`configs/config_snakemake.yaml`. These include the selected stages, regions,
technologies, scenarios, Snakefile, number of cores, and related workflow
options. The interface displays the selected Snakefile and core count, but the
configuration document remains their source of truth.

Snakemake builds a dependency graph and runs only jobs whose requested outputs
are missing or older than their inputs. For exclusions, LAVA uses a checkpoint
and exact input resolution to determine whether spatial preparation must run
again. This is explained in
[Snakemake checkpoints and input resolution](snakemake_checkpoints_and_inputs.md).

### Preflight and dry run

Before starting either execution mode, the UI performs a preflight check. It
validates the configuration, resolves the command and working directory, checks
required programs and files, and presents detected errors and warnings.

Errors prevent confirmation. Warnings can be reviewed before deciding whether
to continue. The preflight for a spatial preparation or Snakemake run can also
summarize why prepared spatial data is considered reusable or why preparation
is required.

For Snakemake runs, the **Workflow plan** view expands the configured stages
into their requested region, technology, scenario, and weather-year targets.
Implicit dependencies are included; for example, an exclusion request also
shows spatial data preparation. A missing output is marked as planned to run,
while an existing output is marked for a freshness check. Prepared spatial
inputs can be identified as reusable from the spatial preflight. These statuses
are preliminary: Snakemake's dry run makes the final timestamp and dependency
decision.

**Dry run** is available only in Snakemake Workflow mode. It asks Snakemake to
construct and report the planned jobs without executing them. A successful dry
run is a useful dependency and configuration check, but it cannot guarantee
that external downloads, authentication, memory use, or the scripts themselves
will succeed during execution.

### Monitoring a run

During execution, the Run tab reports the current stage, region, completed and
remaining jobs, duration, and process output. Web addresses printed by a process
are clickable, which is particularly useful when an external data service asks
the user to authenticate in a browser.

The feedback area contains:

- **Output**, containing the live process stream;
- **Warnings & Errors**, containing classified messages and links to related
  settings where available; and
- **Run history**, containing previous UI-launched runs.

**Open larger...** displays these views in a resizable window. **Copy command**
copies the exact command for reproduction in a terminal. **Open full log** opens
the complete log for the latest run, while **Open output folder** opens the most
relevant generated-data location.

**Stop** requests termination of the active process. **Reset** clears the active
run state after the process has stopped; it does not delete generated data.
Only one main workflow operation is allowed at a time. Results aggregation and
scenario deletion are also disabled while the Run tab owns an active workflow,
preventing simultaneous changes to the same result files.

### Run completion summary

When a process finishes, the UI presents a summary containing its outcome,
duration, execution context, detected warnings or errors, and output location.
The process exit code remains decisive: a summary can explain a failure, but it
does not convert a failed command into a successful run.

Logs created by the interface are stored below `logs/ui_runs/`, and UI run
history is maintained in `logs/ui_run_history.json`. Snakemake can additionally
write its own logs below `.snakemake/log/`.

## Results tab

The Results tab contains three sections.

### Aggregated Results

**Run results_analysis.py** scans generated results and creates the aggregated
outputs, including `aggregated_available_land.json`. The table displays scenario,
technology, region, eligibility share, available area, and power potential.
Each column can be filtered using a case-insensitive text match. The execution
log is intentionally compact and scrollable so more space remains available for
the result table. Select a column heading to sort it; metric columns are sorted
numerically, including values stored in scientific notation.

### Scenario Comparison

Select a baseline scenario (Scenario A) and a comparison scenario (Scenario B)
to match results by technology and region. The table presents both values and
calculates Scenario B minus Scenario A for:

- eligibility share in percentage points;
- available area in square kilometres; and
- power potential in terawatts.

Technology and region filters can narrow the comparison. Rows present in only
one scenario remain visible with blank unavailable values rather than being
silently removed. Comparison columns are sortable and the displayed comparison
can be exported as UTF-8 CSV or as an Excel workbook. Excel export requires
`openpyxl`; if it is unavailable, CSV export remains available.

The chart below the table can group differences by region or technology and can
show any of the three metrics. Green bars are positive changes and red bars are
negative changes. Eligibility differences are averaged when several rows are
combined; area and power differences are summed.

### Delete Scenario Results

This section discovers scenarios with generated files. Selecting a scenario
shows the exact project-relative paths that would be removed. Deletion requires
confirmation and invalidates aggregated outputs so that old summaries are not
mistaken for current results.

Review the file preview carefully. Scenario deletion changes generated data and
is different from removing a scenario selection from
`config_snakemake.yaml`, which only changes future requested jobs.

### Map

The Map section discovers supported layers under `data/<region>/`. Select a
region to list its available GeoTIFF, GeoJSON, and GeoPackage layers. Up to three
layers can be selected, ordered, renamed, and assigned an opacity. Temporary
files and old-resolution backups are omitted from the preset list.

Technology and scenario filters narrow the available-land outputs for the
selected region. **Add Matching Results** fills the available layer slots with
matching result rasters, which makes comparing scenarios or technologies faster.

**Load Map** prepares an interactive HTML map and opens it in the system's
default web browser. The map is intentionally browser-based rather than embedded
in the Tkinter window. A custom plain-text or HTML legend can be added before
opening it. After loading, **Save Map HTML...** saves a portable copy of the
interactive map for later viewing or sharing.

## Documentation tab

The Documentation tab reads the complete local MkDocs documentation tree,
including Home, Knowledge Base, and Contributing pages. Select a page from the
navigation tree to render it in the interface. Links, images, code blocks, and
tables are rendered locally where supported.

**Open Online** opens the corresponding published documentation page in the
default browser. The local page reflects the checked-out repository version,
whereas the online page reflects the currently published documentation and may
therefore differ.

## Recommended UI workflow

For a normal Snakemake analysis:

1. Complete **Setup** if the active configuration files do not exist.
2. In **Configuration > General**, define the study area and spatial data
   sources.
3. Configure the required technology scenarios under **Technology exclusions**
   and, when needed, configure **Suitability** and advanced data preparation.
4. In **Configuration > Workflow**, select the stages, regions, technologies,
   scenarios, Snakefile, and cores.
5. Select **Validate all configurations**, resolve all errors, and use
   **Save All**.
6. In **Run**, select **Snakemake Workflow** and start with **Dry run**.
7. Review the preflight report and dry-run job plan.
8. Select **Run**, complete browser authentication if requested, and monitor the
   Output and Warnings & Errors views.
9. Review the completion summary and full log.
10. Use **Results** to aggregate metrics and open generated layers on a map.

For one isolated processing step, select **Single Script**, choose the script,
provide its displayed inputs, review preflight, and run it. The user is
responsible for ensuring that its required upstream data already exists.

## What the interface does not change

The interface is a controller and editor around the existing project files. In
particular:

- it does not create a separate UI-only configuration;
- it does not make a Snakemake scenario override a technology scenario;
- it does not bypass dependencies when Snakemake determines that preparation is
  required;
- it does not treat a warning as a failed process; and
- it does not change the output naming between manual and Snakemake execution.

This shared-file design keeps terminal commands, manual script execution, and
UI-launched workflows compatible and reproducible.
