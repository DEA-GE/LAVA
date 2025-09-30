Troubleshooting
===============

Even with a well-configured setup, you may encounter issues when running the LAVA_china pipeline. This section lists some common problems and how to resolve them. If your issue is not listed here, consider checking the log files or error messages for clues, and ensure your configuration and environment are set up as per the instructions.

OGR Errors (Vector/Raster Data Handling)
----------------------------------------

**Symptom:** The pipeline halts with an error message related to OGR or GDAL (the libraries used for geospatial data I/O). You might see messages like "OGR Error", "GDAL exception", or an inability to read/write a certain file format.

**Common causes & solutions:**

- **Missing or misconfigured GDAL/OGR:** Ensure that the conda environment includes GDAL/OGR and it is properly activated. (The provided environment should have it, but if you see `ModuleNotFoundError` for `osgeo` or `ogr`, the environment might not be active or installed correctly.)
- **Unsupported file format or driver issues:** Check that your input files are in a supported format. For example, if you're using a KML or another less common format, GDAL may need an extra driver. Stick to common formats like Shapefile or GeoJSON for vector data. If you must use another format, ensure GDAL supports it and the appropriate driver is available.
- **Incorrect file paths:** An "unable to open file" error often means the path in your config is wrong or the file is missing. Double-check that the path to your shapefiles or other data in the YAML config is correct relative to the project directory (or provide an absolute path).
- **Data corruption or projection issues:** Sometimes an OGR error can indicate a corrupted file or a projection mismatch. Try opening the file in a GIS software to ensure it’s valid. If it’s a projection issue (e.g., the pipeline expects WGS84 but the data is in a local projection), either reproject your data or update the config/processing to handle that projection.

After addressing the above, try running the pipeline again. OGR/GDAL errors are usually resolved by fixing environment issues or correcting input data problems.

YAML Decoding Errors (Configuration)
-----------------------------------

**Symptom:** Running `snakemake` fails immediately with a YAML parse error, or the pipeline cannot read the config file. Error messages may include phrases like "YAMLError", "could not find expected ':'", or "mapping values are not allowed here".

**Common causes & solutions:**

- **Syntax errors in YAML:** YAML is sensitive to formatting. Even a single mis-placed character can break it. Check the indicated line number in the error (if provided). Look for:

    - Missing colon or value (every key should be followed by a colon and a space, then the value).
    - Inconsistent indentation (use spaces consistently, no tabs).
    - Unclosed quotes or brackets.
    - A stray `-` that isn't part of a proper list.
- **Special characters not quoted:** If your values include characters like `:`, `#`, or `\`, they might be interpreted as YAML syntax. For example, a Windows path `C:\data\file` or a string with a colon like `http://example` need to be quoted. Ensure file paths and URLs in the config are enclosed in quotes.
- **Copy-paste formatting issues:** If you copied config content from another source (like an email or Word doc), invisible characters or wrong indentation might have been introduced. Re-type those lines or use a plain text editor to fix formatting.
- **Blank lines or encoding issues:** Ensure there are no odd characters in the file. Save the config in UTF-8 encoding. Avoid tabs (use 2 spaces for indentation).

After fixing the YAML file, run a dry run (`snakemake -n`) to confirm that the configuration is now loading properly. It can be helpful to use an online YAML validator or a linter to check your config file if you keep encountering issues.

OpenEO Memory Overflow Errors
-----------------------------

**Symptom:** When processing data through OpenEO, you receive errors indicating memory overflow or out-of-memory conditions. This might happen during large data retrievals or computations (for instance, processing a very large region at high resolution or a long time series). The error might come from the OpenEO backend and look like a failure to complete the job due to memory limits.

**Common causes & solutions:**

- **Request too large:** The most common reason is that the area or time range you are requesting data for is too large to handle in one go. Try reducing the spatial extent (process a smaller region or tile the region into sub-regions) or shorten the time range and process in batches. You can then merge the results if needed.
- **High resolution data on large extent:** If you're requesting data at full resolution for a very large area (e.g., high-res imagery for all of China at once), it's likely to overwhelm memory. Consider using a lower resolution or summary product if appropriate, or split the request (as above).
- **OpenEO backend limits:** Some OpenEO providers have default memory and processing time limits for jobs. If you consistently hit a memory error on the backend, check if the pipeline or OpenEO client allows specifying job options. For example, some OpenEO clients let you set `job_options={"max_memory": ...}` or similar. If the LAVA_china config has settings for OpenEO jobs (memory, tile size, etc.), try adjusting them to be more modest.
- **Local environment (if applicable):** In cases where OpenEO operations are executed locally or intermediate results are stored locally, ensure your machine has enough memory. Closing other applications or increasing swap space can help avoid local memory errors.
- **Monitor and iterative approach:** It might be necessary to iteratively approach large tasks: process data in chunks, verify each chunk, and clean up intermediate data as you go to free memory.

In summary, memory overflow issues can often be mitigated by processing less data at a time or by tuning the job parameters. If the problem persists even after trying the above, you may need to consult OpenEO platform documentation or support to see if higher resource allocations are possible for your jobs, or if an alternative approach (like downloading raw data and processing offline in smaller pieces) is more feasible.

