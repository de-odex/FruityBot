import datetime
import logging
import math
import operator
import re
import urllib.parse
from collections import OrderedDict, Counter, namedtuple
from itertools import islice

import slider
from twisted.internet import threads
from twisted.python import threadpool

import utils

logger = logging.getLogger(__name__)

Recommendation = namedtuple("Recommendation", "rec_list i last_refresh")

rec_thread_pool = threadpool.ThreadPool(name="recommendations")

class OsuUser:
    def __init__(self, user_id, preferences):
        self.preferences = preferences
        self.user_id = user_id
        self.user_client = None
        self.last_beatmap = None
        self.last_mod = None
        self.last_kwargs = None
        self.top_plays = [-1, None, None, None]  # per mode, will be arrays


class Osu:
    def __init__(self, cmd, bot):
        self.cmd = cmd  # use self.cmd.osu_library to get the library, to survive reloads
        self.bot = bot

    # region utils

    @staticmethod
    def key_count(beatmap):
        percent = sum(1 for x in beatmap.hit_objects if
                      isinstance(x, slider.beatmap.Slider) or
                      isinstance(x, slider.beatmap.Spinner)) \
                  / len(beatmap.hit_objects)
        if percent < 0.2:
            return 7
        if percent < 0.3 or round(beatmap.circle_size) >= 5:
            return 7 if round(beatmap.overall_difficulty) > 5 else 6
        if percent > 0.6:
            return 5 if round(beatmap.overall_difficulty) > 4 else 4
        return max(4, min(round(beatmap.overall_difficulty) + 1, 7))

    # endregion

    def np(self, osu_user, bot, e):
        osu_user.last_mod = False
        osu_user.last_kwargs = False

        link_str = re.findall(
            utils.URL_REGEX,
            e.arguments[0])
        link = urllib.parse.urlparse(link_str[0])
        if link.path.split("/")[1] == "b":
            beatmap_id = link.path.split("/")[2].split("&")[0]
        elif link.path.split("/")[1] == "beatmapsets" and link.fragment.split("/")[1].isdigit():
            beatmap_id = link.fragment.split("/")[1]
        else:
            return bot.msg(e.source.nick, "This is a beatmap set, not a beatmap")
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        estimate_strs = ((), ("SS", "99% FC", "98% FC"), ("SS", "99.5% FC", "99% FC", "98.5% FC"), ("SS", "99% 970k", "97% 900k"))
        pp_args = ((), (100, 99, 98), (100, 99.5, 99, 98.5), ((100, 1000000), (99, 970000), (97, 900000)))

        beatmap_data, beatmap_data_api, mode = self.get_data(e, beatmap_id)

        osu_user.last_beatmap = (beatmap_data, beatmap_data_api, mode, beatmap_id)

        bot.msg(e.source.nick, self.format_message(beatmap_data, beatmap_data_api, mode, estimate_strs, pp_args))
        return True

    def acm_mod(self, osu_user, bot, e):
        split_msg = e.arguments[0].split()

        mods_name = ""

        beatmap_data, beatmap_data_api, mode_api, beatmap_id = osu_user.last_beatmap

        mode = utils.Utils.check_mode_in_db(e.source, self.bot, beatmap_data)

        if mode_api != mode:
            beatmap_data_api = self.cmd.osu_api_client.beatmap(beatmap_id=beatmap_id,
                                                               include_converted_beatmaps=True,
                                                               game_mode=slider.game_mode.GameMode(mode))

        max_combo = int(beatmap_data_api.max_combo) if beatmap_data_api.max_combo else int(beatmap_data.max_combo)
        artist_name = beatmap_data.artist + " - " + beatmap_data.title + " [" + beatmap_data.version + "]"

        bm_time = utils.Utils.strfdelta(datetime.timedelta(seconds=int(beatmap_data_api.hit_length.seconds),
                                                           milliseconds=beatmap_data_api.hit_length.seconds -
                                                                        int(beatmap_data_api.hit_length.seconds)),
                                        "{M:02}:{S:02}")
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        if split_msg[0] == "acc":

            # checks for former mod data if any
            if not osu_user.last_mod:
                mods = 0
            else:
                mods = osu_user.last_mod

            # reads args of message
            acc = combo = miss = score = 0
            for i in split_msg:
                if utils.Utils.isfloat(i) or i.endswith(("%",)):
                    acc = float(i.replace("%", ""))
                elif i.endswith(("x",)):
                    combo = i.rstrip("x")
                elif i.endswith(("m",)):
                    miss = i.rstrip("m")
                elif i.endswith(("s",)):
                    score = i.rstrip("s")
                else:
                    pass

            if mods & 1 == 1:
                mods_name += "NF"
            if mods & 2 == 2:
                mods_name += "EZ"
            if mods & 8 == 8:
                mods_name += "HD"
            if mods & 1024 == 1024:
                mods_name += "FL"
            if mods == 0:
                mods_name = "NoMod"

            if mode == 2:
                if not combo:
                    combo = int(beatmap_data_api.max_combo)
                if not miss:
                    miss = 0

                try:
                    miss = int(miss)
                    miss = utils.Utils.clamp(miss, 0, max_combo - 1)
                except:
                    return bot.msg(e.source.nick, "You MISSed something there")
                try:
                    combo = int(combo)
                    combo = utils.Utils.clamp(combo, 0, max_combo)
                except:
                    return bot.msg(e.source.nick, "You made a mistake with your combo!")
                try:
                    acc = float(acc)
                    acc = utils.Utils.clamp(acc, 0.0, 100.0)
                except:
                    return bot.msg(e.source.nick, "Check your accuracy again, please")

                osu_user.last_kwargs = [acc, combo, miss]
                pp_values = (str(Osu.calculate_pp(beatmap_data,
                                                  beatmap_data_api, mode, acc=acc,
                                                  player_combo=combo, miss=miss,
                                                  mods=mods)),)
                acc_combo_miss = str(acc) + "% " + str(combo) + "x " + str(miss) + "miss " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                            + "* " + bm_time \
                            + " AR" + str(beatmap_data.approach_rate) \
                            + " MAX" + str(beatmap_data_api.max_combo)
                bot.msg(e.source.nick, artist_name
                        + " | osu!catch"
                        + " | " + acc_combo_miss + ": "
                        + pp_values[0] + "pp"
                        + " | " + end_props)
            elif mode == 3:
                try:
                    score = int(score)
                    if 1000000 >= score >= 0:
                        score = score
                    else:
                        raise SyntaxError
                except:
                    return bot.msg(e.source.nick, "You messed up your score there...")
                try:
                    acc = float(acc)
                    if 0 <= acc <= 100:
                        acc = acc
                    else:
                        raise SyntaxError
                except:
                    return bot.msg(e.source.nick, "Check your accuracy again, please")

                osu_user.last_kwargs = [acc, score]
                pp_values = (str(Osu.calculate_pp(beatmap_data,
                                                  beatmap_data_api, mode=mode, acc=acc,
                                                  score=score, mods=mods)),)
                acc_score = str(acc) + "% " + str(score) + " " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                            + "* " + bm_time \
                            + " OD" + str(beatmap_data.overall_difficulty) \
                            + " " + str(Osu.key_count(beatmap_data)) + "key" \
                            + " OBJ" + str(len(beatmap_data.hit_objects))
                bot.msg(e.source.nick, artist_name
                        + " | osu!mania"
                        + " | " + acc_score + ": "
                        + pp_values[0] + "pp"
                        + " | " + end_props)
            elif mode == 1:
                try:
                    miss = int(miss)
                    if miss < max_combo or miss >= 0:
                        miss = miss
                    else:
                        raise SyntaxError
                except:
                    return bot.msg(e.source.nick, "You MISSed something there")
                try:
                    acc = float(acc)
                    if 0 <= acc <= 100:
                        acc = acc
                    else:
                        raise SyntaxError
                except:
                    return bot.msg(e.source.nick, "Check your accuracy again, please")

                osu_user.last_kwargs = [acc, miss]
                pp_values = (str(Osu.calculate_pp(beatmap_data,
                                                  beatmap_data_api, mode=mode, acc=acc,
                                                  miss=miss, mods=mods)),)
                acc_miss = str(acc) + "% " + str(miss) + "miss " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                            + "* " + bm_time \
                            + " OD" + str(beatmap_data.overall_difficulty) \
                            + " MAX" + str(beatmap_data_api.max_combo)
                bot.msg(e.source.nick, artist_name
                        + " | osu!taiko"
                        + " | " + acc_miss + ": "
                        + pp_values[0] + "pp"
                        + " | " + end_props)
        elif split_msg[0] == "with":
            # checks for former acm data if any
            if not osu_user.last_kwargs:
                acm_data = False
            else:
                acm_data = osu_user.last_kwargs

            all_mods = slider.Mod.parse('nfezhdhrfl')

            # reads args of message
            mods = slider.Mod.parse(split_msg[1]) & all_mods

            # sets mod names for output and checks if no args were passed
            if mods & 1 == 1:
                mods_name += "NF"
            if mods & 2 == 2:
                mods_name += "EZ"
            if mods & 8 == 8:
                mods_name += "HD"
            if mods & 16 == 16:
                mods_name += "HR"
            if mods & 1024 == 1024:
                mods_name += "FL"
            if mods == 0:
                return bot.msg(e.source.nick, "These mods are not supported yet!")

            osu_user.last_mod = mods
            if mode == 2:  # hd and fl
                if mods & ~slider.Mod.parse('hdfl'):
                    return bot.msg(e.source.nick, "These mods are not supported yet!")

                if acm_data:
                    acc, combo, miss = acm_data
                else:
                    acc, combo, miss = (100, beatmap_data_api.max_combo, 0)
                pp_values = (str(Osu.calculate_pp(beatmap_data, beatmap_data_api, mode, acc=acc,
                                                  player_combo=combo, miss=miss, mods=mods)),)
                acc_combo_miss = str(acc) + "% " + str(combo) + "x " + str(miss) + "miss " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                            + "* " + bm_time \
                            + " AR" + str(beatmap_data.approach_rate) \
                            + " MAX" + str(beatmap_data_api.max_combo)
                return bot.msg(e.source.nick, artist_name
                               + " | osu!catch"
                               + " | " + acc_combo_miss + ": "
                               + pp_values[0] + "pp"
                               + " | " + end_props)
            elif mode == 3:  # nf and ez only
                if mods & ~slider.Mod.parse('nfez'):
                    return bot.msg(e.source.nick, "These mods are not supported yet!")

                if acm_data:
                    acc, score = acm_data
                else:
                    acc, score = (100, 1000000)
                pp_values = (str(Osu.calculate_pp(beatmap_data, beatmap_data_api, mode=mode, acc=acc, score=score,
                                                  mods=mods)),)
                acc_score = str(acc) + "% " + str(score) + " " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                            + "* " + bm_time \
                            + " OD" + str(beatmap_data.overall_difficulty) \
                            + " " + str(Osu.key_count(beatmap_data)) + "key" \
                            + " OBJ" + str(len(beatmap_data.hit_objects))
                return bot.msg(e.source.nick, artist_name
                               + " | osu!mania"
                               + " | " + acc_score + ": "
                               + pp_values[0] + "pp"
                               + " | " + end_props)
            elif mode == 1:  # all mods as of now
                if acm_data:
                    acc, miss = acm_data
                else:
                    acc, miss = (100, 0)
                pp_values = (str(Osu.calculate_pp(beatmap_data, beatmap_data_api, mode, acc=acc, miss=miss,
                                                  mods=mods)),)
                acc_miss = str(acc) + "% " + str(miss) + "miss " + mods_name
                end_props = str(round(float(beatmap_data_api.star_rating), 2)) \
                            + "* " + bm_time \
                            + " OD" + str(beatmap_data.overall_difficulty) \
                            + " MAX" + str(beatmap_data_api.max_combo)
                return bot.msg(e.source.nick, artist_name
                               + " | osu!taiko"
                               + " | " + acc_miss + ": "
                               + pp_values[0] + "pp"
                               + " | " + end_props)
                # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    @staticmethod
    def format_message(beatmap_data, beatmap_data_api, mode, estimate_strs, pp_args):
        artist_name = beatmap_data.artist + " - " + beatmap_data.title + " [" + beatmap_data.version + "]"
        bm_time = utils.Utils.strfdelta(datetime.timedelta(seconds=int(beatmap_data_api.hit_length.seconds),
                                                           milliseconds=beatmap_data_api.hit_length.seconds -
                                                                        int(beatmap_data_api.hit_length.seconds)),
                                        "{M:02}:{S:02}")

        end_props = f"{round(float(beatmap_data_api.star_rating), 2)}* {bm_time} "

        estimate_str = (estimate_strs[mode])
        try:
            pp_values = tuple(str(Osu.calculate_pp(beatmap_data, beatmap_data_api, mode=mode, acc=i))
                              for i in (pp_args[mode]))
        except:
            pass

        if mode == 1:
            mode_str = "osu!taiko"
            end_props += f"OD{beatmap_data.overall_difficulty} MAX{beatmap_data.max_combo}"
        elif mode == 2:
            mode_str = "osu!catch"
            end_props += f"AR{beatmap_data.approach_rate} MAX{beatmap_data_api.max_combo}"
        elif mode == 3:
            mode_str = "osu!mania"
            pp_values = tuple(str(Osu.calculate_pp(beatmap_data, beatmap_data_api, mode=mode, acc=i[0], score=i[1]))
                              for i in [(100, 1000000), (99, 970000), (97, 900000)])
            end_props += f"OD{beatmap_data.overall_difficulty} {Osu.key_count(beatmap_data)}key " \
                         f"OBJ{len(beatmap_data.hit_objects)}"
        else:
            return False

        final_str = f"{artist_name} | {mode_str} | "
        try:
            for i in range(len(estimate_str)-1):
                assert type(estimate_str[i]) is str
                final_str += f"{estimate_str[i]}: {round(float(pp_values[i]), 2)}pp | "
        except IndexError:
            pass
        final_str += f"{end_props}"

        return final_str

    def get_data(self, e, beatmap_id):
        beatmap_data = self.cmd.osu_library.lookup_by_id(beatmap_id, download=True, save=True)
        beatmap_data_api = self.cmd.osu_api_client.beatmap(beatmap_id=beatmap_id, include_converted_beatmaps=True)
        if not beatmap_data_api:
            raise Exception  # ModeError

        mode = utils.Utils.check_mode_in_db(e.source, self.bot, beatmap_data, np=True)

        if mode == -1:
            return

        beatmap_data_api = self.cmd.osu_api_client.beatmap(beatmap_id=int(beatmap_id),
                                                           include_converted_beatmaps=True,
                                                           game_mode=slider.GameMode(mode))

        if beatmap_data_api.max_combo is None and mode is not 3:
            beatmap_data_api = self.cmd.osu_api_client.beatmap(beatmap_id=int(beatmap_id),
                                                               include_converted_beatmaps=True)

        return (beatmap_data, beatmap_data_api, mode)

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def recommend(self, osu_user, bot, e):
        # https://github.com/Tyrrrz/OsuHelper/blob/master/OsuHelper/Services/RecommendationService.cs#L34

        def get_recommendation():
            recommend_list = list(bot.recommend[e.source.nick][user_mode].rec_list.items())
            try:
                recommended = recommend_list[bot.recommend[e.source.nick][user_mode].i]
            except IndexError:
                bot.msg(e.source.nick, "No more recommendations. Try !r reset")
                raise IndexError

            # start parsing data
            estimate_strs = ((),
                             (f"Confidence {recommended[1]} | SS", "99% FC", "98% FC"),
                             (f"Confidence {recommended[1]} | SS", "99.5% FC", "99% FC", "98.5% FC"),
                             (f"Confidence {recommended[1]} | SS", "99% 970k", "97% 900k"))
            pp_args = ((), (100, 99, 98), (100, 99.5, 99, 98.5), ((100, 1000000), (99, 970000), (97, 900000)))

            beatmap_data, beatmap_data_api, mode = self.get_data(e, recommended[0])

            osu_user.last_beatmap = (beatmap_data, beatmap_data_api, mode, recommended[0])

            bot.msg(e.source.nick, self.format_message(beatmap_data, beatmap_data_api, mode, estimate_strs, pp_args))

            # new object, then commit to sqlitedict
            try:
                x = bot.recommend[e.source.nick]
                x[user_mode] = Recommendation(rec_list=bot.recommend[e.source.nick][user_mode].rec_list,
                                              i=bot.recommend[e.source.nick][user_mode].i + 1,
                                              last_refresh=bot.recommend[e.source.nick][user_mode].last_refresh)
                bot.recommend[e.source.nick] = x
            except:
                x = [-1, None, None, None]
                x[user_mode] = Recommendation(rec_list=bot.recommend[e.source.nick][user_mode].rec_list,
                                              i=bot.recommend[e.source.nick][user_mode].i + 1,
                                              last_refresh=datetime.datetime.now())
                bot.recommend[e.source.nick] = x

        def iterate_maps_callback(result):
            _temp_list.extend(result)
            finish_deferred.append(0)

            logger.debug(f"*finished: {len(finish_deferred)} / {len(top_plays)}")
            if len(finish_deferred) % 3 == 0:
                bot.msg(e.source.nick, "Progress: " +
                        ("█" * round(len(finish_deferred) / 3)) + ("░" * round((30 - len(finish_deferred)) / 3)))

            if len(finish_deferred) == len(top_plays):
                _temp.update(_temp_list)
                _temp2 = OrderedDict(sorted(_temp.items(), key=operator.itemgetter(1), reverse=True))
                for i in top_plays:
                    _temp2.pop(i.beatmap_id, None)
                _temp3 = OrderedDict(islice(_temp2.items(), 200))

                try:
                    x = bot.recommend[e.source.nick]
                    x[user_mode] = \
                        Recommendation(rec_list=_temp3, i=0, last_refresh=bot.recommend[e.source.nick][user_mode])
                    # 0 used to be iter(_temp3.items())
                    bot.recommend[e.source.nick] = x
                except:
                    x = [-1, None, None, None]
                    x[user_mode] = \
                        Recommendation(rec_list=_temp3, i=0, last_refresh=datetime.datetime.now())
                    # 0 used to be iter(_temp3.items())
                    bot.recommend[e.source.nick] = x
                get_recommendation()

        def iterate_maps_errback(failure):
            try:
                failure.raiseException()
            except:
                logger.exception("IterMap Exception")

        def gen_rec_from_top(i):
            client = cmd.osu_api_client.copy()
            start_deferred.append(0)

            logger.debug(f"started: {len(start_deferred)} / {len(top_plays)}")

            # map top plays
            high_scores = sorted(client.beatmap_best(beatmap_id=i.beatmap_id, game_mode=game_mode),
                                 key=lambda x: abs(x.pp - i.pp))[:20]
            # through map top plays
            total_scores = []
            for j in high_scores:
                user_high_scores = sorted(
                    [k for k in client.user_best(user_id=j.user_id, game_mode=game_mode)
                     if (k.rank == "S" or k.rank == "X" or k.rank == "SH" or k.rank == "XH") and
                     (pp_limit_lower <= k.pp <= pp_limit_upper)],
                    key=lambda x: abs(x.pp - i.pp))[:20]
                total_scores.extend([k.beatmap_id for k in user_high_scores])
            return total_scores

        def iterate_map():
            # through own top plays
            for i in top_plays:
                # single thread
                # iterate_maps_callback(gen_rec_from_top(i))

                # multi-thread
                d = threads.deferToThreadPool(rec_thread_pool, gen_rec_from_top, i)
                d.addCallback(iterate_maps_callback)
                d.addErrback(iterate_maps_errback)

        user_mode = osu_user.preferences[e.source.nick].mode

        try:
            if bot.recommend[osu_user.user_id][user_mode] is not None \
                    and datetime.datetime.now() - bot.recommend[osu_user.user_id][user_mode].last_refresh < \
                    datetime.timedelta(hours=730, minutes=30):
                get_recommendation()
                return
        except:
            pass

        # progress tracker (I was lazy, OK?)
        start_deferred = []
        finish_deferred = []

        _temp_list = []  # sometimes i hate how assignment vs modification works
        _temp = Counter()

        cmd = self.cmd
        game_mode = slider.GameMode(user_mode)
        osu_user.user_client = cmd.osu_api_client.user(user_name=e.source.nick, game_mode=game_mode)

        top_plays = osu_user.user_client.high_scores(limit=30)
        osu_user.top_plays[user_mode] = top_plays
        assert len(top_plays) > 0

        pp_list = [i.pp for i in top_plays]
        pp_limit_lower = sum(pp_list) / float(len(pp_list))
        pp_limit_upper = pp_limit_lower * 1.25

        try:
            logger.debug("Generating recommendations")
            bot.msg(e.source.nick, "Generating recommendations, this may take a while...")
            iterate_map()
        except:
            logger.exception("Rec Exception")
            bot.msg(e.source.nick, "RecommendError: Unknown")

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    @staticmethod
    def calculate_pp(osu_b_data, osu_b_data_api, mode, mods=0, acc=100.0, **kwargs):
        if mode == 2:
            r = Osu.__CatchTheBeat()
        elif mode == 3:
            r = Osu.__Mania()
        elif mode == 1:
            r = Osu.__Taiko()
        else:
            return -1
        return r.calculate_pp(mods=mods, osu_b_data=osu_b_data, osu_b_data_api=osu_b_data_api, acc=acc, **kwargs)

    class __CatchTheBeat:
        @staticmethod
        def calculate_pp(osu_b_data, osu_b_data_api, acc=100.0, player_combo=0, miss=0, mods=0):
            stars = float(osu_b_data_api.star_rating)
            max_combo = int(osu_b_data.max_combo)
            player_combo = int(osu_b_data.max_combo) if player_combo == 0 else player_combo
            ar = float(osu_b_data.approach_rate)

            final_pp = pow(((5 * max(1.0, stars / 0.0049)) - 4), 2) / 100000
            final_pp *= 0.95 + 0.4 * min(1.0, max_combo / 3000.0) + (math.log(max_combo / 3000.0, 10) * 0.5
                                                                     if max_combo > 3000 else 0.0)
            final_pp *= pow(0.97, miss)
            final_pp *= pow(player_combo / max_combo, 0.8)
            if ar > 9:
                final_pp *= 1 + 0.1 * (ar - 9.0)
            elif ar < 8:
                final_pp *= 1 + 0.025 * (8.0 - ar)
            else:
                pass
            final_pp *= pow(acc / 100, 5.5)

            try:
                if mods & 8 == 8:
                    final_pp *= 1.05 + 0.075 * (10.0 - min(10.0, ar))
                elif mods & 1024 == 1024:
                    final_pp *= 1.35 * (0.95 + 0.4 * min(1.0, max_combo / 3000.0) + (
                        math.log(max_combo / 3000.0, 10) * 0.5 if max_combo > 3000 else 0.0))
            except:
                pass

            return final_pp

    class __Mania:
        @staticmethod
        def calculate_pp(osu_b_data, osu_b_data_api, acc=100.0, score=1000000, mods=0):
            #  Thanks Error- for the formula
            stars = float(osu_b_data_api.star_rating)
            od = float(osu_b_data.overall_difficulty)
            object_count = len(osu_b_data.hit_objects)

            perfect_window = 64 - 3 * od
            strain1 = math.pow(5 * max(1.0, stars / 0.0825) - 4, 3) / 110000
            strain2 = 1 + 0.1 * min(1.0, object_count / 1500)
            base_strain = strain2 * strain1
            strain_multiplier = (score / 500000 * 0.1 if score < 500000 else
                                 ((score - 500000) / 100000 * 0.2 + 0.1 if score < 600000 else
                                  ((score - 600000) / 100000 * 0.35 + 0.3 if score < 700000 else
                                   ((score - 700000) / 100000 * 0.2 + 0.65 if score < 800000 else
                                    ((score - 800000) / 100000 * 0.1 + 0.85 if score < 900000 else
                                     ((score - 900000) / 100000 * 0.05 + 0.95))))))
            acc_factor = math.pow(
                math.pow((150 / perfect_window) * math.pow(acc / 100, 16), 1.8) * 2.5 *
                min(1.15, math.pow(object_count / 1500, 0.3)), 1.1)
            strain_factor = math.pow(base_strain * strain_multiplier, 1.1)
            final_pp = math.pow(acc_factor + strain_factor, 1 / 1.1) * 1.1
            try:
                if mods & 2 == 2:
                    final_pp *= 0.5
                elif mods & 1 == 1:
                    final_pp *= 0.9
                else:
                    final_pp *= 1.1
            except:
                final_pp *= 1.1

            return final_pp

    class __Taiko:
        @staticmethod
        def calculate_pp(osu_b_data, osu_b_data_api, acc=100.0, miss=0, mods=0):
            stars = float(osu_b_data_api.star_rating)
            max_combo = int(osu_b_data.max_combo)
            od = float(osu_b_data.overall_difficulty)
            perfect_hits = max_combo - miss

            try:
                if mods & 2 == 2:
                    od *= 0.5
                elif mods & 16 == 16:
                    od *= 1.4
                else:
                    pass
            except:
                pass

            max_od = 20
            min_od = 50
            result = min_od + (max_od - min_od) * od / 10
            result = math.floor(result) - 0.5
            perfect_window = round(result, 2)

            strain = (math.pow(max(float(1), stars / 0.0075) * 5 - 4, 2) / 100000) * \
                     (min(float(1), max_combo / 1500) * 0.1 + 1)
            strain *= math.pow(0.985, miss)
            strain *= min(math.pow(perfect_hits, 0.5) / math.pow(max_combo, 0.5), 1)
            strain *= acc / 100
            acc_factor = math.pow(150 / perfect_window, 1.1) * math.pow(acc / 100, 15) * 22
            acc_factor *= min(math.pow(max_combo / 1500, 0.3), 1.15)

            mod_multiplier = 1.1
            try:
                if mods & 8 == 8:
                    mod_multiplier *= 1.1
                    strain *= 1.025
                elif mods & 1 == 1:
                    mod_multiplier *= 0.9
                elif mods & 1024 == 1024:
                    strain *= 1.05 * min(float(1), max_combo / 1500) * 0.1 + 1
                else:
                    pass
            except:
                pass
            final_pp = math.pow(math.pow(strain, 1.1) + math.pow(acc_factor, 1.1), 1.0 / 1.1) * mod_multiplier
            return final_pp
