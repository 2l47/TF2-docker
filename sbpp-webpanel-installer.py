#!/usr/bin/env python3

# This script installs and configures MariaDB and the SourceBans++ WebPanel.
# Database credentials and other info will be written to "sbpp.ini".
# The installer must be run as root, e.g. with "sudo".

# You will first be prompted for an admin username and password for SBPP, as well as your Steam ID and email address.
# The installer does NOT save your admin credentials - only the randomly generated credentials used for accessing the database are saved.
# If you forget your SBPP admin password, you will have to manually replace the password hash for your user in the sbpp_admins table, or log in with Steam.

import configparser
import getpass
from helpers import execute, genpass, normalize_permissions, prompt, sed
import os
import pathlib
import re
import requests
import shutil
from sid import getSteamID
import stat
import subprocess
import tarfile
import urllib



# Make sure we're running as root before we try to do anything
if os.geteuid() != 0:
	raise SystemExit("ERROR: The installer must be run as root.")


print("\n\n======== Part 1: SBPP Administrator Account Information ========")

# SourceBans++ needs an administrator account set up to complete the installation later on.
print("\nSourceBans++ uses accounts to manage bans, so we need some information for the administrator account.")
print("You will now be prompted for the SourceBans++ administrator's username, password, Steam ID (any format), and email address.")

sbpp_admin_user = input("\nPlease enter the SourceBans++ administrator's username: ")

sbpp_admin_pass = getpass.getpass("\nPlease enter the SourceBans++ administrator's password: ")
if sbpp_admin_pass != getpass.getpass("Please confirm the password: "):
	raise SystemExit("\nERROR: The password you entered did not match.")

# The latest release of SourceBans++ at the time of writing (09/23/2021) is version 1.6.3, released way back in 2018.
# Version 1.7 will reportedly use a library to support built-in SteamID conversion (https://github.com/sbpp/sourcebans-pp/issues/535), but for some reason, a new official release has not been distributed on GitHub since 2018.
# Because it's less work to fetch the latest release, "since those come bundled with all requiered [sic] code dependencies and pre-compiled sourcemod plugins", we're stuck with version 1.6.3 until a new release is put out.
# SBPP version 1.6.3 expects a regular Steam ID (e.g. STEAM_1:1:1234), so I wrote a quick Steam ID conversion module (sid.py) to handle conversion from any format.
print("\nThe Steam ID of your Steam account is required. Any of the following formats will work:")
print("""\tSteam ID (STEAM_1:1:418668784)
	Steam ID3 (U:1:837337569)
	Steam32 ID (837337569)
	Steam64 ID (76561198797603297)
	Vanity URL (Sydney_2l47)""")

print("\nIf in doubt, your \"Friend Code\" is actually just your Steam32 ID.")
print("Go to the \"Friends\" menu in Steam -> \"Add a Friend...\") to get it. Example: 837337569")

print("\nSince you can log in to SourceBans++ with your Steam account, you MUST use your actual account to prevent random people from gaining access to the SourceBans++ WebPanel.")
print("Entering a value of 0 *should* make it impossible to login via Steam, but only because a Valve employee hasn't created an account with this Steam32 ID yet.")
print("Previous employees have used values as low as 1 and up, but it's still possible for them to do something funny here.")

sbpp_admin_steam = getSteamID(input("\nPlease enter the Steam ID of the SourceBans++ administrator's Steam account: "))
# SBPP actually wants an incorrect universe value of zero for logins to work so :/
universe_x, id_number_y, account_number_z = re.match(r"STEAM_(\d):(\d):(\d+)", sbpp_admin_steam).groups()
sbpp_admin_steam = f"STEAM_0:{id_number_y}:{account_number_z}"

sbpp_admin_email = input("\nPlease enter the SourceBans++ administrator's email address: ")

print(f"\nSBPP Admin Username: {sbpp_admin_user}\nSBPP Admin Steam ID: {sbpp_admin_steam}\nSBPP Admin Email: {sbpp_admin_email}")
assert prompt("Do these values look okay? ")


print("\n\n======== Part 2: Host IP and SourceBans++ WebPanel URL ========")

# Where are we?
host_ip = subprocess.check_output("hostname -I | cut -d ' ' -f 1", shell=True).decode().strip()
if not prompt(f"\nI auto-detected your public IP address as {host_ip}. Is this correct? "):
	host_ip = input("Please enter your public IP address: ")
print(f"Host IP address noted as {host_ip}.")

# Figure out the webpanel URL
webpanel_url = f"http://{host_ip}/sbpp"
if prompt(f"\nThe webpanel URL is currently set to {webpanel_url}. Do you want to change it (e.g. to https://example.com/sbpp)? "):
	webpanel_url = input("Please enter the webpanel URL, including the http:// or https:// prefix and the /sbpp suffix: ")
