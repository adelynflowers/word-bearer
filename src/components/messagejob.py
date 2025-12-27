"""
Holds the component which handles scheduled messaging.
"""

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import os
from loguru import logger
from zoneinfo import ZoneInfo
import discord
import shutil


@dataclass
class MessageJob:
    """
    Holds configuration for a scheduled
    message job.
    """

    id: str
    timestamp: datetime
    channel_id: int
    content: str
    files: list[str]


class MessageJobHandler:
    """
    Handles sending scheduled messages, and tracking
    which ones were sent to prevent duplicates.
    """

    job_dir: str = "/jobs"
    finished_dir: str = "/jobs/finished"
    jobs: dict[str, MessageJob] = {}
    client: discord.Client

    def __init__(self, job_dir: str, finished_dir: str, client: discord.Client):
        """Initializes the class

        Args:
            job_dir (str): The directory where scheduled job jsons live
            finished_dir (str): The directory where jsons are moved once the message is sent
            client (discord.Client): The discord bot client instance
        """
        self.job_dir = job_dir
        self.finished_dir = finished_dir
        self.client = client
        self._ensure_dirs()
        self._load_jobs()

    def _ensure_dirs(self):
        """
        Creates the queue/finished job directories
        """
        for dir in [self.job_dir, self.finished_dir]:
            Path(dir).mkdir(parents=True, exist_ok=True)

    async def _run_job(self, job: MessageJob):
        """Runs a job, sending the message. Does not do
        time/resend validation.

        Args:
            job (MessageJob): The job to complete

        Raises:
            RuntimeError: If the channel for the job isn't valid
        """
        logger.info(f"Running MessageJob with id {job.id}")
        channel = self.client.get_channel(job.channel_id)
        if not channel:
            return
        if not (
            isinstance(channel, discord.TextChannel)
            or isinstance(channel, discord.Thread)
        ):
            raise RuntimeError(f"Job requested invalid channel: {job}")
        files = [discord.File(path) for path in job.files]

        await channel.send(
            content=job.content,
            files=files,
            allowed_mentions=discord.AllowedMentions(
                users=True, roles=True, everyone=False
            ),
        )

    def _mark_done(self, job: MessageJob):
        """Moves a job from the queue to the finished
        directory so it won't be picked up on future restarts.

        Args:
            job (MessageJob): The job to archive
        """
        job_path = f"{self.job_dir}/{job.id}.json"
        self.jobs.pop(job.id, None)
        if os.path.exists(job_path):
            shutil.move(job_path, f"{self.finished_dir}/{job.id}.json")

    def _load_jobs(self):
        """
        Loads jobs from the queue directory
        """
        jobs = {}

        for file in Path(self.job_dir).glob("*.json"):
            with file.open() as f:
                raw = json.load(f)

            job = MessageJob(
                id=raw["id"],
                timestamp=datetime.fromtimestamp(
                    int(raw["timestamp"]), tz=ZoneInfo("UTC")
                ),
                channel_id=int(raw["channel_id"]),
                content=raw["content"],
                files=raw.get("files", []),
            )

            jobs[job.id] = job
        logger.info(f"{len(jobs)} jobs loaded")
        self.jobs = jobs

    async def run_jobs(self):
        """
        Check if messages are due to be sent. For any that are,
        send them and then archive them.
        """
        now = datetime.now(ZoneInfo("UTC"))
        due = [job for job in self.jobs.values() if job.timestamp <= now]

        for job in due:
            await self._run_job(job)
            self._mark_done(job)
