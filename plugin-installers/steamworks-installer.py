#!/usr/bin/env python3

# Installs Steamworks


header("Attempting Steamworks installation...", newlines=(2, 1))

# The SteamWorks downloads page
base_url = "https://users.alliedmods.net/~kyles/builds/SteamWorks/"

# Figure out the latest version of SteamWorks.
response = session.get(base_url)
versions = re.findall(r'(?<=href=")SteamWorks-git\d+-linux\.tar\.gz', response.content.decode(), flags=re.M)
latest = versions[0]

# Download it.
download_url = f"{base_url}/{latest}"
dest_filename = "downloads/steamworks-latest.tar.gz"
urllib.request.urlretrieve(download_url, dest_filename)

# Extract.
extracted = untar(dest_filename, expect_root_regex="addons")

# Now copy it in and then delete the extracted files
shutil.copytree(extracted, f"container-data/{container_name}/tf/addons/", dirs_exist_ok=True)
shutil.rmtree(extracted)

print("Success!")
