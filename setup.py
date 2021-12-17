#!/usr/bin/env python3

__version__ = "0.2.0"
__ghrepo = "https://github.com/2l47/TF2-docker"

import argparse
import configparser
import docker
from helpers import genpass, normalize_permissions, untar, unzip, waitForServer
import html
import json
import os
import pathlib
import re
import requests
import shutil
import subprocess
import urllib.parse
import urllib.request



# ======== Process initial container options ========

parser = argparse.ArgumentParser(
	description = f"TF2-docker container setup script, version {__version__}",
	formatter_class = argparse.ArgumentDefaultsHelpFormatter
)

# General container options
parser.add_argument("--profile-name", "-p", type=str, required=True, help="A profile name with custom configurations, files, and plugins.")
parser.add_argument("--region-name", "-r", type=str, required=True, help="Docker containers are created with names like \"tf2-default-dallas-1\". Provide a region, e.g. \"dallas\"")
parser.add_argument("--instance-number", "-i", type=int, required=True, help="Docker containers are created with names like \"tf2-default-dallas-1\". Provide an instance number, e.g. \"1\"")
parser.add_argument("--cpu-affinity", "-c", type=str, default="", help="The CPUs in which to allow container execution. e.g. \"0,1\" or \"0-3\"")

# Plugin-specific options
parser.add_argument("--with-sbpp", action="store_true", help="Attempts to install SourceBans++ using the configuration supplied in \"sbpp.ini\".")

# Behavioral options
parser.add_argument("--overwrite", "-o", action="store_true", help="Stops and removes any preexisting containers with the same name.")
parser.add_argument("--erase", "-e", action="store_true", help="Erases preexisting container data directories with the same name.")
parser.add_argument("--force-reuse", "-f", action="store_true", help="Forces reuse of existing container data directories. A bad idea due to repeated cfg appending.")
parser.add_argument("--skip-apt", "-s", action="store_true", help="Skips upgrading the base system and installing extra packages. Will cause issues with some profiles.")
parser.add_argument("--no-wait", "-n", action="store_true", help="Skips waiting for the server to come online after everything is completed.")

# Other options
parser.add_argument("--host-ip", type=str, help="Optional value that overrides the auto-detected host IP address.")

# Parse the command-line arguments and make sure they're sane
args = parser.parse_args()
assert args.region_name.isalpha() and args.region_name.islower()
assert args.instance_number > 0

# Define the container name based on the profile name, server region, and instance number
assert args.profile_name.isalpha() and args.profile_name.islower()
container_name = f"tf2-{args.profile_name}-{args.region_name}-{args.instance_number}"

# We use the host IP address to check if the server has been brought up later on
if not args.host_ip:
	args.host_ip = subprocess.check_output("hostname -I | cut -d ' ' -f 1", shell=True).decode().strip()
	print(f"Auto-detected your public IP address as {args.host_ip}. If this is incorrect, override the value with the --host-ip option.\n")


# ======== Prepare the container configuration ========

# Connect to the docker socket
client = docker.from_env()

# Make sure a container doesn't already exist with this name
print(f"Using container name {container_name}; checking for pre-existing containers...")
preexisting = client.containers.list(all=True, filters={"name": container_name})
descriptors = [f"{i}: {i.name}" for i in preexisting]
if descriptors:
	if not args.overwrite:
		raise SystemExit(f"ERROR: Found {len(preexisting)} pre-existing container(s) matching the name \"{container_name}\":\n\t{descriptors}\n\nYou may need to delete them or pick another identifier.")
	else:
		# "Overwrite" the container(s)
		print("WARNING: Overwriting preexisting containers!")
		for c in preexisting:
			if c.status == "running":
				print(f"Killing container \"{c.name}\" ({c})...")
				c.kill()
			print(f"Removing container \"{c.name}\" ({c})...")
			c.remove(v=True)
else:
	print("No conflictingly named containers found.")

# Set up a persistent data directory for the container
data_dir = pathlib.PosixPath(f"container-data/{container_name}")
if data_dir.exists() and args.erase:
	print("WARNING: Erasing existing container data!")
	shutil.rmtree(data_dir)
