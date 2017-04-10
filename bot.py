import socket
import re
import requests
import urllib
import config
import math
import time
import sys
import winsound
import string
import random
# import multiprocessing
# import traceback
first_time = time.time()
beatmap_data_s = {}


class ModeError(Exception):
	pass


class MsgError(Exception):
	pass


class NpError(Exception):
	pass


# PP COMMANDS


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


def calculatepp(osubdata, acc="hi", max_player_combo="hi", miss="hi", mods="hi"):
	stars = float(osubdata["difficultyrating"])
	max_combo = int(osubdata["max_combo"])

	# print(str(acc) + ", " + str(max_player_combo) + ", " + str(miss))
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

	# print(str(acc) + ", " + str(max_player_combo) + ", " + str(miss))

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

	try:
		if mods & 8 == 8:
			finalpp *= 1.05 + 0.075 * (10.0 - min(10.0, ar))
		if mods & 1024 == 1024:
			finalpp *= 1.35 * (0.95 + 0.4 * min(1.0, max_combo / 3000.0) + (math.log(max_combo / 3000.0, 10) * 0.5 if max_combo > 3000 else 0.0))
		# if mods == 1:
		# 	finalpp *= 0.90
	except:
		pass
	# END

	return float(round(finalpp, 3))


def sendnp(message, name):
	global beatmap_data_s
	link = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', message)
	try:
		beatmap_id = urllib.parse.urlparse(link[0]).path.split("/")[2]
		if urllib.parse.urlparse(link[0]).path.split("/")[1] != "b":
			sendmsg("ERROR: TUB1D;" + ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(20)), name)
			return
		beatmap_data = get_b_data(config.api_key, beatmap_id)
		if not beatmap_data:
			raise ModeError
		beatmap_data_s[name] = beatmap_data
		sent = beatmap_data[0]["artist"] + " - " + beatmap_data[0]["title"] + " [" + beatmap_data[0]["version"] + "] | osu!catch | SS: " + str(calculatepp(beatmap_data[0])) + "pp | 99.5% FC: " + str(calculatepp(beatmap_data[0], 99.5)) + "pp | 99% FC: " + str(calculatepp(beatmap_data[0], 99)) + "pp | 98.5% FC: " + str(calculatepp(beatmap_data[0], 98.5)) + "pp | " + str(round(float(beatmap_data[0]["difficultyrating"]), 2)) + "* " + time.strftime("%M:%S", time.gmtime(int(beatmap_data[0]["total_length"])))
		sendmsg(sent, name)
	except IndexError:
		sendmsg("There seems to be no link in your /np... Is this a beatmap you made?", name)
	except ModeError:
		sendmsg("The bot only accepts CtB-mode maps, including converts. Sorry to the Mania and Taiko players out there :(", name)


def sendacm(message, name):
	global beatmap_data_s
	try:
		if name not in beatmap_data_s:
			raise NpError
		split_msg = message.split()
		del split_msg[0]
		if not split_msg:
			raise MsgError
		acc = 'hi'
		combo = 'hi'
		miss = 'hi'
		for i in split_msg:
			attr = i.split(":")
			if attr[0] == "acc":
				acc = attr[1]
			elif attr[0] == "combo":
				combo = attr[1]
			elif attr[0] == "miss":
				miss = attr[1]
		beatmap_data = beatmap_data_s[name]
		sent = beatmap_data[0]["artist"] + " - " + beatmap_data[0]["title"] + " [" + beatmap_data[0]["version"] + "] | osu!catch | With your indicated attributes: " + str(calculatepp(beatmap_data[0], acc, combo, miss)) + "pp | " + str(round(float(beatmap_data[0]["difficultyrating"]), 2)) + "* " + time.strftime("%M:%S", time.gmtime(int(beatmap_data[0]["total_length"])))
		sendmsg(sent, name)
	except MsgError:
		sendmsg("Somehow your message got lost in my head... Send it again?", name)
	except NpError:
		sendmsg("You haven't /np'd me anything yet!", name)


def sendmod(message, name):
	global beatmap_data_s
	try:
		if name not in beatmap_data_s:
			raise NpError
		split_msg = message.split()
		del split_msg[0]
		if not split_msg:
			raise MsgError
		mods = 0
		if split_msg[0].find("HD") != -1:
			mods += 8
		if split_msg[0].find("FL") != -1:
			mods += 1024
		beatmap_data = beatmap_data_s[name]
		sent = beatmap_data[0]["artist"] + " - " + beatmap_data[0]["title"] + " [" + beatmap_data[0]["version"] + "] | osu!catch | With your indicated mods: " + str(calculatepp(beatmap_data[0], "", "", "", mods)) + "pp | " + str(round(float(beatmap_data[0]["difficultyrating"]), 2)) + "* " + time.strftime("%M:%S", time.gmtime(int(beatmap_data[0]["total_length"])))
		sendmsg(sent, name)
	except MsgError:
		sendmsg("Somehow your message got lost in my head... Send it again?", name)
	except NpError:
		sendmsg("You haven't /np'd me anything yet!", name)


