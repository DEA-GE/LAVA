# Configuration file for the Sphinx documentation builder.

project = 'LAVA_china'
author = 'm-dandrea'
release = '0.1'

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
]

templates_path = ['_templates']
exclude_patterns = []

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']