try:
	pathlib.Path.mkdir(data_dir, parents=True)
except FileExistsError:
	if not args.force_reuse:
		raise SystemExit("ERROR: A data directory for a container with this name already exists.\nSince there doesn't seem to be an associated container, you may wish to delete it.")

# Randomized passwords get stored here
try:
	os.mkdir("container-passwords")
except FileExistsError:
	pass

# Plugins get downloaded here
try:
	os.mkdir("downloads")
except FileExistsError:
	pass


# ======== Load and process configuration files ========

# Reads values from configuration files
config = configparser.ConfigParser()
# Preserve case-sensitive keys
config.optionxform = str
# Load default settings, passwords, tokens, keys, etc.
config.read("default-settings.ini")
config.read("settings.ini")
config.read("sample-credentials.ini")
config.read("credentials.ini")

# Load any overriding or additional settings from the selected profile, if any
if args.profile_name:
	config.read(f"profiles/{args.profile_name}/settings.ini")

# srcds configuration time
srcds = config["srcds"]
creds = config["credentials"]

# Check if we actually have a token first, though
if len(creds["SRCDS_LOGIN_TOKEN"]) != 32:
	print("\nWARNING: You have not entered a game server login token in credentials.ini (SRCDS_LOGIN_TOKEN).")
	print("Without one, your server might not display in the community server browser or be reachable.")
	print("You probably want to create one at: https://steamcommunity.com/dev/managegameservers")
	print("See sample-credentials.ini for instructions on how to store your credentials.")

# Check if the profile wants a random server/rcon password
for i in ["SRCDS_PW", "SRCDS_RCONPW"]:
	if srcds[i] == "random":
		srcds[i] = genpass()
		fname = f"container-passwords/{container_name}_{i}.txt"
		with open(fname, "w") as f:
			f.write(f"{srcds[i]}\n")
		print(f"\nThe {i} has been changed to: {srcds[i]}\nFor your convenience, it has been saved to {fname}.")

# Different SRCDS instances need different ports!
srcds["SRCDS_PORT"] = str(int(srcds["SRCDS_START_PORT"]) + args.instance_number - 1)
print(f"\nSRCDS port set to {srcds['SRCDS_PORT']}.")
srcds["SRCDS_TV_PORT"] = str(int(srcds["SRCDS_TV_START_PORT"]) + args.instance_number - 1)
print(f"SourceTV port set to {srcds['SRCDS_TV_PORT']}.")
# We use different key names in our credential configuration files for clarity
srcds["SRCDS_TOKEN"] = creds["SRCDS_LOGIN_TOKEN"]
srcds["SRCDS_WORKSHOP_AUTHKEY"] = creds["STEAM_WEB_API_KEY"]
# Construct an environment dict from our config for the docker image to use on its first run
env = dict(srcds.items())

# Adds the region name and instance number to the server hostname if enabled
if srcds.getboolean("append-identifier-to-hostname"):
	srcds["SRCDS_HOSTNAME"] = f"{srcds['SRCDS_HOSTNAME']} | {args.region_name} | {args.instance_number}"


# ======== Initialize the container ========

# Pull the docker image
print("\nPulling the docker image...")
client.images.pull("cm2network/tf2:sourcemod")

# Create the container
data_directory = pathlib.Path.resolve(pathlib.PosixPath(f"container-data/{container_name}"), strict=True)
container = client.containers.create("cm2network/tf2:sourcemod", cpuset_cpus=args.cpu_affinity, detach=True, environment=env, name=container_name, network_mode="host", volumes={data_directory: {"bind": "/home/steam/tf-dedicated/"}})

# Start the container
print("Starting the container...")
container.start()

# Now we need to do all the actual setup stuff.
print("Waiting for the base docker image to install the TF2 SRCDS with SourceMod before installing profile configurations, files, and plugins...\n")
ready_message = "Success! App '232250' already up to date."
logs = container.attach(stdout=True, stream=True)
for backlog in logs:
	lines = backlog.decode().split("\n")
	for l in lines:
		print(l)
	if ready_message in lines:
		break
print(f"\n{'=' * 8} SRCDS installed! {'=' * 8}")


