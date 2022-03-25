#!/usr/bin/env python3

# We determine the rotation to use from the day of the year and the container's instance number (stored by the profile's crontab module as the offset value).
# If this is the first time running, or rotations.json has been updated, we regenerate tf/subscribed_file_ids.txt
# Lastly, we write out the mapcycle.txt for the current rotation.

# Side note: subscribed_file_ids.txt might actually be completely unnecessary for TF2.

__version__ = "0.0.3"
__ghrepo = "https://github.com/2l47/TF2-docker"

from datetime import date
import hashlib
import json
import os



# Load the map rotations
with open("rotations.json") as f:
	rotations = json.load(f)

# How many rotations are configured?
num_rotations = len(rotations)

# The offset for instance number 1 is zero, and so on.
with open("offset.dat") as f:
	offset = int(f.read())

# Today's day out of the year, 1 to 366.
day_of_year = date.today().timetuple().tm_yday
# Today's rotation index, e.g. 3.
tr_index = (day_of_year + offset) % num_rotations
# Today's rotation ID, e.g. R3.
tr_id = list(rotations.keys())[tr_index]
# Today's rotation.
tr = rotations[tr_id]

# Debug info
print(f"Rotation offset: {offset}")
print(f"DOY: {day_of_year}")
print(f"Today's rotation (index {tr_index}; ID {tr_id}):")
import pprint
pprint.pprint(tr)
print()


# This function writes a mapcycle.txt from the given rotation
def write_mapcycle(rotation):
	print("Writing mapcycle.txt")
	with open("tf/cfg/mapcycle.txt", "a") as mapcycle:
		mapcycle.truncate(0)
		for map_name in rotation:
			map = rotation[map_name]
			if map["type"] == "stock":
				mapcycle.write(f"{map_name}\n")
			elif map["type"] == "workshop":
				workshop_id = map["workshop_id"]
				mapcycle.write(f"workshop/{workshop_id}\n")
			else:
				raise SystemExit(f"Unknown map type: {map['type']}")


# Check if rotations.json has been updated; if so, update workshop IDs
previous_hash = None
# Get the hash of rotations.json as of the previous run (if any)
if os.path.exists("rotations.json.md5"):
	with open("rotations.json.md5") as f:
		previous_hash = f.read().strip()
# Get the current hash
with open("rotations.json", "rb") as f:
	current_hash = hashlib.md5(f.read()).hexdigest()
# Write the current hash
with open("rotations.json.md5", "w") as md5_f:
	md5_f.write(current_hash)

# We're going to recreate subscribed_file_ids.txt
if previous_hash != current_hash:
	print(f"Previous hash ({previous_hash}) differs from current hash ({current_hash}).")
	print("Updating subscribed_file_ids.txt...")

	# SRCDS needs to know what workshop files to subscribe to
	subscribed_file_ids = set()

	# Get workshop map IDs and download necessary maps from all rotations
	for rotation_id in rotations:
		print(f"Processing rotation ID {rotation_id}...")
		maps = rotations[rotation_id]
		for map_name in maps:
			map = maps[map_name]
			print(f"\t{map['type']} map {map_name}")
			if map["type"] == "workshop":
				workshop_id = map["workshop_id"]
				subscribed_file_ids.add(workshop_id)

	# Okay Cool Now Write Out The Up-To-Date "subscribed_file_ids.txt"
	print(f"Writing {len(subscribed_file_ids)} workshop IDs to subscribed_file_ids.txt")
	with open("tf/cfg/subscribed_file_ids.txt", "w") as f:
		f.write("\n".join(subscribed_file_ids))
# As far as we know, rotations.json hasn't been updated.
else:
	print("rotations.json doesn't appear to have been updated; not rewriting subscribed_file_ids.txt")


# Just update the mapcycle now
# Fortunately this is very easy since I already wrote the function for it above ^:)
write_mapcycle(tr)
