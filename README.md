# datasette-upload-dbs

[![PyPI](https://img.shields.io/pypi/v/datasette-upload-dbs.svg)](https://pypi.org/project/datasette-upload-dbs/)
[![Changelog](https://img.shields.io/github/v/release/simonw/datasette-upload-dbs?include_prereleases&label=changelog)](https://github.com/simonw/datasette-upload-dbs/releases)
[![Tests](https://github.com/simonw/datasette-upload-dbs/workflows/Test/badge.svg)](https://github.com/simonw/datasette-upload-dbs/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/simonw/datasette-upload-dbs/blob/main/LICENSE)

Upload SQLite database files to Datasette

## Installation

Install this plugin in the same environment as Datasette.

    datasette install datasette-upload-dbs

## Usage

Usage instructions go here.

## Development

To set up this plugin locally, first checkout the code. Then create a new virtual environment:

    cd datasette-upload-dbs
    python3 -m venv venv
    source venv/bin/activate

Now install the dependencies and test dependencies:

    pip install -e '.[test]'

To run the tests:

    pytest
