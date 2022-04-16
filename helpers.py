#!/usr/bin/env python3

import a2s
import os
import pathlib
import re
from shared import _version, _repo
import shutil
import socket
import subprocess
import tarfile
import time
from xkcdpass import xkcd_password as xp
import zipfile



# Outputs an error message and links to the GitHub repo if what happened may be an issue, then exits
def error(message, is_issue):
	if is_issue:
		message += f"\n\nPlease create an issue at: {_repo}"
	raise SystemExit(message)


# Runs a list of commands, logging what's being done, the output, and any errors
def execute(commands):
	if type(commands) == str:
		commands = [commands]
	for cmd in commands:
		try:
			print(f"Running command: {cmd}")
			output = subprocess.check_output(cmd, shell=True).decode()
			if output:
				print(output)
		except subprocess.CalledProcessError as ex:
			print(ex.output.decode())
			raise


# Generates a four-word passphrase
def genpass():
	return xp.generate_xkcdpassword(xp.generate_wordlist(wordfile=xp.locate_wordfile()), numwords=4, delimiter="-")


# Prints a header
def header(text, newlines=(0, 0)):
	nl_prefix = "\n" * newlines[0]
	nl_suffix = "\n" * newlines[1]
	print(f"{nl_prefix}{'=' * 8} {text} {'=' * 8}{nl_suffix}")


# Normalizes permissions recursively on a directory
def normalize_permissions(path_obj, dir_permissions=0o755, file_permissions=0o644, type_permissions={}):
	assert type(path_obj) == pathlib.PosixPath
	for f in path_obj.glob("**/*"):
		if f.is_dir():
			f.chmod(dir_permissions)
		elif f.is_file():
			f.chmod(file_permissions)
			for extension in type_permissions:
				if f.name.endswith(extension):
					f.chmod(type_permissions[extension])
					break


# Returns the answer to a question as a boolean
def prompt(text):
	answer = input(text)
	return answer.lower() in ["y", "yes", "yeah"]


# Basic function to replace patterns in files
def sed(filename, pattern, repl):
	p = pathlib.Path(filename)
	p.write_text(re.sub(pattern, repl, p.read_text(), flags=re.M))


# Selects a download URL for a plugin
def select_plugin_url(plugin_entry, download_urls, type):
	selection = None
	# If a manual selection has not been specified, expect only one option
	expected_length = 1
	actual_length = len(download_urls)
	# If a specific attachment has been declared to use, try to use it
	if type == "attachment" and "force_attachment_selection" in plugin_entry:
		selection, expected_length = plugin_entry["force_attachment_selection"]
	elif type == "compiler" and "force_compiler_selection" in plugin_entry:
		selection, expected_length = plugin_entry["force_compiler_selection"]
	else:
		selection = 0
	# If there are no options, let the main program handle it, since we fall back to compiler links before bailing out
	if len(download_urls) == 0:
		raise ValueError("No download URLs found!")
	# Handle out of bounds manual selection
	if selection < 0 or selection >= actual_length:
		error(f"\nERROR: Plugin {type} download URL index selection ({selection}) is out of range ({actual_length})!", is_issue=True)
	# We expect exactly one option by default. Otherwise, if the number of options changes, the index may not be correct.
	elif len(download_urls) != expected_length:
		message = f"\nERROR: Got {len(download_urls)} plugin {type} download URLs (expected {expected_length}): {download_urls}"
		message += f"\nPlugin thread URL: {plugin_entry['thread_url']}"
		if len(download_urls) > 1:
			message += f"\nNote: You can specify a specific plugin {type} URL index to select by setting the field \"force_{type}_selection\" in plugins.json."
			message += f"\nThe format should be: \"force_{type}_selection\": [selected_index, number_of_URLs]"
		error(message, is_issue=True)
	return download_urls[selection]


# Extracts the given tarfile and returns the path to the extracted files
def untar(filename, mode="r:gz", expect_root_regex=None):
	print(f"Opening tarfile \"{filename}\" in mode \"{mode}\" for unarchiving...")
	tar = tarfile.open(filename, mode)
	members = tar.getmembers()
	root = members[0].name
	print(f"Archive root: {root}")
	if expect_root_regex:
		assert re.fullmatch(expect_root_regex, root)
	tar.extractall("downloads/")
	return pathlib.PosixPath(f"downloads/{root}/")


# Unzips the zipfile somewhere
def unzip(filename, where, strip_leading_dir=False):
	with zipfile.ZipFile(filename, "r") as zip:
		# Get the archive root
		if strip_leading_dir:
			root_info = zip.infolist()[0]
			root = root_info.filename
			try:
				assert root.endswith("/")
			except AssertionError:
				print("Failed to determine zip archive root directory! Hierarchy follows:")
				# Print debug info
				for filename in zip.infolist():
					print(f"info: {filename}")
				for filename in zip.namelist():
					print(f"name: {filename}")
				raise
			print(f"\tGot zip root directory: {root}")

		# Make sure temp is empty
		try:
			shutil.rmtree("temp")
		except FileNotFoundError:
			pass
		os.mkdir("temp")

		# Extract to temporary location
		zip.extractall("temp/")

		if strip_leading_dir:
			print("\tStripping leading dir from zip archive contents")
			shutil.copytree(f"temp/{root}", where, dirs_exist_ok=True)
		else:
			print("\tNot stripping leading dir from zip archive contents")
			# Just copy all of the zipfile's contents in
			shutil.copytree("temp/", where, dirs_exist_ok=True)


# Waits for the given server to come online
def waitForServer(ip, port):
	while True:
		try:
			r = a2s.info((ip, port))
			print("Server is online!\n")
			break
		except socket.timeout:
			time.sleep(1)