# ======== Update the base system ========

if not args.skip_apt:
	print(f"\n{'=' * 8} Upgrading the base system and installing extra packages... {'=' * 8}")
	for command in ["apt update", "apt full-upgrade -y", "apt install net-tools procps vim -y", "apt autoremove --purge -y"]:
		exit_code, output = container.exec_run(command, user="root")
		print(f"{output.decode()}\n")
		assert exit_code == 0

# Go ahead and shutdown the server while we set things up.
print(f"{'=' * 8} Killing the container for server configuration... {'=' * 8}")
container.kill()


# ======== Define configuration helper functions ========

# Edit configuration options easily by replacing patterns
def edit(cfg, pattern, repl):
	assert not cfg.startswith(str(data_directory))
	assert not cfg.startswith("/")
	p = pathlib.Path(f"{data_directory}/{cfg}")
	p.write_text(re.sub(pattern, repl, p.read_text(), flags=re.M))


# ======== Configure the server ========

print(f"\n{'=' * 8} Starting configuration... {'=' * 8}")
# The first thing to do is make the configured server name persistent.
edit("tf/cfg/server.cfg", "^hostname.*", f"hostname {srcds['SRCDS_HOSTNAME']}")
# Same thing for the rcon password
edit("tf/cfg/server.cfg", "^rcon_password.*", f"rcon_password {srcds['SRCDS_RCONPW']}")

# Direct-copy and append files from the global profile and selected profile
for profile_name in ["global", args.profile_name]:
	print(f"\nApplying configurations from the \"{profile_name}\" profile...")

	# Dynamically copy profile data
	print(f"Direct-copying files...")
	profile_prefix = f"profiles/{profile_name}"
	copy_prefix = f"{profile_prefix}/direct-copy/"
	if os.path.isdir(copy_prefix):
		shutil.copytree(copy_prefix, f"{data_directory}/", dirs_exist_ok=True)

	# Append to files
	print("Appending profile files to container files...")
	p = pathlib.PosixPath(f"{profile_prefix}/append-to/")
	for f in p.glob("**/*"):
		if f.is_file():
			rel_path = f.relative_to(f"{profile_prefix}/append-to/")
			sv_f = pathlib.PosixPath(f"{data_directory}/{rel_path}")
			sv_f_data = sv_f.read_text() + "\n" + f.read_text()
			sv_f.write_text(sv_f_data)

# Execute any user scripts for the profile
for filename in os.listdir(f"profiles/{args.profile_name}/preinst_modules/"):
	if filename.endswith(".py"):
		module = filename.split(".py")[0]
		exec(f"from profiles.{args.profile_name}.preinst_modules.{module} import loader")
		loader(args.profile_name, args.region_name, args.instance_number, container)


# ======== Install server plugins ========

