#!/usr/bin/env bash

# Usage: Just run ./install-dependencies.sh


# If the script was called with sudo, we'll want to give the calling user permissions rather than the user we're executing as
DOCKER_USER=$USER
if [[ -n $SUDO_USER ]]; then
	echo -e "You didn't need to run this with sudo since it's used in the script, but it's handled, so long as the user that will be managing TF2 docker containers is in fact $SUDO_USER.\n"
	DOCKER_USER=$SUDO_USER
else
	if [[ $EUID -eq 0 ]]; then
		echo "Looks like you're logged in as root. It might work (I haven't tried), but there may be security risks."
		echo "You should really consider creating a non-root user account with sudo privileges instead."
		read -p "Press enter to continue..."
	fi
fi

# Install prerequisites
sudo apt update
sudo apt install docker-compose python3-pip xkcdpass -y
sudo pip3 install --target /usr/lib/python3/dist-packages python-a2s

# Give the calling user access to docker
sudo adduser $DOCKER_USER docker

echo -e "\nTF2-docker dependencies installed (probably). You may need to fully log out and back in before your docker permissions will take effect."
