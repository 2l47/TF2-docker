# TF2-docker


## About

TF2-docker enables you to easily deploy TF2 servers in docker containers using predefined or custom configuration profiles.


## Basic usage

Clone the repository where you want to host your server(s):
```
git clone https://github.com/2l47/TF2-docker
cd TF2-docker
```

Install required dependencies: `./install-dependencies.sh`

Run the TF2 docker container setup script to see available options: `./setup.py --help`

* If you want to use the SourceBans++ plugin, you will need to run `./sbpp-installer.py` first to set up a database and webserver before creating a container.
	* If you have multiple physical servers running TF2-docker (e.g. to serve different regions), you may want them all to connect to the same database, which is running on a single server.
	* To do this, you can simply copy `sbpp.ini` from the server you run `./sbpp-installer.py` on to the other servers in order to share access to the database.


## Setup Examples

1. This example will set up a basic TF2 server using the "default" profile, which specifies that random crits will be disabled, spray delay time will be set to zero, and voice command ("Medic!") delays will be reduced to a minimum.

`./setup.py --region syrupland --instance-number 1`

2. This example will set up a TF2 server suitable for playing a competitive [RGL.gg](https://rgl.gg/) match. (Note: the supplied profile is incomplete at the moment)

`./setup.py --region dallas --instance-number 1 --profile-name rgl`


## Some Quick Notes

1. Docker creates "volumes" for containers, but they don't get deleted when you delete the container they're attached to. If you've been working on a custom profile and testing it repeatedly, you may wish to run `docker volume prune -f` to delete unused volumes and free up that disk space.

2. TF2-docker includes a "global" profile. Anything in here gets applied before any other profile is loaded.
	* By default, this just enables SourceTV, which allows anyone to connect to your server on a different port (by default, STV is on port 27020 whereas the server runs on port 27015) and freely spectate without wasting any of the server's (default) 24 player slots.
	* As far as I know, SourceTV is completely safe. If you wanted to disable it anyways, you could just put "tv_enable 0" in `profiles/yourcustomprofile/append-to/tf/cfg/server.cfg`, and the value would be overridden.


## Creating custom profiles

So you want to roll your own server, huh? No problem - I designed TF2-docker around this idea.


### Changing default server settings

Let's learn!
1. Create a new folder under profiles with a name like "custom". Profile names must only contain lowercase letters.
2. Create a `settings.ini` file like the following example. Values in here will override the values in the `default-settings.ini` file.
```
[srcds]
# My custom server name
SRCDS_HOSTNAME = Pink Fluffy Unicorns Dancing On Rainbows
# My server has a password now! Only players with the password can join.
SRCDS_PASSWORD = Could you make me some breakfast?
# Use a predetermined rcon password instead of a randomly generated four-word passphrase
SRCDS_RCONPW = You underestimate the power of the octave jump.
```

Note: When "SRCDS_RCONPW" is set to "random" (the default), a randomly generated four-word passphrase (such as ["correct-horse-battery-staple"](https://xkcd.com/936/)) is used and saved to `container-rcon-passwords/your-container-name_SRCDS_RCONPW.txt`. In this example, we opt to use a static rcon password instead.


### Creating custom configurations

For examples, look at the "default" profile. It copies the files `mapcycle.txt` and `motd.txt` into the server's `cfg` folder using the `direct-copy` folder, and appends some options to the `server.cfg` using the `append-to` folder.


#### Creating/replacing files in the container upon installation

In your profile, make a folder named `direct-copy`. All of the folders and files here will be copied directly into the server. If you've manually downloaded some obscure plugin, you can just add it in there.


#### Appending to files in the container upon installation

In your profile, make a folder named `append-to`. Any text in these files will be added to the end of the respective files on the server.


#### Editing files in the container upon installation

I'll implement this later if I really need to.