print(f"The webpanel URL will be set to {webpanel_url}.")


print("\n\n======== Part 3: MariaDB Bind Address ========")

bind_address = "172.17.0.1"
print("\nIf you have multiple physical servers running TF2-docker (e.g. to serve different regions), you may want them all to connect to the same database running on this server.")
print("If so, you will need to expose the database to the public internet (or alternatively, use tunneling or VLANs for the connection).")
print("Although the database requires authentication, directly exposing it to the public internet carries significant security risks, so only do this if you know what you're doing.")
print("(One might consider implementing an IP whitelist and dropping all other traffic to the database port.)")

# Ask if the user is running a server cluster
if prompt("\nMariaDB is currently set to bind to 172.17.0.1, which should only allow local TF2-docker servers to connect to the database. If you are running a server cluster, this should be your server's public IP address or otherwise instead. Do you want to change the bind address? "):
	# Alright, let's figure out the bind address for MariaDB
	if prompt(f"Your public IP address was noted as {host_ip}. Do you want to bind MariaDB to this address? "):
		bind_address = host_ip
	else:
		bind_address = input("Please enter the IP address for MariaDB to bind to: ")
print(f"The MariaDB bind address will be set to {bind_address}.")


print("\n\n======== Part 4: Save and Load Configurations ========")

# Write out the configuration for setup.py to pass on to containers with SBPP enabled.
config = configparser.ConfigParser()
config.add_section("sbpp")
sbpp = config["sbpp"]
sbpp["db-host"] = bind_address
sbpp["db-port"] = "3306"
sbpp["db-user"] = "sbpp"
sbpp["db-pass"] = genpass()
sbpp["db-name"] = "tf2_docker"
sbpp["db-table-prefix"] = "sbpp"
sbpp["webpanel-url"] = webpanel_url
with open("sbpp.ini", "w") as f:
	config.write(f)

# Now load credentials, and make sure we have a Steam Web API key (required for SBPP).
config.read("sample-credentials.ini")
config.read("credentials.ini")
steam_web_api_key = config["credentials"]["STEAM_WEB_API_KEY"]
if len(steam_web_api_key) != 32:
	raise SystemExit("\nERROR: A Steam Web API key is required for SourceBans++.\nPlease generate one at: https://steamcommunity.com/dev/apikey\nSee sample-credentials.ini for instructions on how to store your credentials.")


print("\n\n======== Part 5: MariaDB Installation ========")

# Install MariaDB. If you needed to, you could pick an alternative mirror from: https://downloads.mariadb.org/mariadb/repositories/
print("\nInstalling MariaDB...")
execute([
	"apt update",
	"apt install mariadb-server -y"
])
mariadb_conf = "/etc/mysql/mariadb.conf.d/50-server.cnf"


print("\n\n======== Part 6: MariaDB Setup ========")

# Set up MariaDB now, using the configuration we generated
print("\nSetting up MariaDB...")

# Create a database named tf2_docker. SBPP will use tables in it prefixed by the configured "db-table-prefix".
# Other plugins should also use this database (with their own tables).
execute(f"mysql --execute \"CREATE DATABASE IF NOT EXISTS {sbpp['db-name']};\"")

# Grant full permissions on all of the SBPP tables to the SBPP "db-user".
# These table names are hardcoded to avoid giving the SBPP db user privileges on other tables in the tf2_docker database (other plugins).
sbpp_tables = ["admins", "admins_servers_groups", "banlog", "bans", "comments", "comms", "demos", "groups", "log", "mods", "overrides", "protests", "servers", "servers_groups", "settings", "srvgroups", "srvgroups_overrides", "submissions"]
for table in sbpp_tables:
	execute(f"mysql --execute \"GRANT ALL PRIVILEGES ON tf2_docker.{sbpp['db-table-prefix']}_{table} TO '{sbpp['db-user']}'@'%' IDENTIFIED BY '{sbpp['db-pass']}';\"")
# Commit privilege changes
execute("mysql --execute \"FLUSH PRIVILEGES;\"")

# Set the bind address for mariadb
sed(mariadb_conf, r"^bind-address.*", f"bind-address = {bind_address}")

# Restart mariadb so it uses the new bind address
execute("systemctl restart mariadb")

print("\nSuccessfully configured mariadb.")


print("\n\n======== Part 7: Webserver and SourceBans++ WebPanel Installation ========")

print("\nInstalling webserver packages...")
execute("apt install apache2 libapache2-mod-php php-gmp php-pdo-mysql php-xml -y")

print("Downloading SourceBans++ WebPanel...")
# Figure out the latest version of SBPP.
response = requests.get("https://github.com/sbpp/sourcebans-pp/releases")
# We need the webpanel only...
versions = re.findall(r'(?<=href=")/sbpp/sourcebans-pp/releases/download/[0-9.]+/sourcebans-pp-[0-9.]+.webpanel-only.tar.gz(?=")', response.content.decode(), flags=re.M)
latest = versions[0]
download_url = f"https://github.com/{latest}"
# Download it.
dest_filename = "sourcebans-pp-latest.webpanel-only.tar.gz"
urllib.request.urlretrieve(download_url, dest_filename)

