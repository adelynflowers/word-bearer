"""
Holds classes that tie together the discord bot and the abstract ladder
compute logic.
"""

import discord
from ladder.ladder import (
    LadderResult,
    LadderConfig,
    LadderPlayer,
    compute_standings,
    update_players_basic,
)
import datetime
from zoneinfo import ZoneInfo
import csv
from pydantic import BaseModel, Field, ConfigDict
import os
import pathlib
from loguru import logger
from enum import IntEnum
import json


class DiscordLadderResult(BaseModel, LadderResult):
    """
    An implementation of LadderResult that fits the responses received
    from discord form submissions.
    """

    model_config = ConfigDict(populate_by_name=True)

    player: str = Field(validation_alias="player_name")
    opponent: str = Field(validation_alias="opponent_name")
    time: int = Field(validation_alias="timestamp")
    player_victory: bool = Field(validation_alias="player_won")
    draw: bool = Field(validation_alias="was_draw")
    vp_player: int = Field(validation_alias="player_vp")
    vp_opponent: int = Field(validation_alias="opponent_vp")
    league_name: str = Field(validation_alias="league_name")

    def player_name(self) -> str:
        return self.player

    def opponent_name(self) -> str:
        return self.opponent

    def player_won(self) -> bool:
        return self.player_victory

    def was_draw(self) -> bool:
        return self.draw

    def player_vp(self) -> int:
        return self.vp_player

    def opponent_vp(self) -> int:
        return self.vp_opponent

    def match_date(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.time, tz=ZoneInfo("UTC"))


class IsoWeekday(IntEnum):
    """
    An IntEnum representation that matches isoweekday in datetime
    for legibility and consistency.
    """

    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7


class LadderManager:
    """
    A class that sits between the discord bot and the abstract
    ladder logic. Handles the posting of league standings and the
    storage of results.
    """

    config: LadderConfig
    client: discord.Client
    results_path: pathlib.Path
    channel_id: int
    league_name: str
    config_file: pathlib.Path
    posting_day: IsoWeekday

    def __init__(
        self,
        client: discord.Client,
        config: LadderConfig,
        channel_id: int,
        results_dir: str,
        league_name: str,
        config_dir: str,
        posting_day: IsoWeekday,
    ):
        """Initializes the class and ensures parent directories are created.

        Args:
            client (discord.Client): The discord bot client instance for sending messages
            config (LadderConfig): A configuration instance for ladder logic
            channel_id (int): The channel that messages will be posted to
            results_dir (str): The directory where results will be stored
            league_name (str): The name of the league, used for file names
            config_dir (str): The directory where message records will be keptdaa
            posting_day (IsoWeekday): The day of the week messages should be posted
        """
        self.client = client
        self.config = config
        self.channel_id = channel_id
        self.league_name = league_name
        sanitized_name = league_name.lower().replace(" ", "-")
        self.config_file = pathlib.Path(
            config_dir, f"{sanitized_name}-message-record.json"
        )
        self.results_path = pathlib.Path(results_dir, f"{sanitized_name}-results.csv")
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.results_path.parent.mkdir(parents=True, exist_ok=True)
        self.posting_day = posting_day

    def _read_results(self) -> list[LadderResult]:
        """
        Reads the result file, creating a new one if
        it does not yet exist.
        """
        results: list[LadderResult] = []
        if not self.results_path.exists():
            with open(self.results_path, "w", newline="") as result_file:
                result_writer = csv.DictWriter(
                    result_file, DiscordLadderResult.model_fields
                )
                result_writer.writeheader()
        with open(self.results_path, newline="") as csvfile:
            result_reader = csv.DictReader(csvfile)
            for row in result_reader:
                result = DiscordLadderResult.model_validate(row)
                results.append(result)
        return results

    def _compute_standings(self) -> list[LadderPlayer]:
        """
        Passes the results to the ladder libraries compute function
        and returns the standings.
        """
        results = self._read_results()
        standings = compute_standings(results, self.config, update_players_basic)
        return standings

    def store_result(self, result: DiscordLadderResult) -> None:
        """Stores a single result on disk.

        Args:
            result (DiscordLadderResult): result to write
        """
        mode = "a"
        if not os.path.exists(self.results_path):
            mode = "w"
            pathlib.Path(self.results_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.results_path, mode, newline="") as result_file:
            result_writer = csv.DictWriter(
                result_file, DiscordLadderResult.model_fields
            )
            if mode == "w":
                result_writer.writeheader()
            result_writer.writerow(result.model_dump())

    async def post_standings(self):
        """
        Posts standings if it is the correct time and
        this week's message hasn't been posted already.
        """
        # is today after 5PM UTC (12 EST) on the weekday for posting messages, and before the end of
        # the league?
        now = datetime.datetime.now(tz=ZoneInfo("UTC"))
        valid_date = now <= self.config.end_date and now >= self.config.start_date
        valid_day = now.date().isoweekday() >= self.posting_day
        valid_time = now.hour >= 16
        if not (valid_day and valid_time and valid_date):
            return
        # is a record of this week's message present?
        need_to_post = True
        message_record = []
        if not self.config_file.exists():
            with open(self.config_file, "w") as file:
                json.dump(message_record, file)
        else:
            with open(self.config_file, "r") as file:
                message_record = json.load(file)
            for message in message_record:
                if str(message) == str(now.isocalendar()[1]):
                    need_to_post = False
        # if not, post it
        if need_to_post:
            await self._post_standings()
            message_record.append(now.isocalendar()[1])
            with open(self.config_file, "w") as file:
                json.dump(message_record, file)

    async def _post_standings(self) -> None:
        """
        Computes standings and sends a message.
        """
        standings = self._compute_standings()
        if len(standings) == 0:
            return
        standings.sort(key=lambda player: player.ladder_points, reverse=True)
        message = f"""## Ladder Standings for {self.league_name} 
*As of {datetime.datetime.now().strftime("%B %d, %Y")}*
        {"\n".join([f"- {player.name} ({player.ladder_points}) " for player in standings])}
        """
        channel = self.client.get_channel(self.channel_id)
        logger.info(f"{channel}: {type(channel)}")
        if not (
            isinstance(channel, discord.TextChannel)
            or isinstance(channel, discord.Thread)
        ):
            raise RuntimeError(
                f"LadderManager requested invalid channel: {self.config}"
            )
        await channel.send(content=message)
