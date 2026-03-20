# Instructions for Contributing

We welcome anyone interested in contributing to this project, be it with new ideas, suggestions, by filing bug reports or contributing code.

## Code Contributions

### Style Guidelines

The project uses [`pre-commit`](https://pre-commit.com/) with [Ruff](https://docs.astral.sh/ruff/) to enforce consistent code style.

You can install `pre-commit` via pip or conda:

```bash
pip install pre-commit
# or
conda install -c conda-forge pre-commit
```

To activate it so it runs automatically before every commit, run once:

```bash
pre-commit install
```

This will automatically check the changes which are staged before you commit them.

To manually run it on all files, use:

```bash
pre-commit run --all
```

**Ruff**

Currently, the only tool run by `pre-commit` is [Ruff](https://docs.astral.sh/ruff/), which serves as both our linter and formatter. It combines common tools like Flake8 and Black. Besides `pre-commit`, you can also run it via your CLI (see [Ruff installation](https://docs.astral.sh/ruff/installation/)) or IDE (e.g. the [VSCode plugin](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)).

Ruff can be installed manually:

```bash
pip install ruff
```

To run the linter:

```bash
ruff check . --fix
```

This checks all files and gives hints on what to improve. The `--fix` flag automatically fixes some issues; others need to be fixed manually.

To run the formatter:

```bash
ruff format .
```

This formats all files immediately, similar to Black.

!!! note
    It is not mandatory to use Ruff or `pre-commit` locally — we also run them in our CI/CD pipeline. But it is highly recommended to make everyone's life easier.

## Documentation Contributions

The documentation is built with [MkDocs](https://www.mkdocs.org/) using the [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) theme.

To preview the documentation locally, install the required packages:

```bash
pip install mkdocs mkdocs-material
```

Then serve the docs:

```bash
mkdocs serve
```

This compiles the documentation and makes it available at `http://127.0.0.1:8000`.

## Reporting Issues

If you encounter a bug or have a feature request, please [open an issue](https://github.com/DEA-GE/LAVA/issues) on GitHub. When reporting a bug, include:

- A short description of the problem
- Steps to reproduce it
- The relevant error message or output
- Your operating system and Python environment details
