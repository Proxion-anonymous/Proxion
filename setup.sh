#!/bin/sh

python3 -m pip install poetry
poetry install --without dev
poetry run solc-select install all
poetry shell
