# PowerShell wrapper to run Snakemake with proper PYTHONPATH
# This script sets PYTHONPATH to the project root (parent directory of snakemake folder)
# Usage: .\run_snakemake.ps1 --snakefile snakemake/Snakefile --cores 4 --resources openeo_req=1

# Get the directory where this script is located (snakemake folder)
$SnakemakeDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition

# Get the project root (parent of snakemake folder)
$ProjectRoot = Split-Path -Parent -Path $SnakemakeDir

# Set PYTHONPATH to the project root
$env:PYTHONPATH = $ProjectRoot

# Run snakemake with all passed arguments
snakemake @args
