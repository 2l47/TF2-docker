#!/usr/bin/env bash

# Usage: Just run ./install-dependencies.sh


# If the script was called with sudo, we'll want to give the calling user permissions rather than the user we're executing as
DOCKER_USER=$USER
if [[ -n $SUDO_USER ]]; then
	if [[ $SUDO_USER == "root" ]]; then
		: # Insert condescending comment here
	fi
	echo -e "You didn't need to run this with sudo, but whatever. It's handled, so long as your username is in fact $SUDO_USER.\n"
	DOCKER_USER=$SUDO_USER
else
	if [[ $EUID -eq 0 ]]; then
		echo "Looks like you're logged in as root. Everything will probably still work (I haven't tried), but there may be security risks."
		echo "You should really consider creating a non-root user account with sudo privileges instead."
		read -p "Press enter to continue..."
	fi
fi

# Install prerequisites
sudo apt update
sudo apt install docker-compose xkcdpass -y
sudo apt install python3-pip
sudo pip3 install --target /usr/lib/python3/dist-packages python-a2s

# Give the calling user access to docker
sudo usermod --append --groups docker $DOCKER_USER

echo -e "\nTF2-docker dependencies installed (probably). You may need to fully log out and back in before your docker permissions will take effect."
