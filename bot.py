"""Discord bot that watches Star Cineplex movies and reports ticket sales."""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta

import discord
from discord.ext import commands, tasks

import config
from cineplex_API import CineplexAPI, Movie, Show

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class Watch:
    query: str
    channel: discord.abc.Messageable
    hall_names: tuple[str, ...] = ()
    include_3d: bool = False
    mention: str = ""
    notified: bool = False


class CineplexBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=config.COMMAND_PREFIX, intents=intents)
        self.api = CineplexAPI()
        self.watches: dict[tuple[int, str], Watch] = {}
        self.channel_halls: dict[int, tuple[str, ...]] = {}

    async def setup_hook(self) -> None:
        self.poll_watches.start()

    async def on_ready(self) -> None:
        logger.info("Logged in as %s", self.user)

    @tasks.loop(seconds=config.POLL_INTERVAL)
    async def poll_watches(self) -> None:
        for key, watch in list(self.watches.items()):
            if watch.notified:
                continue
            try:
                movies = await asyncio.to_thread(self.api.find_movies, watch.query)
                for movie in movies:
                    selling = await asyncio.to_thread(
                        self.api.selling_shows,
                        movie.id,
                        self._watch_dates(),
                        watch.hall_names,
                        watch.include_3d,
                    )
                    if selling:
                        await watch.channel.send(
                            f"{watch.mention} {self._format_alert(movie, selling)}".strip()
                        )
                        watch.notified = True
                        break
            except Exception:
                logger.exception("Watch check failed for %r", watch.query)

    @poll_watches.before_loop
    async def before_poll_watches(self) -> None:
        await self.wait_until_ready()

    @staticmethod
    def _watch_dates() -> set[str]:
        today = date.today()
        return {(today + timedelta(days=offset)).isoformat() for offset in range(3)}

    @staticmethod
    def _format_alert(
        movie: Movie, selling: list[tuple[Show, str]]
    ) -> str:
        lines = [f"🎟️ **Tickets are now selling: {movie.title}**"]
        for show, venue in selling[:10]:
            lines.append(
                f"• {venue} — {show.date} {show.time} ({show.format or 'standard'}), "
                f"{show.available_seats}/{show.total_seats} seats"
                f"\n  {CineplexAPI.booking_url(show.id)}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_available(
        movie: Movie, selling: list[tuple[Show, str]]
    ) -> str:
        today = date.today().isoformat()
        lines = [f"🎟️ **Available tickets for {movie.title}**"]
        dates = sorted({show.date for show, _ in selling})
        if today not in dates:
            lines.append("No ticket available for today; showing the next available date.")
        for show, venue in selling[:10]:
            lines.append(
                f"• {venue} — {show.date} {show.time} ({show.format or 'standard'}), "
                f"{show.available_seats}/{show.total_seats} seats"
                f"\n  {CineplexAPI.booking_url(show.id)}"
            )
        return "\n".join(lines)

    @staticmethod
    def _earliest_available(
        selling: list[tuple[Show, str]]
    ) -> list[tuple[Show, str]]:
        if not selling:
            return []
        earliest_date = min(show.date for show, _ in selling)
        return [(show, venue) for show, venue in selling if show.date == earliest_date]


bot = CineplexBot()


@bot.command(name="watch")
async def watch_movie(ctx: commands.Context, *, movie_name: str) -> None:
    await _run_watch(ctx, movie_name)


@bot.command(name="3d")
async def watch_movie_with_3d(ctx: commands.Context, *, movie_name: str) -> None:
    await _run_watch(ctx, movie_name, include_3d=True)


