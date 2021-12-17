#!/usr/bin/env python3

import a2s
import os
import pathlib
import re
import shutil
import socket
import subprocess
import tarfile
import time
from xkcdpass import xkcd_password as xp
import zipfile



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
					f.chmod(types[extension])
					break


# Returns the answer to a question as a boolean
def prompt(text):
	answer = input(text)
	return answer.lower() in ["y", "yes", "yeah"]


# Basic function to replace patterns in files
def sed(filename, pattern, repl):
	p = pathlib.Path(filename)
	p.write_text(re.sub(pattern, repl, p.read_text(), flags=re.M))


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
		# Print debug info
		for filename in zip.infolist():
			print(f"info: {filename}")
		for filename in zip.namelist():
			print(f"name: {filename}")

		# Get the archive root
		if strip_leading_dir:
			root_info = zip.infolist()[0]
			root = root_info.filename
			assert root.endswith("/")
			print(f"Got zip root directory: {root}")

		# Make sure temp is empty
		try:
			shutil.rmtree("temp")
		except FileNotFoundError:
			pass
		os.mkdir("temp")

		# Extract to temporary location
		zip.extractall("temp/")

		if strip_leading_dir:
			print("Stripping leading dir from zip archive contents")
			shutil.copytree(f"temp/{root}", where, dirs_exist_ok=True)
		else:
			print("Not stripping leading dir from zip archive contents")
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
