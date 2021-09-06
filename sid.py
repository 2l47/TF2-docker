#!/usr/bin/env python3

# Module to convert various Steam ID formats to the standard Steam ID textual format ("STEAM_X:Y:Z").

# The Steam API defines universe values differently from the wiki. With respect to values 0 and 5, I went with the API definitions.
# https://developer.valvesoftware.com/wiki/SteamID#Universes_Available_for_Steam_Accounts
# https://partner.steamgames.com/doc/api/steam_api#EUniverse

import re
import requests
import xml.etree.ElementTree



# Returns a Steam ID from a Steam32 ID and the given universe
def from_universe(steam32_id, universe_x):
	# Sanity check
	assert 0 < universe_x < 5
	# Get the Y and Z components from the Steam32 ID
	id_number_y = 0 if steam32_id % 2 == 0 else 1
	account_number_z = int((steam32_id - id_number_y) / 2)
	return f"STEAM_{universe_x}:{id_number_y}:{account_number_z}"


# By default, this function will assume that any Steam32 ID is a Steam account in the "Public" universe.
# When assume_user is False, the function will prompt the user for a universe number.
def getSteamID(sid, assume_user=True, debug=False):
	if type(sid) != str:
		raise ValueError(f"Expected a Steam ID format contained within a string, but got type {type(sid)}.")
	# Check for different Steam ID formats
	# Regular Steam ID
	if sid.startswith("STEAM_"):
		return sid
	# Steam ID3
	elif re.fullmatch(r"U:\d:\d+", sid):
		_, universe_x, steam32_id = sid.split(":")
		return from_universe(int(steam32_id), int(universe_x))
	# Is this a Steam32 or Steam64 ID?
	elif sid.isdigit():
		sid = int(sid)
		# Check for a Steam64 ID by comparing against the maximum value of a Steam32 ID
		if sid > 0xFFFFFFFF:
			# This is a Steam64 ID, we can get the Steam32 ID and universe with bitwise operators
			steam32_id = sid & 0xFFFFFFFF
			universe_x = sid >> 56
			return from_universe(steam32_id, universe_x)
		# This is just a Steam 32 ID. The universe is unknown.
		# Unless you're Valve, the universe is probably "Public" (1).
		else:
			# By default, we assume the account is in the "Public" universe.
			universe_x = 1
			# If assume_user is False, we prompt for the universe instead.
			if not assume_user:
				universe_x = int(input("Enter your Steam account's Universe ID. If you aren't Valve, enter 1 here: "))
			return from_universe(sid, universe_x)
	# The provided Steam ID has non-digit characters. It's probably a vanity URL.
	else:
		if debug:
			print("This looks like a vanity URL; fetching Steam Community profile to get the Steam64 ID...")
		r = requests.get(f"https://steamcommunity.com/id/{sid}?xml=1")
		content = r.content.decode()
		element = xml.etree.ElementTree.fromstring(content)
		steam64_id = element.find("steamID64").text
		if debug:
			print(f"Got Steam64 ID: {steam64_id}")
		assert steam64_id.isdigit()
		assert int(steam64_id) > 0xFFFFFFFF
		return getSteamID(steam64_id, assume_user=False)
