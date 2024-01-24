#!/usr/bin/env python3

import argparse
import configparser
import docker
from helpers import assert_exec, error, genpass, header, select_plugin_url, str_to_list, untar, unzip, waitForServer
import html
import json
import os
import pathlib
import re
import requests
from shared import _version, _repo
import shutil
import subprocess
import urllib.parse
import urllib.request



# ======== Process initial container options ========

parser = argparse.ArgumentParser(
	description = f"TF2-docker container setup script, version {_version}",
	formatter_class = argparse.ArgumentDefaultsHelpFormatter
)

# General container options
parser.add_argument("--profile-name", "-p", type=str, required=True, help="A profile name with custom configurations, files, and plugins.")
parser.add_argument("--region-name", "-r", type=str, required=True, help="Docker containers are created with names like \"tf2-default-dallas-1\". Provide a region, e.g. \"dallas\"")
parser.add_argument("--instance-number", "-i", type=int, required=True, help="Docker containers are created with names like \"tf2-default-dallas-1\". Provide an instance number, e.g. \"1\"")
parser.add_argument("--cpu-affinity", "-c", type=str, default="", help="The CPUs in which to allow container execution. e.g. \"0,1\" or \"0-3\"")

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
	print(f"Auto-detected your IP address as {args.host_ip}. If this is incorrect, override the value with the --host-ip option.\n")


# ======== Prepare the container configuration ========

# Connect to the docker socket
client = docker.from_env()

# Make sure a container doesn't already exist with this name
print(f"Using container name {container_name}; checking for pre-existing containers...")
preexisting = client.containers.list(all=True, filters={"name": container_name})
descriptors = [f"{i}: {i.name}" for i in preexisting]
if descriptors:
	if not args.overwrite:
		message = f"ERROR: Found {len(preexisting)} pre-existing container(s) matching the name \"{container_name}\":\n"
		message += f"\t{descriptors}\n\n"
		message += "You may need to delete them or pick another identifier."
		error(message, is_issue=False)
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
		message = "ERROR: A data directory for a container with this name already exists."
		message += "\nSince there doesn't seem to be an associated container, you may wish to delete it."
		error(message, is_issue=False)

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
config.read(f"profiles/{args.profile_name}/settings.ini")
config.read(f"profiles/{args.profile_name}/credentials.ini")

# srcds configuration time
srcds = config["srcds"]
creds = config["credentials"]

# Check if we actually have a token first, though
gameserver_login_token = ""
try:
	section_name = f"region:{args.region_name}"
	tokens = str_to_list(config[section_name].get("SRCDS_LOGIN_TOKENS"))
	gameserver_login_token = tokens[args.instance_number - 1]
	if gameserver_login_token == "":
		print(f"\nWARNING: You have not entered a gameserver login token in credentials.ini (SRCDS_LOGIN_TOKENS) under the [{section_name}] section.\n" \
			"Without one, your server might not display in the community server browser, be reachable, or be able to communicate with the item server.\n" \
			"You probably want to create one at: https://steamcommunity.com/dev/managegameservers\n" \
			"See sample-credentials.ini for instructions on how to store your credentials.")
	elif len(gameserver_login_token) != 32:
		error(f"\nInvalid gameserver login token for instance number {args.instance_number} of region {args.region_name}: {gameserver_login_token}", is_issue=False)
except KeyError:
	print(f"\nWARNING: You have not defined any gameserver login tokens in credentials.ini for the {args.region_name} region.")
except IndexError:
	error(f"\nA gameserver login token is not present for instance number {args.instance_number} of region {args.region_name}!", is_issue=False)

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
srcds["SRCDS_TOKEN"] = gameserver_login_token
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

# Allow users with a UID/GID other than 1000 to use bind mounts successfully without file permissions or bindfs nonsense
UID, GID = os.getuid(), os.getgid()
if UID != 1000 or GID != 1000:
	# Adjust the entry script to make it wait while we change the steam user's UID/GID
	assert_exec(container, "steam", "sed -i 's_\#!/bin/bash_&\\nsleep 15_' entry.sh")
	# Restart the container
	container.restart(timeout=0)
	# Change the steam user's UID
	assert_exec(container, "root", f"usermod -u {UID} steam")
	# Change the ID of the steam group (also updates the steam user's GID)
	assert_exec(container, "root", f"groupmod -g {GID} steam")
	# Correct file permissions
	assert_exec(container, "root", "chown -R steam:steam /home/steam/ /tmp/dumps/")
	# Restore the entry script
	assert_exec(container, "steam", "sed -i '/sleep 15/d' entry.sh")
	# Restart the container again
	container.restart(timeout=0)

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
header("SRCDS installed!", newlines=(1, 0))


