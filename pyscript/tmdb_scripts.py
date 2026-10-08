# pyscript/arthouse_films.py
import aiohttp
from datetime import date, timedelta

TMDB_URL = "https://api.themoviedb.org/3/discover/movie"
POSTER_BASE = "https://image.tmdb.org/t/p/w342"
BACKDROP_BASE = "https://image.tmdb.org/t/p/w780"

COUNTRIES = "DK|SE|NO|FI|IS|FR|DE|IT|ES|BE|NL|AT|PL|RO|PT|IE|GR|HU|CZ|GB"
# Disney, Paramount, Columbia, 20th Century, Universal, Warner Bros., Marvel Studios, Marvel Entertainment
EXCLUDED_COMPANIES = "2|4|5|25|33|174|420|7505"

DAYS_BACK = 540
PAGES = 3  # 20 films per page
ENTITY = "sensor.arthouse_films"


async def fetch_page(session, headers, page):
    params = {
        "language": "en-US",
        "primary_release_date.gte": (date.today() - timedelta(days=DAYS_BACK)).isoformat(),
        "with_origin_country": COUNTRIES,
        "without_companies": EXCLUDED_COMPANIES,
        "vote_count.gte": 25,
        "vote_average.gte": 7,
        "sort_by": "popularity.desc",
        "page": page,
    }
    async with session.get(TMDB_URL, params=params, headers=headers) as resp:
        if resp.status != 200:
            log.error(f"TMDB page {page} failed: {resp.status} {await resp.text()}")
            return []
        data = await resp.json()
        return data.get("results", [])

async def fetch_details(session, headers, movie_id):
    """Full movie record: includes imdb_id, origin_country, runtime, genres..."""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}"
    async with session.get(url, params={"language": "en-US"}, headers=headers) as resp:
        if resp.status != 200:
            log.warning(f"TMDB details {movie_id} failed: {resp.status}")
            return None
        return await resp.json()


def slim(movie):
    """Keep only what the dashboard needs, to keep attributes small."""
    return {
        "id": movie["id"],
        "title": movie.get("title"),
        "original_title": movie.get("original_title"),
        "language": movie.get("original_language"),
        "release_date": movie.get("release_date"),
        "rating": round(movie.get("vote_average", 0), 1),
        "votes": movie.get("vote_count"),
        "overview": movie.get("overview"),
        "poster": POSTER_BASE + movie["poster_path"] if movie.get("poster_path") else None,
        "backdrop": BACKDROP_BASE + movie["backdrop_path"] if movie.get("backdrop_path") else None,
        "url": f"https://www.themoviedb.org/movie/{movie['id']}",
    }


@time_trigger("startup", "cron(0 6 * * *)")
@service
async def refresh_arthouse_films():
    """Fetch recent European / festival-type films from TMDB."""
    token = pyscript.config["global"]["tmdb_token"]
    if not token:
        log.error("tmdb_token missing from pyscript config")
        return

    headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}
    movies = []

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        for page in range(1, PAGES + 1):
            results = await fetch_page(session, headers, page)
            movies.extend(results)
            if len(results) < 20:
                break

        seen = set()
        films = []
        for m in movies:
            if m["id"] not in seen:
                seen.add(m["id"])
                
                movie_dict = slim(m)
                
                details = await fetch_details(session, headers, m["id"])
                
                log.info(details)
                
                if details and details.get("imdb_id"):
                    movie_dict["url"] = f"https://www.imdb.com/title/{details.get("imdb_id")}/"
                
                films.append(movie_dict)

    state.set(
        ENTITY,
        value=len(films),
        new_attributes={
            "friendly_name": "Arthouse films",
            "icon": "mdi:filmstrip",
            "updated": date.today().isoformat(),
            "results": films,
        },
    )
    log.info(f"Arthouse films: {len(films)} loaded")