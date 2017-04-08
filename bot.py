import socket
import re
import requests
import urllib
import config
import math
import time
import sys
# import traceback


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

	print(str(acc) + ", " + str(max_player_combo) + ", " + str(miss))
	try:
		# print(str(miss))
		miss = int(miss)
		miss = miss if miss < max_combo else 0
	except:
		# print(traceback.format_exc())
		miss = 0

	try:
		# print(str(max_player_combo))
		max_player_combo = int(max_player_combo)
		max_player_combo = max_player_combo if max_player_combo <= max_combo else max_combo - miss
		if max_player_combo < max_combo and miss < 1:
			miss = 1
	except:
		# print(traceback.format_exc())
		max_player_combo = max_combo - miss

	try:
		# print(str(acc))
		acc = float(acc)
		acc = acc if acc >= 0 and acc <= float(((max_combo - miss) / max_combo) * 100) else float(((max_combo - miss) / max_combo) * 100)
	except:
		# print(traceback.format_exc())
		acc = float(((max_combo - miss) / max_combo) * 100)

	print(str(acc) + ", " + str(max_player_combo) + ", " + str(miss))

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

link_s = {}

ircsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server = "cho.ppy.sh"  # Server
channel = "#testit"  # Channel
password = config.password  # Password
botnick = "aEverr"  # Your bots nick
adminname = "aEverr"  # Your IRC nickname
exitcode = "fuck you bot"
help_msg = "Need help? Check https://github.com/de-odex/aEverrBot/wiki for commands."
connected = False
ircsock.settimeout(300)
last_ping = time.time()
threshold = 15

# ircsock.connect((server, 6667))  # Here we connect to the server using the port 6667
# ircsock.send(bytes("PASS " + password + "\n", "UTF-8"))
# ircsock.send(bytes("USER " + botnick + " " + botnick + " " + botnick + " " + botnick + "\n", "UTF-8"))  # We are basically filling out a form with this line and saying to set all the fields to the bot nickname.
# ircsock.send(bytes("NICK " + botnick + "\n", "UTF-8"))  # assign the nick to the bot


def connection(host, port, password, nick, realname):
	global connected
	while connected is False:
		try:
			ircsock.connect((host, port))
			ircsock.send(bytes("PASS " + password + "\n", "UTF-8"))
			ircsock.send(bytes("USER %s %s bla :%s\r\n" % (realname, realname, realname)))
			ircsock.send(bytes("NICK %s\r\n" % nick))
			global connected
			connected = True
		except socket.error:
			print("Attempting to connect...")
			time.sleep(5)
			continue


def joinchan(chan):  # join channel(s).
	ircsock.send(bytes("JOIN " + chan + "\n", "UTF-8"))
	ircmsg = ""
	while ircmsg.find("End of /NAMES list.") == -1:
		ircmsg = ircsock.recv(2048).decode("UTF-8")
		ircmsg = ircmsg.strip('\n\r')
		print(ircmsg)


def ping():  # respond to server Pings.
	global last_ping
	ircsock.send(bytes("PONG :pingis\n", "UTF-8"))
	last_ping = time.time()


def sendmsg(msg, target):  # sends messages to the target.
	ircsock.send(bytes("PRIVMSG " + target + " :" + msg + "\n", "UTF-8"))


connection(server, 6667, password, botnick, botnick)


# joinchan(channel)
beatmap_id = {}
beatmap_data = {}
sent = {}
split_msg = {}
acc = {}
combo = {}
miss = {}
while connected:
	try:
		ircmsg = ircsock.recv(1024).decode("UTF-8")
		ircmsg = ircmsg.strip('\n\r')
		# print(ircmsg)
		if ircmsg.find("PRIVMSG") != -1:
			# “:[Nick]!~[hostname]@[IP Address] PRIVMSG [channel] :[message]”
			# “:[Username]!cho.ppy.sh PRIVMSG [Username] :[message]”
			name = ircmsg.split('PRIVMSG', 1)[0].split(':')[-1].split("!")[0]  # ircmsg.split('!', 1)[0][1:]
			message = ircmsg.split('PRIVMSG', 1)[1].split(':', 1)[1]
			me = ircmsg.split('PRIVMSG', 1)[1].split(':', 1)[0].split()[0]
			print(me)
			print(ircmsg + " name:" + name)
			if len(name) < 17:
				if me == botnick:
					if message[1:23].find("ACTION is listening to") != -1 or message[1:18].find("ACTION is playing") != -1:
						link = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', message)
						global link_s
						try:
							link_s[name] = link[0]
							beatmap_id[name] = urllib.parse.urlparse(link_s[name]).path.split("/")[2]
							beatmap_data[name] = get_b_data(config.api_key, beatmap_id[name])

							sent[name] = beatmap_data[name][0]["artist"] + " - " + beatmap_data[name][0]["title"] + " [" + beatmap_data[name][0]["version"] + "] | osu!catch | SS: " + str(calculatepp(beatmap_data[name][0])) + "pp | 99.9% FC: " + str(calculatepp(beatmap_data[name][0], 99.9)) + "pp"
							sendmsg(sent[name], name)
						except:
							sendmsg("There seems to be no link in your /np... Is this a beatmap you made?", name)

					# send help
					if message[:2].find("!a") != -1:
						if name not in link_s:
							sendmsg("You haven't /np'd me anything yet!", name)
						else:
							split_msg[name] = message.split()
							split_msg.pop(0)
							acc[name] = 'hi'
							combo[name] = 'hi'
							miss[name] = 'hi'
							if name not in split_msg:
								sendmsg("Somehow your message got lost in my head... Send it again?", name)
								break
							for i in split_msg[name]:
								attr = i.split(":")
								if attr[0] == "acc":
									acc[name] = attr[1]
								elif attr[0] == "combo":
									combo[name] = attr[1]
								elif attr[0] == "miss":
									miss[name] = attr[1]
								else:
									pass
							beatmap_id[name] = urllib.parse.urlparse(link_s[name]).path.split("/")[2]
							beatmap_data[name] = get_b_data(config.api_key, beatmap_id[name])

							sent[name] = beatmap_data[name][0]["artist"] + " - " + beatmap_data[name][0]["title"] + " [" + beatmap_data[name][0]["version"] + "] | osu!catch | With your indicated attributes: " + str(calculatepp(beatmap_data[name][0], acc[name], combo[name], miss[name])) + "pp"
							sendmsg(sent[name], name)

					if message[:2].find("!h") != -1:
						sendmsg(help_msg, name)

					if name.lower() == adminname.lower() and message.rstrip() == exitcode:
						sendmsg("aEverrBot is quitting.", name)
						ircsock.send(bytes("QUIT \n", "UTF-8"))
						sys.exit()

		else:
			if ircmsg.find("PING :") != -1:
				ping()
		if (time.time() - last_ping) > threshold:
			break
	except socket.timeout:
		global connected
		connected = False
		print(connected)
		break
print("No internet. Out of loop")
connection(server, 6667, password, botnick, botnick)
