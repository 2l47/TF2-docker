#!/usr/bin/env python3

from helpers import assert_exec, header
import os



# Called by setup.py
def loader(profile_name, region_name, instance_number, container):
	header("Installing varietyd...", newlines=(2, 0))
	print(f"\n(daemon_setup.py) Hello, world! Profile name {profile_name}, region {region_name}, instance number {instance_number}.")

	# Where is the data for this container stored?
	container_data = f"container-data/tf2-{profile_name}-{region_name}-{instance_number}"

	# varietyd includes the region and instance number in webhook messages
	with open(f"{container_data}/container-info.dat", "w") as f:
		f.write(f"{region_name}-{instance_number}\n")

	# autorotate.py needs to know the regional offset when it runs
	with open(f"{container_data}/offset.dat", "w") as f:
		# The rotation offset should be zero for the first instance in a region
		offset = instance_number - 1
		# On variety.tf, we have multiple servers in a region offset further from one another to increase variety
		if profile_name == "variety":
			offset += 3
		f.write(f"{offset}\n")

	# varietyd needs to know what timezone to use for the scheduler
	# Try to get the timezone from the environment variable, otherwise fallback to UTC
	try:
		tz_name = os.environ["TIMEZONE"]
	except KeyError:
		tz_name = "Etc/UTC"
	with open(f"{container_data}/scheduler_timezone.txt", "w") as f:
		f.write(tz_name)

	# Why not use a cron job?
	# 1 - The docker image doesn't have systemd, so we'd have to spawn the cron daemon in the entry script
	# 2 - Debian's version of cron doesn't supply the -m flag which would have let us handle job errors with an external script
	# By default, cron sends output to the mail spool
	# Forwarding to an email address would require automating the installation of an entire mail server, and still set up MX records, etc. manually
	# 3 - I don't want to compile and install cronie as a replacement, and still fall to point 1

	# Instead, we'll just spawn our own daemon (varietyd) to handle map rotation in the entry script.
	# It sends any autorotate.py output via a Discord webhook and can be extended to support more functionality in the future if desired.

	# Now then, since we're not running inside the container, we don't have direct filesystem access to the main volume.
	# Therefore, we need exec access to install the daemon. Fortunately, we've already been passed a container object ^:)
	# Just gotta start the container again, first.
	container.start()

	# varietyd requires the following python modules
	assert_exec(container, "root", "apt install python3-pip -y")
	assert_exec(container, "steam", "pip3 install python-daemon pytz requests scheduler setproctitle")

	# The daemon's already been copied into /home/steam/tf-dedicated/
	# Just edit the entry script to spawn it
	assert_exec(container, "steam", "sed -i 's_\#!/bin/bash_&\\n\\n./tf-dedicated/varietyd\\n_' entry.sh")

	# Shut it back off
	container.kill()
