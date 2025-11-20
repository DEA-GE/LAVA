project = "LAVA"
author = "m-dandrea, jome1"
release = "0.1"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
html_theme = "sphinx_rtd_theme"

root_doc = "index"     # (or master_doc = "index")

# Optional; create docs/_static or comment this out
html_static_path = ["_static"]
html_css_files = ["custom.css"]