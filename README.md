# TF2-docker


## About

TF2-docker enables you to easily deploy TF2 servers in docker containers using predefined or custom configuration profiles.


## Basic usage

Clone the repository where you want to host your server(s):
```
git clone https://gitlab.com/2l47/TF2-docker
cd TF2-docker
```

Install required dependencies: `./install-dependencies.sh`

Run the TF2 docker container setup script to see available options: `./setup.py --help`

* If you want to use the SourceBans++ plugin, you will need to run `./sbpp-installer.py` first to set up a database and webserver before creating a container.
	* If you have multiple physical servers running TF2-docker (e.g. to serve different regions), you may want them all to connect to the same database, which is running on a single server.
	* To do this, you can simply copy `sbpp.ini` from the server you run `./sbpp-installer.py` on to the other servers in order to share access to the database.


## Setup Examples

1. This example will set up a basic TF2 server using the "example" profile, which specifies that random crits will be disabled, spray delay time will be set to zero, and voice command ("Medic!") delays will be reduced to a minimum.

`./setup.py --region syrupland --instance-number 1 --profile-name example`

2. This example will set up a TF2 server suitable for playing a competitive [RGL.gg](https://rgl.gg/) match. (Note: the supplied profile is incomplete at the moment)

`./setup.py --region dallas --instance-number 1 --profile-name rgl`


## Some Quick Notes

1. Docker creates "volumes" for containers, but they don't get deleted when you delete the container they're attached to. If you've been working on a custom profile and testing it repeatedly, you may wish to run `docker volume prune -f` to delete unused volumes and free up that disk space.

2. TF2-docker includes a "global" profile. Anything in here gets applied before any other profile is loaded.
	* By default, this just enables SourceTV, which allows anyone to connect to your server on a different port (normally, STV is on port 27020 when the server game port is 27015) and freely spectate without wasting any of the server's 24 player slots.
		* TF2-docker provides the configuration options SRCDS_START_PORT and SRCDS_TV_START_PORT, which are set to 27015 and 28015, respectively, in `default-settings.ini` to avoid conflict between multiple server instances.
		* SRCDS_MAXPLAYERS is also set to 25 to provide SourceTV with its player slot.
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
SRCDS_PW = Could you make me some breakfast?
# Use a predetermined rcon password instead of a randomly generated four-word passphrase
SRCDS_RCONPW = You underestimate the power of the octave jump.
```

Note: When "SRCDS_RCONPW" is set to "random" (the default), a randomly generated four-word passphrase (such as ["correct-horse-battery-staple"](https://xkcd.com/936/)) is used and saved to `container-rcon-passwords/your-container-name_SRCDS_RCONPW.txt`. In this example, we opt to use a static rcon password instead.

Note 2: If you intend to publish a profile, you should store passwords in the profile's credentials.ini instead (using the same format). For a tv_password, set it in `profiles/yourcustomprofile/direct-copy/tf/cfg/tv_password.cfg` and append "exec tv_password" to your `server.cfg`.


### Creating custom configurations

For examples, look at the "example" profile. It copies the file `motd.txt` into the server's `cfg` folder using the `direct-copy` folder, and appends some options to the `server.cfg` using the `append-to` folder.


#### Creating/replacing files in the container upon installation

In your profile, make a folder named `direct-copy`. All of the folders and files here will be copied directly into the server. If you've manually downloaded some obscure plugin, you can just add it in there.


#### Appending to files in the container upon installation

In your profile, make a folder named `append-to`. Any text in these files will be added to the end of the respective files on the server.


#### Editing files in the container upon installation

If you just want to change a couple of cvars, you could put them in `profiles/yourcustomprofile/append-to/tf/cfg/server.cfg`, either in the form of `mycvar myvalue` or `sm_cvar mycvar myvalue`, depending on which you may want/need. However, if you want to keep things more organized, like if you're changing a bunch of plugin configurations, you should use the `reconfigure` folder.

In your profile, make a folder named `reconfigure`. The functionality is similar to `append-to`, but instead of appending text, setup.py looks for lines in the auto-generated configs starting with the "key" and replaces them with the line from the file in the `reconfigure` folder. For an example, see `profiles/example/reconfigure/tf/cfg/server.cfg`.

For more fine-grained control, consider writing a preinst_module instead (undocumented, see `profiles/example/preinst_modules/example_module.py` for an example).
