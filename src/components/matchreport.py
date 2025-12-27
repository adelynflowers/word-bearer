"""
Holds the modal for match result submission.
"""

import discord
import discord.ui as ui
import traceback
from pydantic import BaseModel, Field
from typing import Callable
from datetime import datetime
from zoneinfo import ZoneInfo
from loguru import logger


class MatchSubmission(BaseModel):
    """
    Holds the data from the modal fields.
    """

    player_name: str = Field(validation_alias="player_name")
    opponent_name: str = Field(validation_alias="opponent_name")
    league_name: str = Field(validation_alias="league_name")
    player_won: bool = Field(validation_alias="player_won")
    was_draw: bool = Field(validation_alias="was_draw")
    notes: str = Field(validation_alias="notes")
    timestamp: int = Field(validation_alias="timestamp")


class MatchReport(discord.ui.Modal, title="Match Report"):
    """
    A modal that can be used to submit match results.
    """

    submission_callback: Callable[[MatchSubmission], None]

    def set_callback(self, callback: Callable[[MatchSubmission], None]):
        self.submission_callback = callback

    def set_leagues(self, leagues: list[str]):
        assert isinstance(self.league_select.component, ui.Select)
        self.league_select.component.options = [
            discord.SelectOption(label=league) for league in leagues
        ]

    user_select = ui.Label(
        text="Your Opponent",
        component=ui.UserSelect(
            placeholder="",
            min_values=1,
            max_values=1,
            required=True,
        ),
    )

    league_select = discord.ui.Label(
        text="Which league is this for?",
        component=discord.ui.Select(
            placeholder="",
            options=[discord.SelectOption(label=league) for league in ["N/A"]],
        ),
    )

    victor = discord.ui.Label(
        text="Who won?",
        component=discord.ui.Select(
            placeholder="",
            options=[
                discord.SelectOption(
                    label="Me"
                ),  # TODO: Use StrEnum to get rid of magic strings
                discord.SelectOption(label="My opponent"),
                discord.SelectOption(label="It was a draw"),
            ],
        ),
    )

    feedback = discord.ui.TextInput(
        label="Additional comments",
        style=discord.TextStyle.long,
        placeholder="Additional information, if you have any",
        required=False,
        max_length=300,
    )

    def _create_result(self, interaction: discord.Interaction) -> MatchSubmission:
        player = interaction.user.name
        assert isinstance(self.user_select.component, ui.UserSelect)
        assert isinstance(self.victor.component, ui.Select)
        assert isinstance(self.league_select.component, ui.Select)
        opponent = self.user_select.component.values[0].name
        victor = self.victor.component.values[0]
        player_won: bool = victor == "Me"
        draw: bool = victor == "It was a draw"
        feedback = self.feedback.value
        league = self.league_select.component.values[0]
        result = MatchSubmission(
            player_name=player,
            opponent_name=opponent,
            league_name=league,
            player_won=player_won,
            was_draw=draw,
            notes=feedback,
            timestamp=int(datetime.now(tz=ZoneInfo("UTC")).timestamp()),
        )
        return result

    async def on_submit(self, interaction: discord.Interaction) -> None:
        result = self._create_result(interaction)
        logger.info(f"Result submitted: {result}")
        self.submission_callback(result)
        await interaction.response.send_message(
            "Your match results have been submitted!", ephemeral=True
        )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        await interaction.response.send_message(
            "Oops! Something went wrong. Please alert adelyn if this was unexpected.",
            ephemeral=True,
        )

        # Make sure we know what the error actually is
        traceback.print_exception(type(error), error, error.__traceback__)
