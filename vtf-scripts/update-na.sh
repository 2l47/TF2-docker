#!/usr/bin/env bash

set -ex


# Timezone for Variety.TF NA servers
export TIMEZONE="America/Chicago"

time ./setup.py -p variety -r dallas -i 1 -o -e
time ./setup.py -p variety -r dallas -i 2 -o -e
