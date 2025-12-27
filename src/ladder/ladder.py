"""
Holds abstract ladder league logic.
"""

from dataclasses import dataclass
from enum import IntEnum
import math
from datetime import datetime
from typing import Callable, Sequence
from abc import ABC, abstractmethod

INITIAL_POINTS = 10


class LadderPeriod(IntEnum):
    """
    The number of days that consist of one period, used for
    period restricted point accumulation.
    """

    WEEKLY = 7


@dataclass
class LadderConfig:
    """
    Configuration required for
    compute logic.
    """

    start_date: datetime
    end_date: datetime
    period: LadderPeriod
    games_per_period: int


class LadderResult(ABC):
    """
    An interface for objects that store
    the results of a Ladder League match.
    """

    @abstractmethod
    def player_name(self) -> str:
        pass

    @abstractmethod
    def opponent_name(self) -> str:
        pass

    @abstractmethod
    def player_won(self) -> bool:
        pass

    @abstractmethod
    def player_vp(self) -> int:
        pass

    @abstractmethod
    def opponent_vp(self) -> int:
        pass

    @abstractmethod
    def was_draw(self) -> bool:
        pass

    @abstractmethod
    def match_date(self) -> datetime:
        pass


@dataclass
class LadderPlayer:
    """
    Stores data about an individual player
    in a ladder league.
    """

    name: str
    games_played: int
    games_won: int
    games_drawn: int
    opponents_played: list[str]
    total_vp: int
    ladder_points: int
    match_periods: dict[int, int]

    def __init__(self, name: str, initial_points: int):
        self.ladder_points = initial_points
        self.name = name
        self.games_played = 0
        self.games_won = 0
        self.games_drawn = 0
        self.opponents_played = []
        self.total_vp = 0
        self.match_periods = {}


def period_of_date(d: datetime, c: LadderConfig):
    """
    Determines the numeric period (0+) of a date given
    the configuration for the league
    """
    result_diff = d - c.start_date
    if c.period == LadderPeriod.WEEKLY:
        period = result_diff.days % 7
        return period
    else:
        raise RuntimeError(
            f"Period determination not implemented for {LadderConfig.period}"
        )


def update_players_basic(
    a: LadderPlayer, b: LadderPlayer, result: LadderResult, config: LadderConfig
) -> None:
    """
    Uses two players and a result about them to update the player objects.

    Ladder logic:
         - Only first game per period counts
         - +1 per game played
         - +1 per win
         - 1/2 of gap if win vs higher opp on ladder
         - +1 for playing new opponent
    """
    result_period = period_of_date(result.match_date(), config)
    a_played = result_period in a.match_periods and a.match_periods[result_period] > 0
    b_played = result_period in b.match_periods and b.match_periods[result_period] > 0

    a_addtl_lp = 0
    b_addtl_lp = 0
    a.games_played += 1
    b.games_played += 1
    a.total_vp += result.player_vp()
    b.total_vp += result.opponent_vp()
    if result.player_won():
        a.games_won += 1
        # Play + win
        if b.ladder_points > a.ladder_points:
            gap = b.ladder_points - a.ladder_points
            a_addtl_lp += math.ceil(gap / 2)
        a_addtl_lp += 2
        # Play
        b_addtl_lp += 1
    elif result.was_draw():
        a.games_drawn += 1
        b.games_drawn += 1
        # Play
        a_addtl_lp += 1
        b_addtl_lp += 1
    else:
        b.games_won += 1
        # Play + win
        if a.ladder_points > b.ladder_points:
            gap = a.ladder_points - b.ladder_points
            b_addtl_lp += math.ceil(gap / 2)
        b_addtl_lp += 2
        # Play
        a_addtl_lp += 1
    # New matchup
    if result.opponent_name() not in a.opponents_played:
        a.opponents_played.append(result.opponent_name())
        b.opponents_played.append(result.player_name())
        a.ladder_points += 1
        b.ladder_points += 1
    if not a_played:
        a.ladder_points += a_addtl_lp
        a.match_periods[result_period] = 0
    if not b_played:
        b.ladder_points += b_addtl_lp
        b.match_periods[result_period] = 0
    a.match_periods[result_period] += 1
    b.match_periods[result_period] += 1


def compute_standings(
    results: Sequence[LadderResult],
    config: LadderConfig,
    updater: Callable[[LadderPlayer, LadderPlayer, LadderResult, LadderConfig], None],
) -> list[LadderPlayer]:
    """Computes the current standings for a ladder league.

    Args:
        results (Sequence[LadderResult]): The list of results that compose the league
        config (LadderConfig): The configuration of the league
        updater (Callable[[LadderPlayer, LadderPlayer, LadderResult, LadderConfig], None]): The update logic used to compute standings

    Returns:
        list[LadderPlayer]: A list of the players involved in the league with their league stats computed
    """
    player_map: dict[str, LadderPlayer] = {}
    for result in results:
        if result.player_name() not in player_map:
            player_map[result.player_name()] = LadderPlayer(
                result.player_name(), INITIAL_POINTS
            )
        if result.opponent_name() not in player_map:
            player_map[result.opponent_name()] = LadderPlayer(
                result.opponent_name(), INITIAL_POINTS
            )
        updater(
            player_map[result.player_name()],
            player_map[result.opponent_name()],
            result,
            config,
        )
    return list(player_map.values())
