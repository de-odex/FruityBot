import datetime
import logging
import operator
import pathlib
import urllib.parse
import zlib
from collections import Counter
from collections import OrderedDict
from itertools import islice
from typing import *

import dill
import math
import numpy
import redis
import requests
import urlextract
from ratelimit import limits, sleep_and_retry
from twisted.internet import reactor, threads
from twisted.python import threadpool

import slider
from ..core_bot.bot_module import Module, cached, command, requires_args
from ..exceptions import MissingPreferenceError
from ..localize import tl
from ..utils import check_mode_in_db, is_type, strfdelta

logger = logging.getLogger(__name__)


@sleep_and_retry
@limits(calls=60, period=60)
def get(*args, **kwargs):
    return requests.get(*args, **kwargs)


class Osu(Module):
    def __init__(self, state, bot):
        logger.debug("Osu.__init__ | starting")
        super().__init__(state, bot)

        logger.debug("Osu.__init__ | setting up osu library directory")
        self.lib_dir: pathlib.Path = (self.bot.root_dir / "osulib").absolute()
        if not self.lib_dir.is_dir() and self.lib_dir.exists():
            raise FileExistsError(f"Library path {self.lib_dir} is not a directory")
        self.lib_dir.mkdir(exist_ok=True)

        # set up redis
        logger.debug("Osu.__init__ | setting up redis")
        self.recommend_redis = redis.Redis(port=6379, db=1)
        self.recommend_redis.config_set('save', f'{60 * 10} 1 {60 * 2} 10')

        logger.debug("Osu.__init__ | loading osu library and api client")
        self.osu_library = slider.library.Library.create_db(self.lib_dir, recurse=False, show_progress=True)
        self.osu_api_client = slider.client.Client(self.osu_library, self.bot.Config().osu.api)
        self.osu_api_client.beatmap = sleep_and_retry(limits(calls=60, period=60)(self.osu_api_client.beatmap))

        logger.debug("Osu.__init__ | finished")

    # region utils

    @classmethod
    def format_message(cls, beatmap_data, beatmap_data_api, mode, pp_kwargs_tuple: Tuple[OrderedDict], recommend=""):
        bm_time = strfdelta(
            datetime.timedelta(
                seconds=int(beatmap_data_api.hit_length.seconds),
                milliseconds=beatmap_data_api.hit_length.seconds - int(beatmap_data_api.hit_length.seconds)
            ),
            "{M:02}:{S:02}"
        )
        end_props = f"{round(float(beatmap_data_api.star_rating), 2)}* {bm_time} "

        if mode == slider.GameMode.taiko:
            mode_str = "osu!taiko"
            end_props += f"OD{beatmap_data.overall_difficulty} MAX{beatmap_data.max_combo}"
            max_combo = beatmap_data.max_combo
        elif mode == slider.GameMode.ctb:
            mode_str = "osu!catch"
            end_props += f"AR{beatmap_data.approach_rate} MAX{beatmap_data_api.max_combo}"
            max_combo = beatmap_data_api.max_combo
        elif mode == slider.GameMode.mania:
            mode_str = "osu!mania"
            end_props += f"OD{beatmap_data.overall_difficulty} {slider.mod.key_count(beatmap_data)}K " \
                f"OBJ{len(beatmap_data.hit_objects)}"
            max_combo = beatmap_data.hit_objects
        else:
            return False

        estimate_strings = [Osu.generate_arg_str(max_combo, **pp_kwargs) for pp_kwargs in pp_kwargs_tuple]
        pp_values = tuple(str(Osu.calculate_pp(beatmap_data, beatmap_data_api, mode=mode, **i))
                          for i in pp_kwargs_tuple)

        final_lst = []

        if recommend:
            link = f"https://osu.ppy.sh/beatmapsets/{beatmap_data.beatmap_set_id}" \
                f"#{slider.GameMode.serialize(beatmap_data.mode)}/" \
                f"{beatmap_data_api.beatmap_id}"
            final_lst.append(f"[{link} {beatmap_data.display_name}]")
            final_lst.append(mode_str)
            final_lst.append(recommend)
        else:
            final_lst.append(beatmap_data.display_name)
            final_lst.append(mode_str)
        try:
            for i in range(len(estimate_strings)):
                assert type(estimate_strings[i]) is str
                final_lst.append(f"{estimate_strings[i]}: {round(float(pp_values[i]), 2)}pp")
        except IndexError:
            pass
        final_lst.append(end_props)
        return " | ".join(final_lst)

    @cached
    def get_api_data(self, beatmap_id, mode):
        beatmap_data_api = self.osu_api_client.beatmap(
            beatmap_id=beatmap_id,
            include_converted_beatmaps=True,
            game_mode=slider.GameMode(mode)
        )
        # noinspection PyProtectedMember
        del beatmap_data_api._library
        return beatmap_data_api

    def get_data(self, e, beatmap_id, np=False):
        library = self.osu_library.copy()
        beatmap_data = library.lookup_by_id(beatmap_id, download=True, save=True)
        library.close()

        mode = check_mode_in_db(e.source, self.bot, beatmap_data.mode, np=np)
        if mode == -1:
            raise MissingPreferenceError

        beatmap_data_api = self.get_api_data(beatmap_id, mode)

        if beatmap_data_api.max_combo is None and mode is not slider.GameMode.mania:
            beatmap_data_api = self.osu_api_client.beatmap(beatmap_id=beatmap_id,
                                                           include_converted_beatmaps=True)

        logger.debug(f"Osu.get_data | data = {(beatmap_data, beatmap_data_api, mode)}")

        return beatmap_data, beatmap_data_api, mode

    @staticmethod
    def get_accuracy(highscore: slider.client.HighScore, mode: slider.GameMode):
        total = sum(v for k, v in highscore.__dict__.items() if 'count' in k)
        if mode == slider.GameMode.taiko:
            return (
                (highscore.count_300 + highscore.count_100 / 2)
                / (highscore.count_300 + highscore.count_100 + highscore.count_miss)
            )
        if mode == slider.GameMode.ctb:
            return (
                (highscore.count_300 + highscore.count_100 + highscore.count_50)
                / (
                    highscore.count_300 + highscore.count_100 + highscore.count_50
                    + highscore.count_miss + highscore.count_katu
                )
            )
        if mode == slider.GameMode.mania:
            # a geki is 300 + 20, a katu is 200
            return ((highscore.count_geki + highscore.count_300) * 6 + highscore.count_katu * 4 +
                    highscore.count_100 * 2 + highscore.count_50) / (total * 6)
        return -1

    @staticmethod
    def generate_arg_str(full_combo, **kwargs):
        arg_str = []
        for k, v in kwargs.items():
            if k == "acc":
                if v == 1:
                    arg_str.append("SS")
                else:
                    arg_str.append(f"{v:.2%}")
            elif k == "player_combo":
                if kwargs.get("acc", 0) != 1:
                    if v == full_combo:
                        arg_str.append(f"FC")
                    else:
                        arg_str.append(f"{v}x")
            elif k == "miss":
                if v > 0:
                    arg_str.append(f"{v} miss")
            elif k == "score":
                if v != 1_000_000:
                    if not v % 1000:
                        arg_str.append(f"{v // 1000}k")
                    else:
                        arg_str.append(f"{v:,}")
                elif "SS" not in arg_str:
                    arg_str.append("SS")
            elif k == "mods":
                arg_str.append(slider.Mod.serialize(v).upper())
        return " ".join(arg_str)

    # endregion

    # region pp calculation

    @staticmethod
    def calculate_pp(osu_b_data, osu_b_data_api, mode, mods=0, **kwargs):
        if mode == 2:
            r = Osu.CatchTheBeat()
        elif mode == 3:
            r = Osu.Mania()
        elif mode == 1:
            r = Osu.Taiko()
        else:
            return -1
        return r.calculate_pp(mods=mods, beatmap_data=osu_b_data, beatmap_data_api=osu_b_data_api, **kwargs)

    class CatchTheBeat:
        @staticmethod
        def calculate_pp(beatmap_data, beatmap_data_api, mods=0, acc=1., player_combo=None, miss=0):
            stars = float(beatmap_data_api.star_rating)
            if mods & slider.Mod.double_time:
                from .osu_diff import diff
                stars = diff.Catch.Diff(beatmap_data, mods=mods).star_rating
                logger.debug(stars)

            max_combo = int(beatmap_data_api.max_combo)
            player_combo = int(beatmap_data_api.max_combo) if player_combo is None else player_combo
            ar = float(beatmap_data.approach_rate)

            final_pp = pow(((5 * max(1.0, stars / 0.0049)) - 4), 2) / 100000
            final_pp *= 0.95 + 0.4 * min(1.0, max_combo / 3000.0) \
                        + (math.log(max_combo / 3000.0, 10) * 0.5 if max_combo > 3000 else 0.0)
            final_pp *= pow(0.97, miss)
            final_pp *= pow(player_combo / max_combo, 0.8)
            if ar > 9:
                final_pp *= 1 + 0.1 * (ar - 9.0)
            elif ar < 8:
                final_pp *= 1 + 0.025 * (8.0 - ar)
            final_pp *= pow(acc, 5.5)

            try:
                if mods & slider.Mod.hidden:
                    final_pp *= 1.05 + 0.075 * (10.0 - min(10.0, ar))
                elif mods & slider.Mod.flashlight:
                    final_pp *= 1.35 * (0.95 + 0.4 * min(1.0, max_combo / 3000.0) +
                                        (math.log(max_combo / 3000.0, 10) * 0.5 if max_combo > 3000 else 0.0))
            except:
                pass

            return final_pp

    class Mania:
        @staticmethod
        def calculate_pp(beatmap_data, beatmap_data_api, mods=0, score=1000000):
            #  Thanks Error- for the formula
            stars = float(beatmap_data_api.star_rating)
            od = float(beatmap_data.overall_difficulty)
            object_count = len(beatmap_data.hit_objects)

            if mods & slider.Mod.key_mod:
                mod_key_count = int(
                    list(
                        k for k, v in slider.Mod.unpack(mods & slider.Mod.key_mod).items() if v
                    )[0][-1]
                )
                score_multiplier = slider.mod.score_multiplier(slider.mod.key_count(beatmap_data), mod_key_count)
                score *= score_multiplier

            perfect_window = 64 - 3 * od
            base_strain = math.pow(5 * max(1.0, stars / 0.2) - 4, 2.2) / 135  # 'Obtain strain difficulty'
            base_strain *= 1 + 0.1 * min(1.0, object_count / 1500)  # 'Longer maps are worth more'
            base_strain *= (0 if score < 500000 else
                            ((score - 500000) / 100000 * 0.3 if score < 600000 else
                             ((score - 600000) / 100000 * 0.25 + 0.3 if score < 700000 else
                              ((score - 700000) / 100000 * 0.2 + 0.55 if score < 800000 else
                               ((score - 800000) / 100000 * 0.15 + 0.75 if score < 900000 else
                                ((score - 900000) / 100000 * 0.1 + 0.90))))))
            window_factor = max(0.0, 0.2 - ((perfect_window - 34) * 0.006667))
            score_factor = pow((max(0, (score - 960000)) / 40000.0), 1.1)
            base_acc = window_factor * base_strain * score_factor
            acc_factor = math.pow(base_acc, 1.1)
            strain_factor = math.pow(base_strain, 1.1)
            final_pp = math.pow(acc_factor + strain_factor, 1 / 1.1)
            try:
                if mods & slider.Mod.easy:
                    final_pp *= 0.5
                elif mods & slider.Mod.no_fail:
                    final_pp *= 0.9
                else:
                    final_pp *= 0.8
            except:
                final_pp *= 0.8

            return final_pp

    class Taiko:
        @staticmethod
        def calculate_pp(beatmap_data, beatmap_data_api, mods=0, acc=1., miss=0):
            stars = float(beatmap_data_api.star_rating)
            max_combo = int(beatmap_data.max_combo)
            od = float(beatmap_data.overall_difficulty)
            perfect_hits = max_combo - miss

            try:
                if mods & slider.Mod.easy:
                    od *= 0.5
                elif mods & slider.Mod.hard_rock:
                    od *= 1.4
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
            strain *= acc
            acc_factor = math.pow(150 / perfect_window, 1.1) * math.pow(acc / 100, 15) * 22
            acc_factor *= min(math.pow(max_combo / 1500, 0.3), 1.15)

            mod_multiplier = 1.1
            try:
                if mods & slider.Mod.hidden:
                    mod_multiplier *= 1.1
                    strain *= 1.025
                elif mods & slider.Mod.no_fail:
                    mod_multiplier *= 0.9
                elif mods & slider.Mod.flashlight:
                    strain *= 1.05 * min(1, max_combo / 1500) * 0.1 + 1
            except:
                pass

            final_pp = math.pow(math.pow(strain, 1.1) + math.pow(acc_factor, 1.1), 1.0 / 1.1) * mod_multiplier
            return final_pp

    # endregion

    # Osu! ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    @command(aliases=["r"])
    def recommend(self, e):
        if not self.osu_library:
            return self.bot.msg(e.source.nick, tl("osu.loading", self.bot.user_pref[e.source.nick].locale))

        user = self.bot.users.setdefault(e.source.nick, OsuUser(e.source.nick))
        try:
            logger.debug(f"Osu.recommend | check for arguments? {len(e.arguments) >= 2}")
            if len(e.arguments) >= 2:
                if e.arguments[1] == "reset":
                    logger.debug("Osu.recommend | recommend reset incurred")
                    del self.recommend_redis[e.source.nick, self.bot.user_pref[e.source.nick].mode, "rec_list"]
                    self.bot.msg(e.source.nick, "Reset your recommendations!")
                elif e.arguments[1] == "reload":
                    logger.debug("Osu.recommend | recommend reload incurred")
                    self.recommend_redis[e.source.nick, self.bot.user_pref[e.source.nick].mode, "i"] = 0
                    self.bot.msg(e.source.nick, "Reloaded your recommendations!")
        except:
            logger.exception("")
            pass

        if e.source.nick not in self.bot.user_pref:
            self.bot.msg(e.source.nick, tl("osu.buggy", self.bot.user_pref[e.source.nick].locale))

        self._recommend(user, e)

    def _recommend(self, osu_user, e):
        """'What the fuck is this', you ask? I don't know either."""

        # christ, deprecate this function ASAP
        # https://github.com/Tyrrrz/OsuHelper/blob/master/OsuHelper/Services/RecommendationService.cs#L34

        rec_num = 20
        min_threads = 5
        max_threads = 10

        def obj_decode(obj):
            return dill.loads(zlib.decompress(bytes(obj))) if obj is not None else None

        def obj_encode(obj):
            return zlib.compress(dill.dumps(obj, dill.HIGHEST_PROTOCOL))

        def get_recommendation():
            # TODO: catch this potential error
            recommend_list = list(obj_decode(self.recommend_redis.get((e.source.nick, user_mode, "rec_list"))).items())
            try:
                recommended = recommend_list[int(self.recommend_redis[e.source.nick, user_mode, "i"])]
            except IndexError:
                self.bot.msg(e.source.nick, "No more recommendations. Try !r reset")
                raise IndexError

            # start parsing data
            try:
                beatmap_data, beatmap_data_api, mode = self.get_data(e, recommended[0])

                if mode == slider.GameMode.taiko:
                    pp_args = tuple(OrderedDict(acc=i, miss=0)
                                    for i in numpy.arange(1., .97, -0.01))
                elif mode == slider.GameMode.ctb:
                    pp_args = tuple(OrderedDict(acc=i, player_combo=beatmap_data_api.max_combo, miss=0)
                                    for i in numpy.arange(1., .98, -0.005))
                elif mode == slider.GameMode.mania:
                    pp_args = tuple(OrderedDict(score=i)
                                    for i in range(1_000_000, 900_000, -25_000))
                else:
                    return tl("osu.mode_invalid", self.bot.user_pref[e.source.nick].locale)

                osu_user.last_beatmap = (beatmap_data, beatmap_data_api, mode, recommended[0])

                self.bot.msg(e.source.nick,
                             self.format_message(
                                 beatmap_data, beatmap_data_api, mode, pp_args, recommend=f"Confidence {recommended[1]}"
                             ))
            except:
                logger.exception("")
                self.bot.msg(e.source.nick, "ParseError: contact the bot author")

            self.recommend_redis.incr((e.source.nick, user_mode, "i"))

        def iterate_maps_callback(result):
            _temp_list.extend(result)

            # progress tracker lmao
            finish_deferred.append(0)
            logger.debug(f"*finished: {len(finish_deferred)} / {len(user_top_plays)}")
            if len(finish_deferred) % 3 == 0:
                self.bot.msg(e.source.nick, "Progress: " +
                             ("█" * (len(finish_deferred) // 3)) + ("░" * ((rec_num - len(finish_deferred)) // 3)))

            if len(finish_deferred) == len(user_top_plays):
                # count instances
                map_counter.update(_temp_list)
                logger.debug(f"Osu.iterate_maps_callback | count {map_counter}")
                # convert to ordered dict and then sort
                map_ordered_dict = OrderedDict(sorted(map_counter.items(), key=operator.itemgetter(1), reverse=True))
                logger.debug(f"Osu.iterate_maps_callback | convert {map_ordered_dict}")
                # cull those already played
                for i in user_top_plays:
                    map_ordered_dict.pop(i.beatmap_id, None)
                logger.debug(f"Osu.iterate_maps_callback | cull played {map_ordered_dict}")
                # retain 200 maps
                map_ordered_dict = OrderedDict(islice(map_ordered_dict.items(), 200))
                logger.debug(f"Osu.iterate_maps_callback | retain 200 {map_ordered_dict}")

                self.recommend_redis.set((e.source.nick, user_mode, "rec_list"), obj_encode(map_ordered_dict),
                                         ex=60 * 60 * 24 * 30)
                self.recommend_redis.set((e.source.nick, user_mode, "i"), 0)

                get_recommendation()

        def iterate_maps_errback(failure):
            try:
                failure.raiseException()
            except:
                logger.exception("IterMap Exception")

        def gen_rec_from_top_play(top_play, pp_limits):
            pp_limit_lower, pp_limit_upper = pp_limits
            client = self.osu_api_client.copy()

            # progress tracker lmao
            start_deferred.append(0)
            logger.debug(f"started: {len(start_deferred)} / {len(user_top_plays)}")

            beatmap_high_scores = sorted(client.beatmap_best(beatmap_id=top_play.beatmap_id, game_mode=game_mode),
                                         key=lambda x: abs(x.pp - top_play.pp))[:20]
            # through map top plays
            total_scores = []
            for beatmap_high_score in beatmap_high_scores:
                # get user who got high score's top plays and filter, if rank S or better and within pp tolerances
                user_high_scores = \
                    sorted(
                        filter(
                            lambda k: (k.rank in ["S", "X", "SH", "XH"]) and (pp_limit_lower <= k.pp <= pp_limit_upper),
                            client.user_best(user_id=beatmap_high_score.user_id, game_mode=game_mode)
                        ),
                        key=lambda x: abs(x.pp - top_play.pp)
                    )[:20]
                total_scores.extend([k.beatmap_id for k in user_high_scores])

            logger.debug(f"Osu.gen_rec_from_top_play | result: {total_scores}")
            return total_scores

        def iterate_map(pp_limits):
            rec_thread_pool = threadpool.ThreadPool(min_threads, max_threads, "recommendations: " + e.source.nick)
            for top_play in user_top_plays:
                # single thread
                # iterate_maps_callback(gen_rec_from_top_play(top_play))

                # multi-thread
                d = threads.deferToThreadPool(reactor, rec_thread_pool, gen_rec_from_top_play, top_play, pp_limits)
                d.addCallback(iterate_maps_callback)
                d.addErrback(iterate_maps_errback)
            rec_thread_pool.start()
            rec_thread_pool.stop()

        # ---

        user_mode = self.bot.user_pref[e.source.nick].mode

        try:
            # if recommendations already exist
            if obj_decode(self.recommend_redis.get((e.source.nick, user_mode, "rec_list"))):
                get_recommendation()
                return
            else:
                # progress tracker (I was lazy, OK?)
                start_deferred = []
                finish_deferred = []

                _temp_list = []  # sometimes i hate how assignment and mutation works
                map_counter = Counter()

                game_mode = slider.GameMode(user_mode)
                osu_user.user_client = self.osu_api_client.user(user_name=e.source.nick, game_mode=game_mode)

                user_top_plays = osu_user.user_client.high_scores(limit=rec_num)
                osu_user.top_plays[user_mode] = user_top_plays
                if not len(user_top_plays):
                    self.bot.msg(e.source.nick, "You have no top plays.")
                    return

                pp_list = [i.pp for i in user_top_plays]

                try:
                    logger.debug("Generating recommendations")
                    self.bot.msg(e.source.nick, "Generating recommendations, this may take a while...")
                    iterate_map((sum(pp_list) / float(len(pp_list)), (sum(pp_list) / float(len(pp_list)) * 1.25)))
                except:
                    logger.exception("Rec Exception")
                    self.bot.msg(e.source.nick, "RecommendError: Unknown")
        except Exception:
            logger.exception("")

    @command(aliases=["action"])
    @requires_args
    def np(self, e):
        osu_user = self.bot.users.setdefault(e.source.nick, OsuUser(e.source.nick))
        osu_user.last_mod = False
        osu_user.last_kwargs = False

        url_extractor = urlextract.URLExtract()
        url_extractor.set_stop_chars_left(url_extractor.get_stop_chars_left() | {'['})
        url_extractor.set_stop_chars_right(url_extractor.get_stop_chars_right() | {']'})
        link_str = url_extractor.find_urls(' '.join(e.arguments))
        if not link_str:
            return tl("osu.link_invalid", self.bot.user_pref[e.source.nick].locale)
        link = urllib.parse.urlparse(link_str[0])
        if link.path.split("/")[1] == "b":
            beatmap_id = link.path.split("/")[2].split("&")[0]
        elif link.path.split("/")[1] == "beatmapsets" and link.fragment.split("/")[1].isdigit():
            beatmap_id = link.fragment.split("/")[1]
        else:
            return tl("osu.beatmapset", self.bot.user_pref[e.source.nick].locale)
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        try:
            beatmap_data, beatmap_data_api, mode = self.get_data(e, beatmap_id, np=True)
        except ValueError:
            return tl("osu.no_beatmap", self.bot.user_pref[e.source.nick].locale)
        except MissingPreferenceError:
            return
        if mode == slider.GameMode.standard:
            return tl("osu.mode_invalid", self.bot.user_pref[e.source.nick].locale)

        osu_user.last_beatmap = beatmap_id
        self.bot.users[e.source.nick] = osu_user

        if mode == slider.GameMode.taiko:
            pp_args = tuple(OrderedDict(acc=i, miss=0)
                            for i in numpy.arange(1., .97, -0.01))
        elif mode == slider.GameMode.ctb:
            pp_args = tuple(OrderedDict(acc=i, player_combo=beatmap_data_api.max_combo, miss=0)
                            for i in numpy.arange(1., .98, -0.005))
        elif mode == slider.GameMode.mania:
            pp_args = tuple(OrderedDict(score=i)
                            for i in range(1_000_000, 900_000, -25_000))
        else:
            return tl("osu.mode_invalid", self.bot.user_pref[e.source.nick].locale)

        return self.format_message(beatmap_data, beatmap_data_api, mode, pp_args)

    @command(aliases=["recent", "lastplay"])
    def replay(self, e):
        osu_user = self.bot.users.setdefault(e.source.nick, OsuUser(e.source.nick))
        osu_user.last_mod = False
        osu_user.last_kwargs = False

        mode = check_mode_in_db(e.source, self.bot, 0)
        if mode == -1:
            raise MissingPreferenceError

        recent = []
        if len(e.arguments) > 1:
            if slider.GameMode.parse(e.arguments[1]):
                recent = self.osu_api_client.user_recent(user_name=e.source.nick,
                                                         game_mode=slider.GameMode.parse(e.arguments[1]),
                                                         limit=1)
        else:
            recent.extend(self.osu_api_client.user_recent(user_name=e.source.nick,
                                                          game_mode=mode,
                                                          limit=1))

        logger.debug(f"Osu.replay | recent plays: {recent}")
        if not recent:
            return self.bot.msg(e.source.nick, tl("osu.no_recent", self.bot.user_pref[e.source.nick].locale))

        recent = sorted(recent, key=lambda beatmap: beatmap.date, reverse=True)[0]
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        beatmap_data, beatmap_data_api, mode = self.get_data(e, recent.beatmap_id)
        if not beatmap_data:
            return
        if mode == slider.GameMode.standard:
            return self.bot.msg(e.source.nick, tl("osu.mode_invalid", self.bot.user_pref[e.source.nick].locale))

        acc = self.get_accuracy(recent, mode)
        miss = recent.count_miss
        player_combo = recent.max_combo
        score = recent.score
        if mode == slider.GameMode.taiko:
            pp_args = OrderedDict(acc=acc, miss=miss)
        elif mode == slider.GameMode.ctb:
            pp_args = OrderedDict(acc=acc, player_combo=player_combo, miss=miss)
        elif mode == slider.GameMode.mania:
            pp_args = OrderedDict(score=score)
        else:
            return self.bot.msg(e.source.nick, tl("osu.mode_invalid", self.bot.user_pref[e.source.nick].locale))
        pp_args["mods"] = sum(recent.mods)

        osu_user.last_beatmap = recent.beatmap_id
        self.bot.users[e.source.nick] = osu_user

        self.bot.msg(e.source.nick, Osu.format_message(beatmap_data, beatmap_data_api, mode, (pp_args,)))

    @command(aliases=["with"], include_funcname=False)
    def cmd_with(self, e):
        if e.source.nick not in self.bot.users:
            return self.bot.msg(e.source.nick, tl("osu.no_np", self.bot.user_pref[e.source.nick].locale))

        osu_user = self.bot.users[e.source.nick]

        beatmap_id = osu_user.last_beatmap
        beatmap_data, beatmap_data_api, mode = self.get_data(e, beatmap_id)
        if mode == slider.GameMode.standard:
            return self.bot.msg(e.source.nick, tl("osu.mode_invalid", self.bot.user_pref[e.source.nick].locale))

        # region mod_header
        # checks for former acm (accuracy combo miss) data if any
        pp_args = osu_user.last_kwargs if osu_user.last_kwargs else False

        all_mods = numpy.uint32(slider.Mod.parse('ezhrhtdthdflsonf1k2k3k4k5k6k7k8k9k'))
        # reads args of message
        try:
            if e.arguments[1].lower() == "nm":
                mods = 0
            else:
                mods = slider.Mod.parse(e.arguments[1]) & all_mods
        except ValueError:
            return self.bot.msg(e.source.nick, tl("osu.mod_invalid", self.bot.user_pref[e.source.nick].locale))

        # sets mod names for output
        osu_user.last_mod = mods

        # checks if mods are supported
        sup_mods = ["", "nfezhdhrfl", "hdfl", "nfez"]
        if beatmap_data.mode == 0:
            sup_mods[3] = "nfez1k2k3k4k5k6k7k8k9k"
        uns_mod = mods & ~numpy.uint32(slider.Mod.parse(sup_mods[mode]))
        if uns_mod:
            return self.bot.msg(e.source.nick, tl("osu.mod_unsupported", self.bot.user_pref[e.source.nick].locale)
                                .format(f": \"{slider.Mod.serialize(uns_mod)}\","))

        # endregion

        # region mode specific stuff
        if pp_args is False:
            if mode == slider.GameMode.taiko:  # all mods as of now
                pp_args = OrderedDict(acc=1., miss=0, mods=mods)
            elif mode == slider.GameMode.ctb:  # hd and fl
                pp_args = OrderedDict(acc=1., player_combo=beatmap_data_api.max_combo, miss=0, mods=mods)
            elif mode == slider.GameMode.mania:  # nf and ez only
                pp_args = OrderedDict(score=1000000, mods=mods)
            else:
                return self.bot.msg(e.source.nick, tl("osu.mode_invalid", self.bot.user_pref[e.source.nick].locale))
        # endregion

        self.bot.msg(e.source.nick, Osu.format_message(beatmap_data, beatmap_data_api, mode, (pp_args,)))

    @command
    def acc(self, e):
        if e.source.nick not in self.bot.users:
            return self.bot.msg(e.source.nick, tl("osu.no_np", self.bot.user_pref[e.source.nick].locale))

        osu_user = self.bot.users[e.source.nick]

        beatmap_id = osu_user.last_beatmap
        beatmap_data, beatmap_data_api, mode = self.get_data(e, beatmap_id)
        if mode == slider.GameMode.standard:
            return self.bot.msg(e.source.nick, tl("osu.mode_invalid", self.bot.user_pref[e.source.nick].locale))

        max_combo = int(beatmap_data_api.max_combo) if beatmap_data_api.max_combo else int(beatmap_data.max_combo)

        # region acc_header
        # reads args of message
        pp_args = OrderedDict(acc=None, player_combo=None, miss=None, score=None)
        for arg in e.arguments:
            if is_type(float, arg.replace(",", ".")) or arg.endswith(("%",)):
                pp_args["acc"] = float(arg.replace("%", "").replace(",", ".")) / 100
            elif arg.endswith(("x",)):
                pp_args["player_combo"] = int(arg.rstrip("x"))
            elif arg.endswith(("m",)):
                pp_args["miss"] = int(arg.rstrip("m"))
            elif arg.endswith(("s",)):
                pp_args["score"] = int(arg.rstrip("s"))
        # endregion

        # region mode specific stuff
        err_str = None
        min_max = {
            "acc":          (0, 1),
            "player_combo": (0, max_combo),
            "miss":         (0, max_combo),
            "score":        (0, 1_000_000)
        }
        defaults = {
            "acc":          1,
            "player_combo": max_combo,
            "miss":         0,
            "score":        1_000_000
        }

        if mode in (slider.GameMode.taiko, slider.GameMode.ctb):
            err_str = Osu.check_arg(pp_args, min_max, defaults, "acc") if not err_str else err_str
            err_str = Osu.check_arg(pp_args, min_max, defaults, "miss") if not err_str else err_str
        if mode == slider.GameMode.ctb:
            err_str = Osu.check_arg(pp_args, min_max, defaults, "player_combo") if not err_str else err_str
        elif mode == slider.GameMode.mania:
            err_str = Osu.check_arg(pp_args, min_max, defaults, "score") if not err_str else err_str

        for arg in pp_args:
            if pp_args[arg] is None:
                del pp_args[arg]
        # endregion

        if err_str:
            return tl(err_str, self.bot.user_pref[e.source.nick].locale)

        # checks for former mod data if any
        pp_args["mods"] = 0 if not osu_user.last_mod else osu_user.last_mod
        osu_user.last_kwargs = pp_args

        self.bot.msg(e.source.nick, Osu.format_message(beatmap_data, beatmap_data_api, mode, (pp_args,)))

    @command(aliases=["u"])
    def update(self, e):
        return

        # user = e.arguments[1] if len(e.arguments) > 1 else e.source.nick
        # logging.debug(user)
        # r = requests.get(f'https://ameobea.me/osutrack/api/get_changes.php'
        #                  f'?user={user}&mode={bot.user_pref[e.source.nick].mode}')

    @staticmethod
    def check_arg(pp_args, min_max, defaults, key):
        if pp_args[key] is None:
            pp_args[key] = defaults[key]
        if not min_max[key][0] <= pp_args[key] <= min_max[key][1]:
            return f"osu.{key}_error"


class OsuUser:
    def __init__(self, username):
        self.username = username
        self.user_client = None
        self.last_beatmap = None
        self.last_mod = None
        self.last_kwargs = None
        self.top_plays = [-1, None, None, None]  # per mode, will be arrays
