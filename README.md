# Star Cineplex Discord ticket watcher

This bot accepts a movie title in Discord and checks Star Cineplex's live catalog and showtime APIs until tickets begin selling. It then sends one message to the channel where the watch was created, including the venue, showtime, available seats, and booking link.

## Setup

1. Create a Discord application and bot in the [Discord Developer Portal](https://discord.com/developers/applications). Enable the **Message Content Intent**, copy the bot token, and invite the bot with `Send Messages` and `Read Message History`.
2. Install dependencies:

   ```powershell
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and set `DISCORD_TOKEN`.
4. Start the bot:

   ```powershell
   .\venv\Scripts\python.exe bot.py
   ```

## Discord commands

```text
!watch Dune
!3d Dune
!watch Dune !3d
!hall Bashundhara City !Sony Square
!watch Dune !hall Bashundhara City !hall Sony Square
!hall
!watching
!unwatch Dune
```

`!watch` accepts a case-insensitive partial title. By default it searches only
Dhaka halls, reports only shows with seats available, and shows only 2D tickets.
Use `!3d Movie name` or append `!3d` to `!watch` to include both 2D and 3D.
It checks today first,
then tomorrow, then the day after tomorrow. If none are available, it watches
every `POLL_INTERVAL` seconds (minimum 15 seconds) and mentions the person who
started the watch when tickets appear.

Use `!hall Hall name !Another hall` to restrict later watches in the current
channel to one or more matching Dhaka halls. Use `!hall` without names to clear
the filter. Hall filters can also be included directly in a watch command, as
shown above. The live source is `https://starcineplex.com/`'s current public API.
