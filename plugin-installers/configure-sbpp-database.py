print("Configuring the SourceBans++ plugin...")

# Configure the SourceBans++ table prefix
edit("tf/addons/sourcemod/configs/sourcebans/sourcebans.cfg", '"DatabasePrefix"\t"sb"', f'"DatabasePrefix"\t"{config["sbpp"]["db-table-prefix"]}"')
# Tell SourceBans++ what the server ID is
edit("tf/addons/sourcemod/configs/sourcebans/sourcebans.cfg", '"ServerID"\t\t"-1"', f'"ServerID"\t\t"{args.instance_number}"')
# Set the SourceBans++ website URL
edit("tf/addons/sourcemod/configs/sourcebans/sourcebans.cfg", '"Website"\t\t\t"http://www.yourwebsite.net/"', f'"Website"\t\t\t"{config["sbpp"]["webpanel-url"]}"')

print("Success!")