print("Installing SourceBans++ WebPanel...")
# Prepare the SBPP webpanel directory
sbpp_inst = pathlib.PosixPath(f"/var/www/html/sbpp/")
try:
	pathlib.Path.mkdir(sbpp_inst)
except FileExistsError:
	pass
# Make it traversable, readable, writable; traversable/readble
sbpp_inst.chmod(0o744)
# Extract the webpanel archive
tar = tarfile.open(dest_filename, mode="r:gz")
tar.extractall("/var/www/html/sbpp/")
# Delete the downloaded archive
pathlib.PosixPath(dest_filename).unlink()
# Set basic permissions manually since SBPP doesn't distribute tarfiles with normal permissions...
normalize_permissions(sbpp_inst, dir_permissions=0o555, file_permissions=0o444, type_permissions={".php": 0o544})
# Now manually set quickstart-requested permissions, for the same reason...
# I don't know why they say to make images 644 when, being directories, they need to be 744 :/
dir_permissions = {"config.php": 0o644, "demos": 0o644, "themes_c": 0o774, "images/games": 0o744, "images/maps": 0o744}
for path, mode in dir_permissions.items():
	p = pathlib.PosixPath(f"/var/www/html/sbpp/{path}")
	if not p.exists():
		if path != "config.php":
			raise SystemExit(f"ERROR: Unexpectedly missing path: {path}")
		continue
	p.chmod(mode)
	for f in p.glob("**/*"):
		f.chmod(mode)
# Now set the owner to www-data so SBPP can write stuff here
execute("chown www-data -R /var/www/html/sbpp")

print("\nSuccessfully installed the SourceBans++ WebPanel.")


print("\n\n======== Part 8: SourceBans++ WebPanel Configuration ========\n")

# Among the last things we need to do are creating SBPP's config.php and declaring an administrator in the tf2_docker database's sbpp_admins table.
# There might be more to it than that, but the installation PHP code already does all this for us.
# So, we're just going to send the HTTP POST requests needed to complete the setup ourselves, using the information we've already collected.
session = requests.Session()
data = {
	"server": sbpp["db-host"],
	"port": sbpp["db-port"],
	"username": sbpp["db-user"],
	"password": sbpp["db-pass"],
	"database": sbpp["db-name"],
	"prefix": sbpp["db-table-prefix"],
	"apikey": steam_web_api_key,
	"sb-wp-url": sbpp["webpanel-url"],
	"sb-email": "",
	"button": "Ok",
	"postd": "1"
}
# After accepting the license, we HTTP GET /index.php?step=2
# Webpanel details are entered on this step page; by POSTing it this time we're just now accepting the license
session.post("http://127.0.0.1/sbpp/install/index.php?step=2", data=data)

# Remove these two keys
data.pop("button")
data.pop("postd")
# Now POST step 3 and it'll actually accept the details we entered
# Then it'll do some sanity checks and return a status page
session.post("http://127.0.0.1/sbpp/install/index.php?step=3", data=data)

# This POST basically accepts that everything looked good on the check page
# Then it'll create the database tables
session.post("http://127.0.0.1/sbpp/install/index.php?step=4", data=data)

data["charset"] = "utf8mb4"
# This POST accepts that the tables were created successfully
# and returns a page prompting us for admin setup
session.post("http://127.0.0.1/sbpp/install/index.php?step=5", data=data)

data["uname"] = sbpp_admin_user
data["pass1"] = sbpp_admin_pass
data["pass2"] = sbpp_admin_pass
data["steam"] = sbpp_admin_steam
data["email"] = sbpp_admin_email
data["postd"] = "1"
# This POST submits the admin account info
# and returns a page with a configuration sample for addons/sourcemod/configs/databases.cfg
session.post("http://127.0.0.1/sbpp/install/index.php?step=5", data=data)

# Clear the "installation success" header that normally publicly displays on the webpanel dashboard until you change it
execute(f"mysql --execute \"UPDATE {sbpp['db-name']}.sbpp_settings SET value='' where setting='dash.intro.title';\"")
execute(f"mysql --execute \"UPDATE {sbpp['db-name']}.sbpp_settings SET value='' where setting='dash.intro.text';\"")

# Delete the install and updater directories and we're good to go, assuming everything was successful, which it should have been.
p = pathlib.PosixPath("/var/www/html/sbpp/install/")
shutil.rmtree(p)
p = pathlib.PosixPath("/var/www/html/sbpp/updater/")
shutil.rmtree(p)


print("\n\n======== Successfully configured the SourceBans++ WebPanel! ========")