if config.has_section("plugins"):
	print(f"\n{'=' * 8} Installing plugins... {'=' * 8}")
	plugins = config["plugins"]

	# Deal with special keys first
	# TODO: RGL goes here or something... maybe a preinst-module would be better for fetching maps..?

	# Enable the specified plugins included with SourceMod but which are disabled by default
	plugins_to_enable = plugins.get("enable-plugins")
	if plugins_to_enable:
		plugins_to_enable = plugins_to_enable.split(",")
		repo = os.getcwd()
		os.chdir(f"{data_directory}/tf/addons/sourcemod/plugins/disabled/")
		for pname in plugins_to_enable:
			# Remove leading spaces from the plugin name
			pname = pname.strip()
			if pname == "":
				if len(plugins_to_enable) == 1:
					print("No plugins to enable...")
				else:
					print("WARNING: Extra comma in enable-plugins?")
				continue
			print(f"Enabling plugin: {pname}")
			s_fname = f"{pname}.smx"
			p = pathlib.PosixPath(s_fname)
			if p.exists():
				p.replace(f"../{s_fname}")
			else:
				print(f"WARNING: Path does not exist: {p}")
		os.chdir(repo)

	# Disable the specified plugins included with SourceMod
	plugins_to_disable = plugins.get("disable-plugins")
	if plugins_to_disable:
		plugins_to_disable = plugins_to_disable.split(",")
		repo = os.getcwd()
		os.chdir(f"{data_directory}/tf/addons/sourcemod/plugins/")
		for pname in plugins_to_disable:
			# Remove leading spaces from the plugin name
			pname = pname.strip()
			if pname == "":
				if len(plugins_to_disable) == 1:
					print("No plugins to disable...")
				else:
					print("WARNING: Extra comma in disable-plugins?")
				continue
			print(f"Disabling plugin: {pname}")
			s_fname = f"{pname}.smx"
			p = pathlib.PosixPath(s_fname)
			if p.exists():
				p.unlink()
			else:
				print(f"WARNING: Path does not exist: {p}")
		os.chdir(repo)

	# Load our plugin database.
	with open("plugins.json") as f:
		plugin_db = json.load(f)

	# Set the user agent for urllib.request.urlretrieve(), used for file downloads
	opener = urllib.request.build_opener()
	opener.addheaders = [("User-Agent", f"setup.py/{__version__} ({__ghrepo})")]
	urllib.request.install_opener(opener)

	# Now download and install the plugins requested.
	session = requests.Session()
	# Set the user agent for the session, used for requesting webpages
	session.headers.update({"User-Agent": f"setup.py/{__version__} ({__ghrepo})"})
	requested_plugins = plugins.get("requested-plugins")
	if requested_plugins:
		requested_plugins = requested_plugins.split(",")
		for pname in requested_plugins:
			# Remove leading spaces from the plugin name
			pname = pname.strip()
			if pname == "":
				if len(requested_plugins) == 1:
					print("No plugins requested...")
				else:
					print("WARNING: Extra comma in requested-plugins?")
				continue
			print(f"\nDownloading and installing plugin: {pname}")
			# Get the plugin entry
			p = plugin_db["plugins"][pname]
			# Directly download the plugin from the specified URL and install it as specified
			if "force_download" in p:
				print("\tDownloading and installing according to plugins.json...")

				# Grab plugin download configuration values
				url = p["force_download"]["url"]
				format = p['force_download']['format']
				assert format.startswith(".")
				strip_leading_dir = p["force_download"].get("strip_leading_dir")
				install_location = p["force_download"]["install_location"]

				# We're using this legacy urllib method because it lets us specify a destination filename easily
				dest_filename = f"downloads/{pname}{format}"
				urllib.request.urlretrieve(p["force_download"]["url"], dest_filename)

				# Handle installation
				if format == ".zip":
					unzip(dest_filename, f"container-data/{container_name}/{install_location}", strip_leading_dir=strip_leading_dir)
				else:
					# TODO
					print("TODO: Install the plugin as specified")
			# Otherwise, try to get a download link from the plugin's AlliedModders thread's webpage HTML
			else:
				print(f"\tAttempting to download the plugin from the AlliedModders forum thread ({p['thread_url']})...")
				response = session.get(p["thread_url"])
				content = response.content.decode("latin")
				# One of these ought to work at least some of the time
				# A. Try to get an attachment; we currently only look for a zip
				attachment_urls_escaped = re.findall(r'(?<=href=")attachment.php.*(?=")(?=.*zip)', content)
				if len(attachment_urls_escaped) > 1:
					error = f"\nERROR: Got {len(attachment_urls_escaped)} plugin download URLs (expected 1): {attachment_urls_escaped}"
					error += f"\nPlease create an issue at: {gh_repo}"
					raise SystemExit(error)
				elif len(attachment_urls_escaped) == 1:
					# Note that this variable is just in the singular form
					attachment_url_escaped = attachment_urls_escaped[0]
					print(f"\tGot escaped download URL from thread: {attachment_url_escaped}")
					attachment_url = html.unescape(attachment_url_escaped)
					print(f"\tGot download URL from thread: {attachment_url}")
					urllib.request.urlretrieve(f"https://forums.alliedmods.net/{attachment_url}", f"downloads/{pname}.zip")
					unzip(f"downloads/{pname}.zip", f"container-data/{container_name}/tf/")
				# B. No attachments found; try to get the plugin as compiled from source
				else:
					print("\tWARNING: No attachment URLs found, falling back to plugin compiler links...")
					plugin_compiler_urls = re.findall(r'(?<=href=")https://www.sourcemod.net/vbcompiler.php\?file_id=\d+', content)
					# Default selection
					compiler_selection = 0
					# User specified selection
					if "force_compiler_selection" in p:
						compiler_selection = p["force_compiler_selection"]
					# If the user doesn't specify and there's more than once choice, bail out
					elif len(plugin_compiler_urls) > 1:
						error = f"\nERROR: Found {len(plugin_compiler_urls)} plugin compiler URLs (expected 1): {plugin_compiler_urls}"
						error += "\nHint: You can specify an index to select in plugins.json with the field \"force_compiler_selection\"."
						raise SystemExit(error)
					# Try to retrieve the requested index
					try:
						# Note that this variable is just in the singular form
						plugin_compiler_url = plugin_compiler_urls[compiler_selection]
						print(f"\tGot plugin compiler URL from thread: {plugin_compiler_url}")
						urllib.request.urlretrieve(plugin_compiler_url, f"downloads/{pname}.smx")
					except IndexError:
						raise SystemExit(f"ERROR: Compiler list index selection ({compiler_selection}) out of range ({len(plugin_compiler_urls)})")


