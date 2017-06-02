import math


class CatchTheBeat:
	def calculatepp(self, osubdata, acc=100, max_player_combo=0, miss=0, mods=0):
		stars = float(osubdata["difficultyrating"])
		max_combo = int(osubdata["max_combo"])
		max_player_combo = int(osubdata["max_combo"]) if max_player_combo == 0 else max_player_combo

		ar = float(osubdata["diff_approach"])

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

		return float(round(finalpp, 3))


class Mania:
	def calculatepp(self, osubdata, acc=100, max_player_combo=0, miss=0, mods=0):
		stars = float(osubdata["difficultyrating"])
		max_combo = int(osubdata["max_combo"])
		max_player_combo = int(osubdata["max_combo"]) if max_player_combo == 0 else max_player_combo

		ar = float(osubdata["diff_approach"])

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

		return float(round(finalpp, 3))
