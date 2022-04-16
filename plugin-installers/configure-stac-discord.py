#!/usr/bin/env python3

# Inserts the StAC webhook URL configuration into discord.cfg


with open(f"profiles/{args.profile_name}/direct-copy/stac-webhook-url.txt") as f:
	webhook_url = f.read().strip()

cfg = (
	'\n	"stac"\n'
	'	{\n'
	f'		"url"	"{webhook_url}"\n'
	'	}\n'
	'}'
)
edit("tf/addons/sourcemod/configs/discord.cfg", r'}\n*\Z', cfg)
