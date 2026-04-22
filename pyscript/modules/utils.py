import aiohttp
import aiofiles


async def download_file(url, filename):
    
    if url.startswith("/api"):
        url = "http://homeassistant.local:8123" + url
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.read()
            async with aiofiles.open(filename, mode='wb') as f:
                f.write(data)

async def fetch(session, url, *args, **kwargs):
    async with session.get(url, *args, **kwargs) as response:
        return await response.text()
 
async def fetch_json(session, url, *args, **kwargs):
    async with session.get(url, *args, **kwargs) as response:
        return await response.json() 
 
async def post(session, url, **kwargs):
    response = await session.post(url, **kwargs)
    return await response.json()
    
    
async def get_metadata_from_itunes(params):

    base_url = "https://itunes.apple.com/search"

    async with aiohttp.ClientSession() as session:
        async with session.get(base_url, params=params) as response:
            data = await response.json(content_type=None)

    if not data["results"]:
        return None

    return data["results"][0]
    

async def get_song_metadata_from_itunes(artist, track):
    base_url = "https://itunes.apple.com/search"
    query = f"{artist} {track}"

    params = {
        "term": query,
        "entity": "song",
        "limit": 1
    }
    return get_metadata_from_itunes(params)


async def get_album_metadata_from_itunes(artist, album):
    base_url = "https://itunes.apple.com/search"
    query = f"{artist} {album}"

    params = {
        "term": query,
        "entity": "album",
        "limit": 1
    }
    return get_metadata_from_itunes(params)
    
    
    
def get_album_art(artist, track, size=600):
    metadata = get_song_metadata_from_itunes(artist, track)
    if metadata:
        artwork_url = metadata["artworkUrl100"]
        return artwork_url.replace("100x100", f"{size}x{size}")
    else:
        return None

def determine_if_song_exists(artist, track):
    
    if not media_string_is_valid(artist) or not media_string_is_valid(track):
        return False
        
    metadata = get_song_metadata_from_itunes(artist, track)
    song_exists = True if metadata else False
    input_text.song_exists_log = f"{song_exists} ({artist} - {track})"

    return song_exists

def get_genre(artist, album):
    metadata = get_album_metadata_from_itunes(artist, album)
    if metadata:
        return metadata["primaryGenreName"]
    return None
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    