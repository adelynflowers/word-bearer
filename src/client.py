"""
Holds the command and client classes for the discord bot.
"""

from datetime import datetime
import discord
from discord import app_commands
from discord.ext import tasks
from components.matchreport import MatchReport, MatchSubmission
from components.messagejob import MessageJobHandler
from ladder.manager import LadderManager, DiscordLadderResult, IsoWeekday
from ladder.ladder import LadderConfig, LadderPeriod
from loguru import logger
from zoneinfo import ZoneInfo
from typing import Callable
from pydantic import BaseModel
from pathlib import Path
import json


def adapt_submission(submission: MatchSubmission) -> DiscordLadderResult:
    """Adapts a MatchSubmission to a DiscordLadderResult

    Args:
        submission (MatchSubmission): input instance

    Returns:
        DiscordLadderResult: From the information in the input
    """
    return DiscordLadderResult(
        player=submission.player_name,
        opponent=submission.opponent_name,
        time=submission.timestamp,
        vp_player=0,
        vp_opponent=0,
        draw=submission.was_draw,
        player_victory=submission.player_won,
        league_name=submission.league_name,
    )


class LeagueConfig(BaseModel):
    """
    Pydantic class for league configs, which
    are retrieved from json files.
    """

    start_date: datetime
    end_date: datetime
    league_name: str
    channel_id: int
    posting_day: int


class WordBearerClient(discord.Client):
    """
    Primary class that holds the discord client logic.
    """

    user: discord.ClientUser
    message_handler: MessageJobHandler
    leagues: dict[str, LadderManager] = {}
    league_dir: str

    def __init__(self, job_dir: str, finished_job_dir: str, league_dir: str) -> None:
        """
        Sets class members from passed values and then initializes the list of leagues.
        """
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.message_handler = MessageJobHandler(job_dir, finished_job_dir, self)
        self.league_dir = league_dir
        self._setup_leagues()

    def _setup_leagues(self):
        """
        Reads json files from the league directory and creates
        LadderManager instances from them. Currently periods are
        fixed to weekly.
        """
        for file in Path(self.league_dir).glob("*.json"):
            with file.open() as f:
                league_config = LeagueConfig.model_validate(json.load(f))
                ladder_config = LadderConfig(
                    start_date=league_config.start_date.astimezone(tz=ZoneInfo("UTC")),
                    end_date=league_config.end_date.astimezone(tz=ZoneInfo("UTC")),
                    period=LadderPeriod.WEEKLY,
                    games_per_period=1,
                )
                manager = LadderManager(
                    self,
                    ladder_config,
                    league_config.channel_id,
                    results_dir=str(Path(self.league_dir, "results")),
                    league_name=league_config.league_name,
                    config_dir=str(Path(self.league_dir, "messages")),
                    posting_day=IsoWeekday(league_config.posting_day),
                )
                self.leagues[manager.league_name] = manager

    def write_ladder_result(self, result: DiscordLadderResult) -> None:
        """Writes a ladder result to storage.

        Args:
            result (DiscordLadderResult): An individual result
        """
        if result.league_name in self.leagues:
            self.leagues[result.league_name].store_result(result)
        else:
            logger.warning(f"An orphaned result was submitted: {result}")

    async def on_ready(self):
        """
        Logs when bot is ready to begin.
        """
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")

    async def setup_hook(self) -> None:
        """
        Does pre-event loop initialization, including adding
        commands.
        """

        def submission_callback(s):
            self.write_ladder_result(adapt_submission(s))

        self.tree.add_command(
            MatchCommands(
                self, callback=submission_callback, managers=list(self.leagues.values())
            )
        )
        self.job_runner.start()
        await self.tree.sync()

    @tasks.loop(seconds=30)
    async def job_runner(self):
        """
        A 30 second job loop, used to send messages
        and post standings when needed.
        """
        await self.message_handler.run_jobs()
        for league in self.leagues.values():
            await league.post_standings()

    @job_runner.before_loop
    async def before_job_runner(self):
        """
        Ensures the discord connection is fully ready
        """
        await self.wait_until_ready()


class MatchCommands(app_commands.Group):
    """
    A class ("cog") that holds a set of commands
    that can be attached to a discord client.
    """

    managers: list[LadderManager] = []
    submission_callback: Callable[[MatchSubmission], None]

    def __init__(
        self,
        client: discord.Client,
        callback: Callable[[MatchSubmission], None],
        managers: list[LadderManager],
    ):
        super().__init__(name="match")
        self.client = client
        self.submission_callback = callback
        self.managers = managers

    def _active_leagues(self):
        """
        Checks league names that are currently running. If none
        are active, returns a dummy entry because the modal requires
        this as a field.
        """
        leagues = []
        now = datetime.now(tz=ZoneInfo("UTC"))
        for manager in self.managers:
            if now >= manager.config.start_date and now <= manager.config.end_date:
                leagues.append(manager.league_name)
        if len(leagues) == 0:
            leagues.append("No active leagues available")
        return leagues

    @app_commands.command(name="report", description="Submit match")
    async def report_match(self, interaction: discord.Interaction):
        """
        Creates a MatchReportModal and sends the results of the
        form submission to the supplied callback.
        """
        modal = MatchReport()
        modal.set_leagues(self._active_leagues())
        modal.set_callback(self.submission_callback)
        await interaction.response.send_modal(modal)
