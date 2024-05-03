from setuptools import setup
import os

VERSION = "0.3.2"


def get_long_description():
    with open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md"),
        encoding="utf8",
    ) as fp:
        return fp.read()


setup(
    name="datasette-upload-dbs",
    description="Upload SQLite database files to Datasette",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    author="Simon Willison",
    url="https://github.com/simonw/datasette-upload-dbs",
    project_urls={
        "Issues": "https://github.com/simonw/datasette-upload-dbs/issues",
        "CI": "https://github.com/simonw/datasette-upload-dbs/actions",
        "Changelog": "https://github.com/simonw/datasette-upload-dbs/releases",
    },
    license="Apache License, Version 2.0",
    classifiers=[
        "Framework :: Datasette",
        "License :: OSI Approved :: Apache Software License",
    ],
    version=VERSION,
    packages=["datasette_upload_dbs"],
    entry_points={"datasette": ["upload_dbs = datasette_upload_dbs"]},
    install_requires=["datasette", "starlette"],
    extras_require={"test": ["pytest", "pytest-asyncio"]},
    package_data={"datasette_upload_dbs": ["templates/*"]},
    python_requires=">=3.7",
)
