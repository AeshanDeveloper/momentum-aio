#!/bin/bash

git fetch origin
git switch mdev
git pull
scripts/run.bat
