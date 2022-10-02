#!/usr/bin/env python3

# Installs the SourceBans++ server plugin

from helpers import normalize_permissions


header("Attempting SourceBans++ installation...", newlines=(2, 1))

# Make sure sbpp.ini exists. If it does, the user has run ./sbpp-installer.py, although that doesn't necessarily mean it was successful. Geronimo!
assert config.read("sbpp.ini") == ["sbpp.ini"]

# Retrieve the latest release of SBPP.
response = session.get("https://api.github.com/repos/sbpp/sourcebans-pp/releases/latest")
latest = response.json()
# We need the plugin only...
plugin_only = re.compile("sourcebans-pp-[0-9.]+.plugin-only.tar.gz")
download_url = None
for asset in latest["assets"]:
	if plugin_only.fullmatch(asset["name"]):
		download_url = asset["browser_download_url"]
		break
assert download_url is not None
# Download it.
dest_filename = "downloads/sourcebans-pp-latest.plugin-only.tar.gz"
urllib.request.urlretrieve(download_url, dest_filename)

# Extract.
extracted = untar(dest_filename, expect_root_regex="addons")

# Normalize permissions yes
normalize_permissions(extracted)

# Now copy it in and then delete the extracted files
shutil.copytree(extracted, f"container-data/{container_name}/tf/addons/", dirs_exist_ok=True)
shutil.rmtree(extracted)

# Insert the SourceBans++ database configuration from sbpp.ini
# This formatting is as good as it's gonna get
# By the way, the default database connect timeout appears to be 60 seconds if you leave it set to 0
# (https://github.com/alliedmodders/sourcemod/blob/1fbe5e/extensions/mysql/mysql/MyDriver.cpp#L101)
# So yeah we use 10 seconds, that's plenty generous
db_cfg = (
	'\n	"sourcebans"\n'
	'	{\n'
	'		"driver"	"default"\n'
	f'		"host"		"{config["sbpp"]["db-host"]}"\n'
	f'		"database"	"{config["sbpp"]["db-name"]}"\n'
	f'		"user"		"{config["sbpp"]["db-user"]}"\n'
	f'		"pass"		"{config["sbpp"]["db-pass"]}"\n'
	'		"timeout"	"10"\n'
	f'		"port"		"{config["sbpp"]["db-port"]}"\n'
	'	}\n'
	'}'
)
edit("tf/addons/sourcemod/configs/databases.cfg", r'}\n*\Z', db_cfg)

print("Success!")