# ======== Install SourceBans++ ========

# If the user requested SourceBans++ installation, go ahead and attempt it.
if args.with_sbpp:
	# Make sure sbpp.ini exists. If it does, the user has run ./sbpp-installer.py, although that doesn't necessarily mean it was successful. Geronimo!
	assert config.read("sbpp.ini") == ["sbpp.ini"]
	print("\nAttempting SourceBans++ installation...")
	# Figure out the latest version of SBPP.
	response = session.get("https://github.com/sbpp/sourcebans-pp/releases")
	# We need the plugin only...
	versions = re.findall(r'(?<=href=")/sbpp/sourcebans-pp/releases/download/[0-9.]+/sourcebans-pp-[0-9.]+.plugin-only.tar.gz(?=")', response.content.decode(), flags=re.M)
	latest = versions[0]
	download_url = f"https://github.com/{latest}"
	# Download it.
	dest_filename = "downloads/sourcebans-pp-latest.plugin-only.tar.gz"
	urllib.request.urlretrieve(download_url, dest_filename)
	# Extract.
	extracted = untar(dest_filename, expect_root_regex="addons")
	# Normalize permissions yes
	normalize_permissions(extracted)
	# Now copy it in and then delete the extracted files
	shutil.copytree(extracted, f"container-data/{container_name}/tf/", dirs_exist_ok=True)
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

print(f"\n{'=' * 8} Plugin installation complete, starting the container... {'=' * 8}")
container.start()


# ======== Reconfigure server plugins ========

# The last thing we have to do is reconfigure plugins.
# Config files will have been generated for newly-installed plugins once the server is online.
print("\nWaiting for the server to come online so we can reconfigure any plugins...")
waitForServer(args.host_ip, int(srcds["SRCDS_PORT"]))

print(f"\n{'=' * 8} Reconfiguring plugins... {'=' * 8}\n")
p = pathlib.PosixPath(f"{profile_prefix}/reconfigure/")
for f in p.glob("**/*"):
	if f.is_file():
		# Load the file as-is
		rel_path = f.relative_to(f"{profile_prefix}/reconfigure/")
		sv_f = pathlib.PosixPath(f"{data_directory}/{rel_path}")
		sv_f_as_is = sv_f.read_text()

		# Conjure and write new contents
		sv_f_data = sv_f_as_is
		for line in f.read_text().split("\n"):
			if line == "" or line.startswith("//"):
				continue
			print(f"Processing line from {f}: {line}")
			key = line.split(" ")[0]
			print(f"Got key \"{key}\", substituting matching lines")
			sv_f_data = re.sub(f"^{key}.*", line, sv_f_data, flags=re.M)
		sv_f.write_text(sv_f_data)


# ======== Yeet ========

print(f"\n{'=' * 8} Configuration complete, restarting the container... {'=' * 8}\n")
container.restart()

if not args.no_wait:
	waitForServer(args.host_ip, int(srcds["SRCDS_PORT"]))