def sendrec(message, name):
	try:
		# get top 10 beatmaps
		# get scores with +-(variance) pp, about 10
		# get users of scores
		# check similar pp plays

		pass
	except:
		pass


# CONNECTION COMMANDS
ircsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server = config.server  # Server
password = config.password  # Password
botnick = config.botnick  # Your bots nick
adminname = config.adminname  # Your IRC nickname
exitcode = config.exitcode
help_msg = "Need help? Check https://github.com/de-odex/aEverrBot/wiki for commands."
connected = False
ircsock.settimeout(300)
last_ping = time.time()
thresh_mult = 1.5
threshold = int(round(64 * thresh_mult, 0))
rec_tries = 1
sleep_timer = 8


def connection(host, port, password, nick, realname):
	global connected
	while connected is False:
		try:
			ircsock.connect((host, port))
			ircsock.send(bytes("PASS " + password + "\n", "UTF-8"))
			ircsock.send(bytes("USER " + botnick + " " + botnick + " " + botnick + " " + botnick + "\n", "UTF-8"))
			ircsock.send(bytes("NICK " + botnick + "\n", "UTF-8"))
			connected = True
		except socket.error:
			global rec_tries, sleep_timer
			print("Attempting to connect... Try #" + str(rec_tries) + ", sleeping for " + str(sleep_timer))
			rec_tries += 1
			winsound.PlaySound("SystemHand", winsound.SND_ALIAS)
			time.sleep(sleep_timer)
			sleep_timer *= 2 if sleep_timer < 256 else 1
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
	print("Ponged after " + str(time.time() - last_ping) + " seconds from last ping!")
	last_ping = time.time()


def sendmsg(msg, target):  # sends messages to the target.
	try:
		ircsock.send(bytes("PRIVMSG " + target + " :" + msg + "\n", "UTF-8"))
		print("Sending: [" + str(msg) + "] to: " + str(target))
	except:
		print("Failed!")


# MAIN


if __name__ == '__main__':
	connection(server, 6667, password, botnick, botnick)
	# joinchan(channel)
	while connected:
		try:
			# print("Connected!")
			rec_tries = 1
			ircmsg = ircsock.recv(1024).decode("UTF-8")
			ircmsg = ircmsg.strip('\n\r')
			if ircmsg.find("QUIT") == -1 and ircmsg.find("PING") == -1:
				print(ircmsg)
			if ircmsg.find("PRIVMSG") != -1:
				try:
					# “:[Nick]!~[hostname]@[IP Address] PRIVMSG [channel] :[message]”
					# “:[Username]!cho.ppy.sh PRIVMSG [Username] :[message]”
					name = ircmsg.split('PRIVMSG', 1)[0].split(':')[-1].split("!")[0]  # ircmsg.split('!', 1)[0][1:]
					message = ircmsg.split('PRIVMSG', 1)[1].split(':', 1)[1].splitlines()[0]  # .strip()[0]
					me = ircmsg.split('PRIVMSG', 1)[1].split(':', 1)[0].split()[0]
					# print(me)
					print("name: " + name + ", message: " + message)
					if len(name) < 17:
						if me == botnick:

							if message[1:10].find("ACTION is") != -1:
								sendnp(message, name)

							if message[:2].find("!a") != -1:  # RECODE TO !a = acc !c = combo !m = miss
								sendacm(message, name)

							if message[:5].find("!with") != -1:
								sendmod(message, name)

							if message[:2].find("!h") != -1 or message[:5].find("!help") != -1:
								sendmsg(help_msg, name)

							if message[:2].find("!f") != -1 or message[:4].find("!faq") != -1:
								sendmsg("You have to write \"acc:95\" for !a; You can indicate !a values in any order, as long as they have the prefix (acc:, combo:, miss:)", name)

							if message[:2].find("!r") != -1:
								sendmsg("Under construction", name)
								pass

							if message[:7].find("!uptime") != -1:
								sendmsg(time.strftime("%H;%M;%S", time.gmtime(time.time() - first_time)) + " since start.", name)

							if message[:5].find("!time") != -1:
								sendmsg("Local time: " + time.strftime("%B %d %H:%M:%S", time.localtime(time.time())), name)

							if name.lower() == adminname.lower() and message.rstrip() == exitcode:
								sendmsg("aEverrBot is quitting.", name)
								ircsock.send(bytes("QUIT \n", "UTF-8"))
								sys.exit()
						last_ping = time.time()
						time.sleep(1)
				except:
					pass
			elif ircmsg.find("PING") != -1:
				ping()

			if (time.time() - last_ping) > threshold:
				raise socket.timeout
		except socket.timeout:
			connected = False
			print("Connected = " + str(connected))
			break

	print("No internet, Since Program start: " + time.strftime("%H:%M:%S", time.gmtime(time.time() - first_time)) + ". Restarting loop...")
	connection(server, 6667, password, botnick, botnick)
