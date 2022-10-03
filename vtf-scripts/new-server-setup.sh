#!/usr/bin/env bash

set -ex

export NEW_VTF_HOST="region.variety.tf"
scp ./settings.ini ./credentials.ini ./sbpp.ini $NEW_VTF_HOST:~/TF2-docker/
scp ./profiles/variety/direct-copy/*-webhook-url.txt $NEW_VTF_HOST:~/TF2-docker/profiles/variety/direct-copy/
scp ./profiles/variety/direct-copy/tf/cfg/sbpp_discord.cfg $NEW_VTF_HOST:~/TF2-docker/profiles/variety/direct-copy/tf/cfg/
