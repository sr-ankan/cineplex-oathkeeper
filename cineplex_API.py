"""Client for the public Star Cineplex catalog and showtime APIs."""

from dataclasses import dataclass
from datetime import date
from typing import Iterable
from typing import Any

import requests

import config


@dataclass(frozen=True)
class Movie:
    id: str
    title: str


@dataclass(frozen=True)
class Show:
    id: str
    venue_id: str
    date: str
    time: str
    status: str
    available_seats: int
    total_seats: int
    format: str


class CineplexAPI:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Origin": config.CINEPLEX_SITE_URL,
                "Referer": f"{config.CINEPLEX_SITE_URL}/",
                "User-Agent": "Mozilla/5.0 (compatible; CineplexDiscordBot/1.0)",
            }
        )

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        response = self.session.get(
            f"{config.CINEPLEX_API_BASE}{path}", params=params, timeout=20
        )
        response.raise_for_status()
        return response.json()

    def find_movies(self, query: str) -> list[Movie]:
        # The unfiltered catalog includes both now-showing and coming-soon
        # titles, which is required when a watch starts before sales open.
        payload = self._get(
            "/catalog/api/movies",
            {"orgId": config.CINEPLEX_ORG_ID},
        )
        movies = []
        normalized_query = query.casefold().strip()
        for item in payload:
            title = (item.get("title") or {}).get("en", "").strip()
            if title and normalized_query in title.casefold():
                movies.append(Movie(id=str(item["id"]), title=title))
        return movies

    def venues(self, hall_names: Iterable[str] | None = None) -> list[dict[str, str]]:
        payload = self._get("/catalog/api/venues")
        requested = [name.casefold().strip() for name in (hall_names or []) if name.strip()]
        return [
            {"id": str(item["id"]), "name": (item.get("name") or {}).get("en", "Unknown venue")}
            for item in payload
            if item.get("isActive", True)
            if self._is_dhaka_venue((item.get("name") or {}).get("en", ""))
            if not requested or any(
                name in ((item.get("name") or {}).get("en", "")).casefold()
                for name in requested
            )
        ]

    @staticmethod
    def _is_dhaka_venue(name: str) -> bool:
        # The API does not expose a city field. Non-Dhaka venues currently
        # identify their city in the venue name; keep the default conservative.
        non_dhaka_cities = ("chattogram", "chittagong", "narayanganj")
        return not any(city in name.casefold() for city in non_dhaka_cities)

    def shows(
        self, movie_id: str, venue_id: str, target_dates: set[str] | None = None
    ) -> list[Show]:
        payload = self._get(
            "/inventory/api/shows",
            {
                "venueId": venue_id,
                "movieId": movie_id,
                "orgId": config.CINEPLEX_ORG_ID,
            },
        )
        today = date.today().isoformat()
        return [
            Show(
                id=str(item["id"]),
                venue_id=str(item.get("venueId", venue_id)),
                date=str(item.get("date", "")),
                time=str(item.get("time", "")),
                status=str(item.get("status", "")),
                available_seats=int(item.get("availableSeats") or 0),
                total_seats=int(item.get("totalSeats") or 0),
                format=str(item.get("format", "")),
            )
            for item in payload
            if str(item.get("venueId", venue_id)) == venue_id
            if item.get("date", "") >= today
            if target_dates is None or item.get("date", "") in target_dates
        ]

    def selling_shows(
        self,
        movie_id: str,
        target_dates: set[str] | None = None,
        hall_names: Iterable[str] | None = None,
        include_3d: bool = False,
    ) -> list[tuple[Show, str]]:
        matches: list[tuple[Show, str]] = []
        for venue in self.venues(hall_names):
            for show in self.shows(movie_id, venue["id"], target_dates):
                if (
                    show.status.casefold() == "selling"
                    and show.available_seats > 0
                    and (include_3d or "3d" not in show.format.casefold())
                ):
                    matches.append((show, venue["name"]))
        return matches

    @staticmethod
    def booking_url(show_id: str) -> str:
        return f"{config.CINEPLEX_SITE_URL}/shows/{show_id}/seats?tenant=star-cineplex"
