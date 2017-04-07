import socket
import re
import requests
import urllib
import config
import math

ircsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server = "chat.freenode.net"  # Server
channel = "#testit"  # Channel
botnick = "aEverrBot"  # Your bots nick
adminname = "aEverr"  # Your IRC nickname. On IRC (and most other places) I go by OrderChaos so that’s what I am using for this example.
exitcode = "fuck you bot"
help_msg = "Need help? Check https://github.com/de-odex/aEverrBot/wiki for commands."

ircsock.connect((server, 6667))  # Here we connect to the server using the port 6667
ircsock.send(bytes("USER " + botnick + " " + botnick + " " + botnick + " " + botnick + "\n", "UTF-8"))  # We are basically filling out a form with this line and saying to set all the fields to the bot nickname.
ircsock.send(bytes("NICK " + botnick + "\n", "UTF-8"))  # assign the nick to the bot


def joinchan(chan):  # join channel(s).
	ircsock.send(bytes("JOIN " + chan + "\n", "UTF-8"))
	ircmsg = ""
	while ircmsg.find("End of /NAMES list.") == -1:
		ircmsg = ircsock.recv(2048).decode("UTF-8")
		ircmsg = ircmsg.strip('\n\r')
		print(ircmsg)


def ping():  # respond to server Pings.
	ircsock.send(bytes("PONG :pingis\n", "UTF-8"))


def sendmsg(msg, target):  # sends messages to the target.
	ircsock.send(bytes("PRIVMSG " + target + " :" + msg + "\n", "UTF-8"))


def get_b_data(api_key, beatmap_id):
	# request for data
	parameters = {
		"k": api_key,
		"b": beatmap_id,
		"m": 2,  # pick ctb game mode
		"a": 1  # allow converts
	}
	osubresponse = requests.get("https://osu.ppy.sh/api/get_beatmaps", params=parameters)
	return osubresponse.json()


def calculatepp(osubdata, acc="hi", max_player_combo="hi", miss="hi"):
	stars = float(osubdata["difficultyrating"])
	max_combo = int(osubdata["max_combo"])

	print(acc + ", " + max_player_combo + ", " + miss)
	try:
		int(miss)
		miss = miss if miss < max_combo else 0
	except:
		miss = 0

	try:
		int(max_player_combo)
		max_player_combo = max_player_combo if max_player_combo <= max_combo else max_combo - miss
	except:
		max_player_combo = max_combo - miss

	try:
		float(max_player_combo)
		acc = acc if acc >= 0 and acc <= 100 else float(((max_combo - miss) / max_combo) * 100)
	except:
		acc = float(((max_combo - miss) / max_combo) * 100)

	print(acc + ", " + max_player_combo + ", " + miss)
	ar = float(osubdata["diff_approach"])

	# DT must be applied first since it is not a multiplier

	finalpp = pow(((5 * max(1, stars / 0.0049)) - 4), 2) / 100000
	finalpp *= 0.95 + 0.4 * min(1.0, max_combo / 3000.0) + (math.log(max_combo / 3000.0, 10) * 0.5 if max_combo > 3000 else 0.0)
	finalpp *= pow(0.97, miss)
	finalpp *= pow(max_player_combo / max_combo, 0.8)
	if (ar > 9):
		finalpp *= 1 + 0.1 * (ar - 9.0)
	if (ar < 8):
		finalpp *= 1 + 0.025 * (8.0 - ar)
	else:
		finalpp *= 1
	finalpp *= pow(acc / 100, 5.5)

	# mods
	# if HD.get() == 1:
	# 	finalpp *= 1.05 + 0.075 * (10.0 - min(10.0, ar))
	# if FL.get() == 1:
	# 	finalpp *= 1.35 * (0.95 + 0.4 * min(1.0, max_combo / 3000.0) + (math.log(max_combo / 3000.0, 10) * 0.5 if max_combo > 3000 else 0.0))
	# if NF.get() == 1:
	# 	finalpp *= 0.90
	# END

	return int(round(finalpp, 0))

link_s = ""


def main():
	joinchan(channel)
	while 1:
		ircmsg = ircsock.recv(2048).decode("UTF-8")
		ircmsg = ircmsg.strip('\n\r')
		print(ircmsg)
		if ircmsg.find("PRIVMSG") != -1:
			# “:[Nick]!~[hostname]@[IP Address] PRIVMSG [channel] :[message]”
			# “:[Username]!cho@ppy.sh PRIVMSG [Username] :[message]”
			name = ircmsg.split('!', 1)[0][1:]
			message = ircmsg.split('PRIVMSG', 1)[1].split(':', 1)[1]

			if len(name) < 17:

				if message[1:23].find("ACTION is listening to") != -1:
					link = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', message)
					global link_s
					link_s = link[0]
					if link == []:
						sendmsg("There seems to be no link in your /np... Is this a beatmap you made?", name)
					else:
						beatmap_id = urllib.parse.urlparse(link[0]).path.split("/")[2]
						beatmap_data = get_b_data(config.api_key, beatmap_id)

						sent = beatmap_data[0]["artist"] + " - " + beatmap_data[0]["title"] + " [" + beatmap_data[0]["version"] + "] | osu!catch | SS: " + str(calculatepp(beatmap_data[0])) + "pp | 99.9% FC: " + str(calculatepp(beatmap_data[0], 99.9)) + "pp"
						sendmsg(sent, name)

				# send help
				# if message[:2].find("!a") != -1:
				# 	if link_s == "":
				# 		sendmsg("You haven't /np'd me anything yet!", name)
				# 	else:
				# 		split_msg = message.split()
				# 		split_msg.pop(0)
				# 		acc = 'hi'
				# 		combo = 'hi'
				# 		miss = 'hi'
				# 		for i in split_msg:
				# 			attr = i.split(":")
				# 			if attr[0] == "acc":
				# 				acc = attr[1]
				# 			elif attr[0] == "combo":
				# 				combo = attr[1]
				# 			elif attr[0] == "miss":
				# 				miss = attr[1]
				# 			else:
				# 				pass
				# 		beatmap_id = urllib.parse.urlparse(link_s).path.split("/")[2]
				# 		beatmap_data = get_b_data(config.api_key, beatmap_id)

				# 		sent = beatmap_data[0]["artist"] + " - " + beatmap_data[0]["title"] + " [" + beatmap_data[0]["version"] + "] | osu!catch | With your indicated attributes: " + str(calculatepp(beatmap_data[0], acc, combo, miss)) + "pp"
				# 		sendmsg(sent, name)

				if message[:2].find("!h") != -1:
					sendmsg(help_msg, name)

				if name.lower() == adminname.lower() and message.rstrip() == exitcode:
					sendmsg("aEverrBot is quitting.", name)
					ircsock.send(bytes("QUIT \n", "UTF-8"))
					return

		else:
			if ircmsg.find("PING :") != -1:
				ping()

main()