async def _run_watch(
    ctx: commands.Context, movie_name: str, include_3d: bool = False
) -> None:
    query, inline_hall_names, inline_3d = _split_watch_options(movie_name)
    include_3d = include_3d or inline_3d
    query = query.strip()
    if not query:
        await ctx.send(f"Usage: `{config.COMMAND_PREFIX}watch movie name`")
        return

    try:
        movies = await asyncio.to_thread(bot.api.find_movies, query)
    except Exception:
        logger.exception("Movie lookup failed")
        await ctx.send("I could not reach Star Cineplex right now. I will keep the bot running; try again shortly.")
        return

    if not movies:
        await ctx.send(f"No current or upcoming Star Cineplex movie matched **{query}**.")
        return
    if len(movies) > 1:
        titles = "\n".join(f"• {movie.title}" for movie in movies[:10])
        await ctx.send(f"More than one movie matched. Be more specific:\n{titles}")
        return

    hall_names = bot.channel_halls.get(ctx.channel.id, ())
    if inline_hall_names:
        try:
            venues = await asyncio.to_thread(bot.api.venues)
        except Exception:
            logger.exception("Inline hall lookup failed")
            await ctx.send("I could not load the Dhaka halls right now. Please try again shortly.")
            return
        hall_names = tuple(
            venue["name"]
            for venue in venues
            if any(
                name.casefold() in venue["name"].casefold()
                for name in inline_hall_names
            )
        )
        if not hall_names:
            await ctx.send("No matching Dhaka hall found. Use `!hall` to see valid hall names.")
            return
        bot.channel_halls[ctx.channel.id] = hall_names
    try:
        selling = await asyncio.to_thread(
            bot.api.selling_shows,
            movies[0].id,
            bot._watch_dates(),
            hall_names,
            include_3d,
        )
    except Exception:
        logger.exception("Initial ticket lookup failed")
        await ctx.send("I could not reach Star Cineplex right now. Please try again shortly.")
        return
    if selling:
        await ctx.send(bot._format_available(movies[0], bot._earliest_available(selling)))
        return

    key = (ctx.channel.id, query.casefold())
    bot.watches[key] = Watch(
        query=query,
        channel=ctx.channel,
        hall_names=hall_names,
        include_3d=include_3d,
        mention=ctx.author.mention,
    )
    await ctx.send(
        "No ticket for today, tomorrow, or the day after tomorrow. "
        f"I'm watching for tickets every {config.POLL_INTERVAL}s, whenever it drops, "
        f"I'll mention you {ctx.author.mention}."
    )


def _split_watch_options(value: str) -> tuple[str, list[str], bool]:
    include_3d = bool(re.search(r"\s*!3d\b", value, flags=re.IGNORECASE))
    value = re.sub(r"\s*!3d\b", "", value, flags=re.IGNORECASE)
    parts = re.split(r"\s*!hall\b", value, flags=re.IGNORECASE)
    query = parts[0]
    hall_names = [part.strip() for part in parts[1:] if part.strip()]
    return query, hall_names, include_3d


@bot.command(name="hall")
async def select_halls(ctx: commands.Context, *, hall_names: str = "") -> None:
    """Select one or more halls for future !watch commands in this channel."""
    raw_names = [name.strip() for name in hall_names.split("!") if name.strip()]
    if not raw_names:
        bot.channel_halls.pop(ctx.channel.id, None)
        await ctx.send("Hall filter cleared. Searches now include available Dhaka halls.")
        return

    try:
        venues = await asyncio.to_thread(bot.api.venues)
    except Exception:
        logger.exception("Hall lookup failed")
        await ctx.send("I could not load the Dhaka halls right now. Please try again shortly.")
        return
    selected = tuple(
        venue["name"]
        for venue in venues
        if any(name.casefold() in venue["name"].casefold() for name in raw_names)
    )
    if not selected:
        available = "\n".join(f"• {venue['name']}" for venue in venues)
        await ctx.send(f"No matching Dhaka hall found. Available halls:\n{available}")
        return

    bot.channel_halls[ctx.channel.id] = selected
    await ctx.send("Hall filter set to: " + ", ".join(selected))


@bot.command(name="unwatch")
async def unwatch_movie(ctx: commands.Context, *, movie_name: str) -> None:
    key = (ctx.channel.id, movie_name.strip().casefold())
    if bot.watches.pop(key, None):
        await ctx.send(f"Stopped watching **{movie_name.strip()}**.")
    else:
        await ctx.send("That movie is not being watched in this channel.")


@bot.command(name="watching")
async def watching(ctx: commands.Context) -> None:
    names = [
        watch.query
        for (channel_id, _), watch in bot.watches.items()
        if channel_id == ctx.channel.id and not watch.notified
    ]
    await ctx.send(
        "Watching: " + ", ".join(names) if names else "This channel is not watching any movies."
    )


if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing from .env")
    bot.run(config.DISCORD_TOKEN)