# ======== Update the base system ========

if not args.skip_apt:
	header("Upgrading the base system and installing extra packages...", newlines=(1, 0))
	for command in ["apt update", "apt full-upgrade -y", "apt install net-tools procps vim -y", "apt autoremove --purge -y"]:
		exit_code, output = container.exec_run(command, user="root")
		print(f"{output.decode()}\n")
		assert exit_code == 0

# Go ahead and shutdown the server while we set things up.
header("Killing the container for server configuration...")
container.kill()


# ======== Define configuration helper functions ========

# Edit configuration options easily by replacing patterns
def edit(cfg, pattern, repl):
	assert not cfg.startswith(str(data_directory))
	assert not cfg.startswith("/")
	p = pathlib.Path(f"{data_directory}/{cfg}")
	p.write_text(re.sub(pattern, repl, p.read_text(), flags=re.M))


# ======== Configure the server ========

header("Starting configuration...", newlines=(1, 0))
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
if os.path.isdir(f"profiles/{args.profile_name}/preinst_modules/"):
	for filename in os.listdir(f"profiles/{args.profile_name}/preinst_modules/"):
		if filename.endswith(".py"):
			module = filename.split(".py")[0]
			exec(f"from profiles.{args.profile_name}.preinst_modules.{module} import loader")
			loader(args.profile_name, args.region_name, args.instance_number, container)


# ======== Install server plugins ========

def handle_custom_installation(cust_inst):
	filename = cust_inst["file_to_exec"]
	with open(f"plugin-installers/{filename}") as f:
		exec(f.read())
	if "function_to_call" in cust_inst:
		func_name = cust_inst["function_to_call"]
		arg_str = ""
		if "function_arguments" in cust_inst:
			arg_str = cust_inst["function_arguments"]
		exec(f"{func_name}({arg_str})")

post_installation_plugins = []

