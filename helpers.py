#!/usr/bin/env python3

import pathlib
import re
import subprocess
import tarfile
from xkcdpass import xkcd_password as xp



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
