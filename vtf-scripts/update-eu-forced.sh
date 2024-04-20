#!/usr/bin/env bash

set -ex

git fetch
git reset --hard origin/dev

# Timezone for Variety.TF EU servers
export TIMEZONE="Europe/Luxembourg"

time ./setup.py -p variety -r frankfurt -i 1 -o -e
time ./setup.py -p variety -r frankfurt -i 2 -o -e