if config.has_section("plugins"):
	header("Installing plugins...", newlines=(0, 1))
	plugins = config["plugins"]

	# Deal with special keys first
	# TODO: RGL goes here or something... maybe a preinst-module would be better for fetching maps..?

	# Enable the specified plugins included with SourceMod but which are disabled by default
	plugins_to_enable = str_to_list(plugins.get("enable-plugins"))
	if plugins_to_enable:
		repo = os.getcwd()
		os.chdir(f"{data_directory}/tf/addons/sourcemod/plugins/disabled/")
		for pname in plugins_to_enable:
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
	plugins_to_disable = str_to_list(plugins.get("disable-plugins"))
	if plugins_to_disable:
		repo = os.getcwd()
		os.chdir(f"{data_directory}/tf/addons/sourcemod/plugins/")
		for pname in plugins_to_disable:
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
	opener.addheaders = [("User-Agent", f"setup.py/{_version} ({_repo})")]
	urllib.request.install_opener(opener)

	# Now download and install the plugins requested.
	session = requests.Session()
	# Set the user agent for the session, used for requesting webpages
	session.headers.update({"User-Agent": f"setup.py/{_version} ({_repo})"})
	requested_plugins = str_to_list(plugins.get("requested-plugins"))
	if requested_plugins:
		for pname in requested_plugins:
			if pname == "":
				if len(requested_plugins) == 1:
					print("No plugins requested...")
				else:
					print("WARNING: Extra comma in requested-plugins?")
				continue
			# Handle plugins with optional features
			to_process = [pname]
			features_start = pname.find("[")
			if features_start != -1:
				base = pname[:features_start]
				feature_names = pname[features_start + 1:-1].split("&")
				print(f"\n{base} requested with features: {', '.join(feature_names)}")
				to_process = {base}
				# Plugin requirements
				if "requires" in plugin_db["plugins"][base]:
					for requirement in plugin_db["plugins"][base]["requires"]:
						to_process.add(requirement)
				# Enabled plugin feature requirements
				for fname in feature_names:
					for f_requirement in plugin_db["plugins"][base]["optional_features"][fname]["requires"]:
						to_process.add(f_requirement)
				print(f"Plugins to fetch: {', '.join(to_process)}")
			for pname in to_process:
				print(f"\nDownloading and installing plugin: {pname}")
				# Get the plugin entry
				p = plugin_db["plugins"][pname]
				# For plugins downloaded from attachments and plugin compiler links.
				extract_to = f"container-data/{container_name}/tf/"
				# Overridden by the force_extract_to parameter.
				if "force_extract_to" in p:
					extract_to = f"container-data/{container_name}/{p['force_extract_to']}"
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
					elif format == ".tar.gz":
						# Extract.
						extracted = untar(dest_filename)

						# Now copy it in and then delete the extracted files
						shutil.copytree(extracted, f"container-data/{container_name}/{install_location}", dirs_exist_ok=True)
						shutil.rmtree(extracted)
					elif format == ".smx":
						try:
							# Literally just move it into the server
							shutil.move(dest_filename, f"container-data/{container_name}/{install_location}")
						except shutil.Error:
							# Probably alreadys exists due to --force-reuse
							# Might as well do a lazy check that this is the case
							assert args.force_reuse
					else:
						error("ERROR: Unknown plugin download extension: {format}", is_issue=True)
				elif "custom_install" in p:
					cust_inst = p["custom_install"]
					# Defer plugin configuration scripts that rely on autogenerated configs
					if "post_installation" in cust_inst:
						if cust_inst["post_installation"]:
							print(f"Deferring installation of {pname}...")
							post_installation_plugins.append(cust_inst)
							continue
					handle_custom_installation(cust_inst)
				# Otherwise, try to get a download link from the plugin's AlliedModders thread's webpage HTML
				else:
					print(f"\tAttempting to download the plugin from the AlliedModders forum thread ({p['thread_url']})...")
					response = session.get(p["thread_url"])
					content = response.content.decode("latin")
					# Option A: Try to get an attachment; currently, we only look for a zip
					attachment_urls_escaped = re.findall(r'(?<=href=")attachment.php.*(?=")(?=.*zip)', content)
					try:
						# Note that this variable is just in the singular form
						attachment_url_escaped = select_plugin_url(p, attachment_urls_escaped, type="attachment")
						print(f"\tGot (escaped) plugin attachment URL from thread: {attachment_url_escaped}")
						attachment_url = html.unescape(attachment_url_escaped)
						print(f"\tGot plugin attachment URL from thread: {attachment_url}")
						urllib.request.urlretrieve(f"https://forums.alliedmods.net/{attachment_url}", f"downloads/{pname}.zip")
						unzip(f"downloads/{pname}.zip", extract_to)
					# Option B: No attachments found; try to get the plugin as compiled from source
					except ValueError as ex:
						print(ex)
						print("\tWARNING: No attachment URLs found, falling back to plugin compiler links...")
						plugin_compiler_urls = re.findall(r'(?<=href=")https://www.sourcemod.net/vbcompiler.php\?file_id=\d+', content)
						try:
							# Note that this variable is just in the singular form
							plugin_compiler_url = select_plugin_url(p, plugin_compiler_urls, type="compiler")
							print(f"\tGot plugin compiler URL from thread: {plugin_compiler_url}")
							# Download it directly into the server
							urllib.request.urlretrieve(plugin_compiler_url, f"container-data/{container_name}/tf/addons/sourcemod/plugins/{pname}.smx")
						except ValueError:
							# No plugin compiler links found, raise and exit
							raise


header("Plugin installation complete, starting the container...", newlines=(2, 0))
container.start()


# ======== Reconfigure server plugins ========

# The last thing we have to do is reconfigure plugins.
# Config files will have been generated for newly-installed plugins once the server is online.
print("\nWaiting for the server to come online so we can reconfigure any plugins...")
waitForServer(args.host_ip, int(srcds["SRCDS_PORT"]))

header("Processing deferred installations...", newlines=(1, 1))
for cust_inst in post_installation_plugins:
	handle_custom_installation(cust_inst)

header("Reconfiguring plugins...", newlines=(1, 1))
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

header("Configuration complete, restarting the container...", newlines=(2, 1))
container.restart()

if not args.no_wait:
	waitForServer(args.host_ip, int(srcds["SRCDS_PORT"]))
