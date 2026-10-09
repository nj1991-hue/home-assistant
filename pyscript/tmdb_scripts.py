# pyscript/arthouse_films.py
import aiohttp
from datetime import date, timedelta
import random

TMDB_URL = "https://api.themoviedb.org/3/discover/movie"
IMDB_RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
POSTER_BASE = "https://image.tmdb.org/t/p/w342"
BACKDROP_BASE = "https://image.tmdb.org/t/p/w780"

COUNTRIES = "DK|SE|NO|FI|IS|FR|DE|IT|ES|BE|NL|AT|PL|RO|PT|IE|GR|HU|CZ|GB"
# Disney, Paramount, Columbia, 20th Century, Universal, Warner Bros., Marvel Studios, Marvel Entertainment
EXCLUDED_COMPANIES = "2|4|5|25|33|174|420|7505"

ENTITY = "sensor.arthouse_films"

@pyscript_executor
def fetch_imdb_ratings(imdb_ids):
    """Stream IMDb's daily ratings dump and pick out the IDs we care about.
    Returns {imdb_id: (rating, votes)}."""
    import gzip
    import urllib.request

    wanted = {i.encode() for i in imdb_ids}
    found = {}
    req = urllib.request.Request(IMDB_RATINGS_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        with gzip.GzipFile(fileobj=resp) as gz:
            next(gz)  # header row
            for line in gz:
                tconst, rating, votes = line.rstrip(b"\n").split(b"\t")
                if tconst in wanted:
                    found[tconst.decode()] = (float(rating), int(votes))
                    if len(found) == len(wanted):
                        break
                    
    return found

async def fetch_page(session, headers, page):
    """
    Fetch a page of movies from tmdb. Each page contains 20 movies
    """
    
    params = {
        "language": "en-US",
        "primary_release_date.gte": "2000-01-01",
        "with_origin_country": COUNTRIES,
        "without_companies": EXCLUDED_COMPANIES,
        "vote_count.gte": 25,
        "vote_average.gte": 7,
        "sort_by": "primary_release_date.desc",
        "page": page,
    }
    async with session.get(TMDB_URL, params=params, headers=headers) as resp:
        if resp.status != 200:
            log.error(f"TMDB page {page} failed: {resp.status} {await resp.text()}")
            return []
        data = await resp.json()
        return data

async def fetch_details(session, headers, movie_id):
    """Full movie record: includes imdb_id, origin_country, runtime, genres..."""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}"
    async with session.get(url, params={"language": "en-US"}, headers=headers) as resp:
        if resp.status != 200:
            log.warning(f"TMDB details {movie_id} failed: {resp.status}")
            return None
        return await resp.json()


async def format_movie(movie, session, headers):

    movie_dict = {
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

    details = await fetch_details(session, headers, movie["id"])
    
    imdb_id = details.get("imdb_id")
    if imdb_id:
        movie_dict["url"] = f"https://www.imdb.com/title/{imdb_id}/"
        movie_dict["imdb_id"] = imdb_id

    
    return movie_dict


@time_trigger("startup", "cron(0 6 * * *)")
@service
async def refresh_arthouse_films():
    """Fetch recent European / festival-type films from TMDB."""
    token = pyscript.config["global"]["tmdb_token"]

    headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}
    tmdb_results = []
    films = []

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        # Fetch the page with the latest movies on it
        data = await fetch_page(session, headers, 1)
        tmdb_results.extend(data["results"])

        # And two random pages 
        # Note: the last page is not included because it might not have 20 results on it
        for page in random.sample(range(2, data['total_pages']), 2):
            data = await fetch_page(session, headers, page)
            tmdb_results.extend(data["results"])
        
        for tmdb_result in tmdb_results:
            film = await format_movie(tmdb_result, session, headers)
            films.append(film)

    # Add IMDB ratings
    ratings = fetch_imdb_ratings([f["imdb_id"] for f in films])
    for film in films:
        rating, votes = ratings.get(film["imdb_id"], (None, None))
        film["imdb_rating"] = rating
        film["imdb_votes"] = votes    

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