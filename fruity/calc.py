
import math, slider


def calculatepp(osubdata, osubdata_api, mode, acc=100, max_player_combo=0, miss=0, score=1000000, mods=0, keys=None):
    # pp returning
    if mode == 2:
        r = __CatchTheBeat()
        return r.calculatepp(acc=acc, max_player_combo=max_player_combo, miss=miss, mods=mods, osubdata=osubdata,
                             osubdata_api=osubdata_api)
    elif mode == 3:
        r = __Mania()
        return r.calculatepp(acc=acc, score=score, mods=mods, keys=keys, osubdata=osubdata, osubdata_api=osubdata_api)
    elif mode == 1:
        r = __Taiko()
        return r.calculatepp(acc=acc, miss=miss, mods=mods, osubdata=osubdata, osubdata_api=osubdata_api)


def keycount(beatmap):
    percent = sum(1 for x in beatmap.hit_objects if
                  isinstance(x, slider.beatmap.Slider) or
                  isinstance(x, slider.beatmap.Spinner)) \
              / len(beatmap.hit_objects)
    if percent < 0.2:
        return 7
    if (percent < 0.3 or round(beatmap.circle_size) >= 5):
        return 7 if round(beatmap.overall_difficulty) > 5 else 6
    if (percent > 0.6):
        return 5 if round(beatmap.overall_difficulty) > 4 else 4
    return max(4, min(round(beatmap.overall_difficulty) + 1, 7))


class __CatchTheBeat:
    def __init__(self):
        pass

    def calculatepp(self, osubdata, osubdata_api, acc=100, max_player_combo=0, miss=0, mods=0):
        stars = float(osubdata_api.star_rating)
        max_combo = int(osubdata.max_combo)
        max_player_combo = int(osubdata.max_combo) if max_player_combo == 0 else max_player_combo
        ar = float(osubdata.approach_rate)

        finalpp = pow(((5 * max(1.0, stars / 0.0049)) - 4), 2) / 100000
        finalpp *= 0.95 + 0.4 * min(1.0, max_combo / 3000.0) + (
            math.log(max_combo / 3000.0, 10) * 0.5 if max_combo > 3000 else 0.0)
        finalpp *= pow(0.97, miss)
        finalpp *= pow(max_player_combo / max_combo, 0.8)
        if (ar > 9):
            finalpp *= 1 + 0.1 * (ar - 9.0)
        elif (ar < 8):
            finalpp *= 1 + 0.025 * (8.0 - ar)
        else:
            pass
        finalpp *= pow(acc / 100, 5.5)

        try:
            if mods & 8 == 8:
                finalpp *= 1.05 + 0.075 * (10.0 - min(10.0, ar))
            elif mods & 1024 == 1024:
                finalpp *= 1.35 * (0.95 + 0.4 * min(1.0, max_combo / 3000.0) + (
                    math.log(max_combo / 3000.0, 10) * 0.5 if max_combo > 3000 else 0.0))
        except:
            pass

        return float(round(finalpp, 3))


class __Mania:
    def __init__(self):
        pass

    def calculatepp(self, osubdata, osubdata_api, acc=100, score=1000000, mods=0, keys=None):
        #  Thanks Error- for the formula
        stars = float(osubdata_api.star_rating)
        od = float(osubdata.overall_difficulty)
        objectcount = len(osubdata.hit_objects)
        if int(osubdata.mode) == 0:
            orig_keys = keycount(osubdata)
        else:
            orig_keys = osubdata.circle_size

        # if keys == None:
        #     keys = orig_keys
        # if orig_keys < keys:
        #     score *= 0.9
        # elif orig_keys > keys:
        #     diff_keys = orig_keys - keys
        #     key_mult = [1, 0.86, 0.82, 0.78, 0.74, 0.7, 0.66]
        #     score *= key_mult[diff_keys]

        pfwdw = 64 - 3 * od
        strain1 = math.pow(5 * max(1, stars / 0.0825) - 4, 3) / 110000
        strain2 = 1 + 0.1 * min(1, objectcount / 1500)
        strainbase = strain2 * strain1
        strainmult = score / 500000 * 0.1 if score < 500000 else (
            (score - 500000) / 100000 * 0.2 + 0.1 if score < 600000 else (
                (score - 600000) / 100000 * 0.35 + 0.3 if score < 700000 else (
                    (score - 700000) / 100000 * 0.2 + 0.65 if score < 800000 else (
                        (score - 800000) / 100000 * 0.1 + 0.85 if score < 900000 else (
                            (score - 900000) / 100000 * 0.05 + 0.95)))))
        accfinal = math.pow(
            math.pow((150 / pfwdw) * math.pow(acc / 100, 16), 1.8) * 2.5 *
            min(1.15, math.pow(objectcount / 1500, 0.3)), 1.1)
        strainfinal = math.pow(strainbase * strainmult, 1.1)
        finalpp = math.pow(accfinal + strainfinal, 1 / 1.1) * 1.1
        try:
            if mods & 2 == 2:
                finalpp *= 0.5
            elif mods & 1 == 1:
                finalpp *= 0.9
            else:
                finalpp *= 1.1
        except:
            finalpp *= 1.1

        return float(round(finalpp, 3))


class __Taiko:
    def __init__(self):
        pass

    def calculatepp(self, osubdata, osubdata_api, acc=100, miss=0, mods=0):
        stars = float(osubdata_api.star_rating)
        max_combo = int(osubdata.max_combo)
        od = float(osubdata.overall_difficulty)
        pfhit = max_combo - miss

        try:
            if mods & 2 == 2:
                od *= 0.5
            elif mods & 16 == 16:
                od *= 1.4
            else:
                pass
        except:
            pass

        maxod = 20
        minod = 50
        result = minod + (maxod - minod) * od / 10
        result = math.floor(result) - 0.5
        pfwdw = round(result, 2)

        strain = (math.pow(max(1, stars / 0.0075) * 5 - 4, 2) / 100000) * (min(1, max_combo / 1500) * 0.1 + 1)
        strain *= math.pow(0.985, miss)
        strain *= min(math.pow(pfhit, 0.5) / math.pow(max_combo, 0.5), 1)
        strain *= acc / 100
        accfinal = math.pow(150 / pfwdw, 1.1) * math.pow(acc / 100, 15) * 22
        accfinal *= min(math.pow(max_combo / 1500, 0.3), 1.15)

        modmult = 1.1
        try:
            if mods & 8 == 8:
                modmult *= 1.1
                strain *= 1.025
            elif mods & 1 == 1:
                modmult *= 0.9
            elif mods & 1024 == 1024:
                strain *= 1.05 * min(1, max_combo / 1500) * 0.1 + 1
            else:
                pass
        except:
            pass
        finalpp = math.pow(math.pow(strain, 1.1) + math.pow(accfinal, 1.1), 1.0 / 1.1) * modmult
        return float(round(finalpp, 3))
