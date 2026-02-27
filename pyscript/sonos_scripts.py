import aiohttp
import asyncio
import aiofiles
from bs4 import BeautifulSoup
import re
import time
import random
import datetime
import json

sonos_media = None

@service
@time_trigger("cron(0 3 * * *)")
def refresh_sonos_media():
    global sonos_media
    playlists = media_player.browse_media(
        entity_id = "media_player.kokken", 
        media_content_type= "favorites_folder", 
        media_content_id= "object.container.playlistContainer"
    )
    streams = media_player.browse_media(
        entity_id = "media_player.kokken", 
        media_content_type= "favorites_folder", 
        media_content_id= "object.item.audioItem.audioBroadcast"
    )
    
    sonos_media_dict = {}
    
    for media in [streams['media_player.kokken'], playlists['media_player.kokken']]:
        for child in media.children:
            sonos_media_dict[child.title] = child.media_content_id

    file_path = "/config/sonos_media.json"
    json_data = json.dumps(sonos_media_dict, indent=4, ensure_ascii=False)

    async with aiofiles.open(file_path, mode="w", encoding="utf-8") as f:
        await f.write(json_data)
        
    sonos_media = None


def get_sonos_media():
    global sonos_media
    
    if not sonos_media:
        file_path = "/config/sonos_media.json"
    
        async with aiofiles.open(file_path, mode="r", encoding="utf-8") as f:
            content = await f.read()
    
        sonos_media = json.loads(content)
    return sonos_media
    
        
def get_media_content_id(media_name):
    sonos_media = get_sonos_media()
    return sonos_media[media_name]
    
def get_media_name(media_content_id):
    sonos_media_inverted = {v:k for k,v in get_sonos_media().items()}
    return sonos_media_inverted[media_content_id]
    
    
@service
def test_get_media_content_id():
    log.info(get_media_content_id("The Voice"))

@service
def get_media_players():
    """
    Returns a list of media players to run actions on.
    
    The media players returned depend on the grouping. For example if all
    media players are grouped only a single player will be returned.
    
    If three players are grouped one player in the group will be returned
    as well as the solo player
    
    And so on.
    """
    media_players_accounted_for=[]
    
    media_players = [
        media_player.kokken,
        media_player.entre,
        media_player.stue,
        media_player.spisestue,
        ]
        
    media_players_to_return = []
    
    for media_player in media_players:
        group_members = getattr(media_player, "group_members", [])
        if media_player.entity_id not in media_players_accounted_for:
            media_players_accounted_for.append(media_player.entity_id)
            media_players_to_return.append(media_player)
            
        for grouped_media_player in group_members:
            if grouped_media_player not in media_players_accounted_for:
                media_players_accounted_for.append(grouped_media_player)
           
    return media_players_to_return

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

async def get_spotify_access_token(client_id, client_secret):
    url = "https://accounts.spotify.com/api/token"
    headers = {
        "Authorization": "Basic " + (client_id + ":" + client_secret).encode("ascii").decode("ascii"),
    }
    data = {
        "grant_type": "client_credentials",
    }
    
    async with aiohttp.ClientSession() as session:
        response_data = await post(session, url, data=data, auth=aiohttp.BasicAuth(client_id, client_secret))

    if "access_token" in response_data:
        return response_data["access_token"]
    else:
        log.warning(f"Error obtaining access token: {response_data}")
        return None


async def spotify_track_exists(artist, title):
    
    access_token = await get_spotify_access_token(pyscript.config["global"]["spotify_client_id"], pyscript.config["global"]["spotify_api_secret"])
    
    search_url = "https://api.spotify.com/v1/search"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "q": f"artist:{artist} track:{title}",
        "type": "track",
        "limit": 1,
    }
    

    async with aiohttp.ClientSession() as session:
        async with session.get(search_url, headers=headers, params=params) as response:
            data = await response.json()
            if "NCRV" in title or "NCRV" in artist:
                song_exists = False
            elif "tracks" in data and data["tracks"]["items"]:
                song_exists = True
            else:
                song_exists = False
                
            input_text.song_exists_log = f"{song_exists} ({artist} - {title})"
            return song_exists


@service
async def test_spotify_track_exists():
    artist = "KRO"
    title = "NCRV"
    exists = await spotify_track_exists(artist, title)
    log.info(f"Track exists: {exists}")


def get_album_info_from_spotify(access_token, artist, title):
    search_url = "https://api.spotify.com/v1/search"
    headers = {
        "Authorization": f"Bearer {access_token}",
    }
    params = {
        "q": f"artist:{artist} track:{title}",
        "type": "track",
        "limit": 1,
    }
    async with aiohttp.ClientSession() as session:
        response_data = await fetch_json(session, search_url, headers=headers, params=params)

    if 'tracks' in response_data and response_data['tracks']['items']:
        track = response_data['tracks']['items'][0]
        return track["album"]
    else:
        log.info(f"No suitable album found for artist: {artist} and title: {title}.")
        return None

def get_album_art(artist, title):

    access_token = await get_spotify_access_token(pyscript.config["global"]["spotify_client_id"], pyscript.config["global"]["spotify_api_secret"])
    if access_token:
        album = await get_album_info_from_spotify(access_token, artist, title)
        if album:
            return album["images"][0]["url"]
    return None



async def parse_pic(html):
    soup = BeautifulSoup(html, 'html.parser')
    pic = soup.find(class_ = "dre-picture__image")
    return pic["src"]

async def parse_media_header(html):
    soup = BeautifulSoup(html, 'html.parser')
    media_header = soup.find(class_ = re.compile("ChannelPlaylistHead_title.*"))
    return media_header.string


async def scrape_dr_playlist(url):
    async with aiohttp.ClientSession() as session:
        html = await fetch(session, url)
        pic = await parse_pic(html)
        media_header = await parse_media_header(html)

    return pic.split("?")[0], media_header
    
async def get_dr_pic(url):
    async with aiohttp.ClientSession() as session:
        html = await fetch(session, url)
        pic = await parse_pic(html)
    return pic.split("?")[0]

async def get_dr_media_header(url):
    async with aiohttp.ClientSession() as session:
        html = await fetch(session, url)
        media_header = await parse_media_header(html)

    return media_header
    
    
def media_string_is_valid(artist_or_song):
    if artist_or_song == "-":
        return False
    if "NPO" in artist_or_song:
        return False
    if "P3" in artist_or_song:
        return False
    if "P4" in artist_or_song:
        return False
    if "BNNVARA" in artist_or_song:
        return False
    if "NCRV" in artist_or_song:
        return False
    if "TROS" in artist_or_song:
        return False
    if "Omroep" in artist_or_song:
        return False
    return True

@state_trigger("media_player.kokken")
@state_trigger("media_player.kokken.*")
@state_trigger("media_player.argon_radio_2i_305890754e1c")
@state_trigger("media_player.argon_radio_2i_305890754e1c.*")
def set_kokken_meta_data():
    kokken_media_content_id = getattr(media_player.kokken,"media_content_id", None)
    kokken_media_artist = getattr(media_player.kokken,"media_artist", None)
    kokken_media_title = getattr(media_player.kokken,"media_title", None)
    kokken_media_album_name = getattr(media_player.kokken,"media_album_name", None)
    kokken_source = getattr(media_player.kokken,"source", None)

    kokken_media_channel = getattr(media_player.kokken,"media_channel", None)
    kokken_media_playlist = getattr(media_player.kokken,"media_playlist", None)

    media_header = None
    media_title = None
    media_subtitle = None
    
    if kokken_media_content_id == "x-rincon-stream:RINCON_804AF2CAFA8001400":
        dab_channel = getattr(media_player.argon_radio_2i_305890754e1c, "media_content_id", None)
        dab_source = getattr(media_player.argon_radio_2i_305890754e1c, "source", None)
        dab_media_title = getattr(media_player.argon_radio_2i_305890754e1c, "media_title", None)
        
        if media_player.argon_radio_2i_305890754e1c != "playing":
            media_title = str(media_player.argon_radio_2i_305890754e1c)
            media_subtitle = '-'
        
        elif dab_media_title and "-" in dab_media_title:
            now_playing = dab_media_title.split("-")[1].strip()
            
            now_playing = ' - '.join([t.strip() for t in dab_media_title.split("-")[1:]])
            
            if "/" in now_playing:
                media_subtitle = now_playing.split("/")[0].strip()
                media_title=now_playing.split("/")[1].strip()
            else:
                if "Nu:" in now_playing and "-" in now_playing:
                    media_subtitle = now_playing.split("-")[1].strip()
                else:
                    media_subtitle = now_playing
                    
        else:
            media_subtitle = dab_media_title or "-"
            
        playlist = None
        
        if dab_source == "AUX in":
            media_header = "Pladespiller"
        elif dab_source == "Internet radio":
            if "NPO Radio 2" in dab_media_title:
                media_header = "NPO Radio 2"
                media_subtitle = media_subtitle.replace("NPO Radio 2 - ","")
            elif '-' in dab_media_title:
                media_header = dab_media_title.split('-')[0].strip()
            else:
                media_header = "Internet radio"
                
            if "-" in media_subtitle and media_player.argon_radio_2i_305890754e1c == "playing":
                media_title = media_subtitle.split("-")[0].strip()
                media_subtitle = media_subtitle.replace(f"{media_title} - ","")
        elif dab_channel == "DAB/preset/3":
            playlist = "p3"
            media_header = "DR P3"
        elif dab_channel == "DAB/preset/4":
            playlist = "p4aarhus"
            media_header = "DR P4"
        elif dab_channel == "DAB/preset/5":
            playlist = "p6beat"
            media_header = "DR P6"
        else:
            media_header = "DAB Radio"
            
        if playlist and not media_title:
            media_title = await get_dr_media_header(f"https://www.dr.dk/lyd/playlister/{playlist}")

    if not media_header:
        media_header = kokken_media_channel or kokken_media_playlist or kokken_source or "???"
        
    if not media_title:
        media_title = kokken_media_artist or "-"
        
    if not media_subtitle:
        media_subtitle = kokken_media_title or "-"

    if input_text.resume_npo_radio_2_after_commercials == "True" and media_header == get_media_name(input_text.npo_radio_2_filler_playlist_id):
        media_header = "NPO Radio 2 (Reklame)"
        
    if kokken_media_playlist == "Music Assistant":
        media_header = kokken_media_album_name

    input_text.kokken_media_title = media_title
    input_text.kokken_media_subtitle = media_subtitle
    input_text.kokken_media_header = media_header
    

@state_trigger("input_text.kokken_media_title")
def add_song_to_kokken_history():
    
    task.unique("add_song_to_kokken_history")
    asyncio.sleep(5) # Only add song when it is playing for 5 seconds or more

    song_title = input_text.kokken_media_title
    artist_name = input_text.kokken_media_subtitle

    if media_string_is_valid(artist_name) and media_string_is_valid(song_title):
        input_text.kokken_song_history = f"{song_title} | {artist_name}"

@service
@state_trigger("input_text.kokken_media_subtitle")
@state_trigger("input_text.kokken_media_header")
def set_kokken_art():
    kokken_media_content_id = getattr(media_player.kokken,"media_content_id", "")
    kokken_media_artist = getattr(media_player.kokken,"media_artist", None)
    kokken_media_title = getattr(media_player.kokken,"media_title", None)
    kokken_entity_picture = getattr(media_player.kokken,"entity_picture", None)
    
    art_url = None

    if kokken_media_content_id == "x-rincon-stream:RINCON_804AF2CAFA8001400":
        dab_channel = getattr(media_player.argon_radio_2i_305890754e1c, "media_content_id", None)
        dab_source = getattr(media_player.argon_radio_2i_305890754e1c, "source", None)

        if dab_source != "DAB":
            playlist = None
        elif dab_channel == "DAB/preset/3":
            playlist = "p3"
        elif dab_channel == "DAB/preset/4":
            playlist = "p4aarhus"
        elif dab_channel == "DAB/preset/5":
            playlist = "p6beat"
        else:
            playlist = None

        if playlist:
            art_url = await get_dr_pic(f"https://www.dr.dk/lyd/playlister/{playlist}")
        else:
            if dab_source == "AUX in":
                art_url = "https://i.pinimg.com/736x/94/ca/e0/94cae02ce1205a5ebefba850c0ccbf47.jpg"
            else:
                art_url = "https://img.freepik.com/premium-vector/retro-radio-receiver-square-vector-icon_92926-93.jpg"
    elif kokken_entity_picture and not "bauerdk" in kokken_media_content_id:
        art_url = kokken_entity_picture
    elif kokken_media_artist and kokken_media_title:
        if "bauerdk" in kokken_media_content_id:
            # Radio 100 and Radio Vinyl switch media_artist and media_title up
            song_title = kokken_media_artist
            artist = kokken_media_title
        else:
            artist = kokken_media_artist
            song_title = kokken_media_title

        # Get album art from Spotify
        art_url = get_album_art(artist, song_title)

    # Radio 100
    if not art_url and "bauerdk" in kokken_media_content_id:
        art_url = "https://play-lh.googleusercontent.com/zx_nqIaKsrcwKVBkqjrAapFyKk1mdA-ZodUyXig-Tt0RDLnuyeQgUPl1sK3SDbnX3A"
            
    if art_url:
        # Store file locally so we still show a file when HA no longer caches        
        filename = "sonos_art.png"
        await download_file(art_url,f"/config/www/{filename}")
        
        # Add a "version" parameter to force a refresh
        input_text.sonos_art_url_kokken=f"/local/{filename}?v={time.time()}"
    

def get_lucky_station():
       
    now = datetime.datetime.now()
    weekday = now.weekday()
    hour = now.hour
    month=now.month
    
    log.info(f"[get_lucky_station] weekday = {weekday}; hour = {hour}")

    # Everyday mix
    stations_to_choose_from = [
        get_media_content_id("Radio Vinyl"),
        get_media_content_id("10's Hits"),
        get_media_content_id("00's Hits"),
        get_media_content_id("Top 100 Listen"),
        get_media_content_id("New Music Daily"),
       ]
       
    if month in [11, 12]:
        stations_to_choose_from += [get_media_content_id("Julehits")]
       
    if hour < 10:
        stations_to_choose_from += [get_media_content_id("Chillout Lounge")]
    else:
        stations_to_choose_from += [get_media_content_id("mix 7")]
       
    if weekday == 0: # Monday
        stations_to_choose_from += [get_media_content_id("70'er Hits")]
    if weekday == 1: # Tuesday
        stations_to_choose_from += [get_media_content_id("80's Hits")]
    if weekday == 2: # Wednesday
        stations_to_choose_from += [get_media_content_id("90's Hits")]
    if weekday == 3: # Thursday
        stations_to_choose_from += [get_media_content_id("Radio Soft Classic")]
    if weekday == 4: # Friday
        if hour >= 18:
            stations_to_choose_from += [get_media_content_id("Dennis' Weekendmix")]
        else:
            stations_to_choose_from += [get_media_content_id("Radio Soft Modern")]
    if weekday == 5: # Saturday
        stations_to_choose_from += [get_media_content_id("myROCK Legends Of Rock")]
    if weekday == 6: # Sunday
        stations_to_choose_from += [get_media_content_id("Radio 100")]
        
    current_station = getattr(media_player.kokken, "media_content_id", None)
    
    if len(set(stations_to_choose_from)) > 1:
        stations_to_choose_from = [s for s in stations_to_choose_from if s != current_station]
        
    return random.choice(stations_to_choose_from)

    
@service
def play_lucky_station_in_kokken():
    task.unique("play_lucky_station_in_kokken")
    station_to_play = get_lucky_station()
    media_content_type = "favorite_item_id" if "FV:" in station_to_play else "music"

    media_player.play_media(
        media_content_id=station_to_play, 
        media_content_type=media_content_type,
        entity_id="media_player.kokken"
    )
    
    media_player.shuffle_set(entity_id = "media_player.kokken", shuffle=True)
    asyncio.sleep(15) # Give automations a chance to reset kokken_feels_lucky
    input_text.kokken_feels_lucky = "True"
    service.call('timer', 'start', entity_id='timer.kokken_is_lucky_change_timer')
    service.call('timer', 'start', entity_id='timer.kokken_is_lucky_force_change_timer')


@state_trigger("timer.kokken_is_lucky_force_change_timer")
@state_trigger("media_player.kokken.media_title")
def change_lucky_station_in_kokken():
    task.unique("play_lucky_station_in_kokken", kill_me=True)
    timer_state = state.get('timer.kokken_is_lucky_change_timer')
    force_timer_state = state.get('timer.kokken_is_lucky_force_change_timer')
    morning_routine_timer_state = state.get('timer.sonos_morning_routine_running')
    
    media_state = state.get('media_player.kokken')
    log.debug(f"Running change_lucky_station_in_kokken - timer_state = {timer_state}; "
              f"media_state = {media_state}; kokken_feels_lucky = {input_text.kokken_feels_lucky}; "
              f"force_timer_state = {force_timer_state}")
    if (
        input_text.kokken_feels_lucky == "True" 
        and timer_state == "idle" 
        and media_state == "playing" 
        and morning_routine_timer_state == "idle"
        ):
        log.info("playing lucky station in kokken")
        play_lucky_station_in_kokken()

    
@service
async def get_npo_radio_2_metadata():

    # URL of the playlist
    url = "https://onlineradiobox.com/nl/radio2/playlist/?lang=en"
    
    # Send HTTP GET request
    headers = {"User-Agent": "Mozilla/5.0"}

    async with aiohttp.ClientSession() as session:
        html = await fetch(session, url, headers=headers)
    
    # Parse the HTML content
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the playlist table
    playlist_table = soup.find("table", class_="tablelist-schedule")
    
    if not playlist_table:
        log.warning(f"Could not scrape {url}")
        return None, None, None
    
    # Find the first row (usually the currently playing song)
    first_row = playlist_table.find("tr")
    
    # Check if it's marked as currently playing
    is_active = "active" in first_row.get("class", [])
    artist = None
    title = None
    
    text = first_row.find_all("td")[1].text.strip()
    if text.count(" - ") == 1:
        artist = text.split(" - ")[0].strip()
        title = text.split(" - ")[1].strip()
        
    dab_media_title = getattr(media_player.argon_radio_2i_305890754e1c, "media_title", "")
    if artist:
        artist_in_media_title = artist in dab_media_title
    else:
        artist_in_media_title = False
        
    if " - " in dab_media_title:
        dab_media_title_artist = dab_media_title.split(" - ")[-2].strip()
        dab_media_title_title = dab_media_title.split(" - ")[-1].strip()
        try:
            song_exists = await spotify_track_exists(dab_media_title_artist, dab_media_title_title) 
        except Exception as e:
            log.warning(f"Error while connecting to Spotify: {e}")
            song_exists = False
    else:
        dab_media_title_artist = "-"
        dab_media_title_title = "-"
        song_exists = False
    
    is_playing = is_active or artist_in_media_title or song_exists
            
    log.info(
        f"is_playing: {is_playing}, "
        f"is_active: {is_active}, "
        f"artist_in_media_title: {artist_in_media_title}, "
        f"song_exists: {song_exists}, "
        f"artist: {artist}, "
        f"title: {title}, "
        f"dab_media_title: {dab_media_title}, "
        f"dab_media_title_artist: {dab_media_title_artist}, "
        f"dab_media_title_title: {dab_media_title_title}"
        )        
    return is_playing, artist, title
    
def npo_radio_2_is_playing():
    return binary_sensor.npo_radio_2_is_playing == "on"

@task_unique("start_stop_npo_radio_2_commercial_break")
@time_trigger("cron(30,55 * * * *)")    
async def start_npo_radio_2_commercial_break():
 
    now = datetime.datetime.now()
    hour = now.hour
    minute = now.minute
    weekday = now.weekday()

    if hour >= 19 and 25 < minute < 45:
        log.info("Not starting half-hour commercial break because the time is past 19:00")
    elif weekday == 6  and 25 < minute < 45:
        log.info("Not starting half-hour commercial break because it is Sunday")
    else:
        if npo_radio_2_is_playing():
            interval = 30
        else:
            interval = 60
    
        log.info(f"scraping at interval = {interval}s")
    
        is_playing = True 
    
        while is_playing == True:
            is_playing, artist, title = await get_npo_radio_2_metadata()
            
            if is_playing:
                log.info("A song is still playing. Sleeping.")
                
                dab_media_title = getattr(media_player.argon_radio_2i_305890754e1c, "media_title", "")
                for i in range(int(interval/2)):
                    
                    if dab_media_title == getattr(media_player.argon_radio_2i_305890754e1c, "media_title", ""):
                        await asyncio.sleep(2)
                    else:
                        # Break out of sleep in case media title changes
                        break
    
        # Let the song fade out
        await asyncio.sleep(3)
    
        log.info("Starting commercial break")
        service.call('timer', 'start', entity_id='timer.just_switched_to_commercials')
        input_text.commercials_on_npo_radio_2 = "True"

@task_unique("start_stop_npo_radio_2_commercial_break")
@time_trigger("cron(3,35 * * * *)")    
async def stop_npo_radio_2_commercial_break():
    now = datetime.datetime.now()
    minute = now.minute
    
    if minute > 30:
        timeout = 3 * 60
    else:
        timeout = 7 * 60
    
    if input_text.resume_npo_radio_2_after_commercials == "True":
        interval = 15
    else:
        interval = 60

    log.info(f"scrape interval = {interval}s")

    is_playing = False
    
    #while is_playing == False:
    for i in range(int(timeout/interval)):
        is_playing, artist, title = await get_npo_radio_2_metadata()
        
        if not is_playing:
            log.info("Commercials are still playing. sleeping.")
            await asyncio.sleep(interval)
        else:
            break
    
    log.info("Stopping commercial break")
    input_text.commercials_on_npo_radio_2 = "False"
    
@state_trigger("input_text.commercials_on_npo_radio_2")
async def switch_to_playlist_on_commercial_break(value=None, old_value=None):
    
    for media_player_obj in get_media_players():
        radio_2_is_playing = npo_radio_2_is_playing()
        media_player_state = state.get(media_player_obj.entity_id)
        media_content_id = getattr(media_player_obj, "media_content_id", None)
        
        filler_playlist_title = get_media_name(input_text.npo_radio_2_filler_playlist_id)
        
        if (
            value == "True" 
            and old_value == "False" 
            and radio_2_is_playing 
            and media_player_state == "playing"
            and media_content_id
            and "x-rincon-stream:RINCON_804AF2CAFA8001400" in media_content_id
        ):
            
            log.info(f"Switching to {filler_playlist_title} because of commercials")
            input_text.resume_npo_radio_2_after_commercials = "True"
            media_player.shuffle_set(entity_id = media_player_obj.entity_id, shuffle=True)
            media_player.play_media(
                media_content_id=input_text.npo_radio_2_filler_playlist_id, 
                media_content_type="favorite_item_id",
                entity_id=media_player_obj.entity_id
            )
            await asyncio.sleep(2)
            media_player.shuffle_set(entity_id = media_player_obj.entity_id, shuffle=True)
        else:
            log.info(
                f"Not switching to {filler_playlist_title}: "
                f"commercials_on_npo_radio_2 value={value}, "
                f"commercials_on_npo_radio_2 old_value={old_value}, "
                f"npo_radio_2_is_playing={radio_2_is_playing}, "
                f"media_player_state = {media_player_state}, "
                f"media_content_id = {media_content_id}"
            )        

def get_media_playlist(media_player_obj):
    return getattr(media_player_obj,"media_playlist", None) or getattr(media_player_obj,"media_channel", None)

def get_media_title(media_player_obj):
    return getattr(media_player_obj,"media_title", None)


@state_trigger("media_player.kokken.media_title")
@state_trigger("media_player.entre.media_title")
@state_trigger("media_player.stue.media_title")
@state_trigger("media_player.spisestue.media_title")
def switch_back_to_npo_radio_2(var_name=None):
    media_players = get_media_players()
    
    timer_state = state.get('timer.just_switched_to_commercials')
    
    if timer_state == "active":
        log.info("Not switching back to NPO radio 2 because timer is active")
        return
    
    if var_name not in [m.entity_id for m in media_players]:
        return

    filler_playlist_title = get_media_name(input_text.npo_radio_2_filler_playlist_id)
    no_need_to_switch=[]

    for media_player_obj in media_players:
        
        media_playlist = get_media_playlist(media_player_obj)
        media_title = get_media_title(media_player_obj)
        media_player_state = state.get(media_player_obj.entity_id)
        commercials_on_npo_radio_2 = input_text.commercials_on_npo_radio_2
        resume_npo_radio_2_after_commercials = input_text.resume_npo_radio_2_after_commercials
        
        if (
            resume_npo_radio_2_after_commercials == "True"
            and commercials_on_npo_radio_2 == "False"
            and media_playlist == filler_playlist_title
            and media_player_state == "playing"
            and media_title
            and media_player_obj.entity_id == var_name
        ):
            log.info("Switching back to NPO Radio 2")
            media_player.media_pause(entity_id = media_player_obj.entity_id)
            media_player.play_media(
                media_content_id="x-rincon-stream:RINCON_804AF2CAFA8001400", 
                media_content_type="music",
                entity_id=media_player_obj.entity_id
            )
            input_text.resume_npo_radio_2_after_commercials = "False"
        elif (
            (media_playlist and media_playlist != filler_playlist_title) 
            or (media_player_state == "playing" and not media_playlist)
        ):
            if media_title and media_player_state != "idle":
                
                if resume_npo_radio_2_after_commercials == "True":
                    log.info(
                        "No need to switch back to NPO Radio 2; "
                        f"playlist = {media_playlist}, "
                        f"media_player_state = {media_player_state}, "
                        f"media_player = {media_player_obj.entity_id}, "
                        f"var_name = {var_name}"
                        f"media_title = {media_title}"
                        )
                no_need_to_switch.append(True)
            else:
                log.info(f"Not setting resume_npo_radio_2_after_commercials to False: media_player_state = {media_player_state}, media_title = {media_title}")
        else:
            log.info(
                f"Not switching to NPO Radio 2: "
                f"resume_npo_radio_2_after_commercials={resume_npo_radio_2_after_commercials}, "
                f"commercials_on_npo_radio_2={commercials_on_npo_radio_2}, "
                f"media_playlist={media_playlist}, "
                f"media_player_state={media_player_state}, "
                f"media_player = {media_player_obj.entity_id}, "
                f"var_name = {var_name}"
            )
    if sum(no_need_to_switch) == len(media_players):
        if resume_npo_radio_2_after_commercials == "True":
            log.info(f"No need to switch back to NPO Radio 2. Setting resume_npo_radio_2_after_commercials to False")
        input_text.resume_npo_radio_2_after_commercials = "False"
        

def add_media_player_to_group(entity_id):
    group_members = getattr(media_player.spisestue, "group_members", [])
    
    if group_members and entity_id not in group_members:
        main_player=group_members[0]
        players_to_join = [main_player, entity_id]
    
        log.info(f"Joining {players_to_join} into {main_player}")
    
        media_player.join(entity_id = main_player, group_members=players_to_join)
    

@service
def add_kokken_to_group():
    add_media_player_to_group("media_player.kokken")

@service
def add_stue_to_group():
    add_media_player_to_group("media_player.stue")

@service
def add_entre_to_group():
    add_media_player_to_group("media_player.entre")


@service
@time_trigger("cron(*/5 * * * *)")  
def group_if_same_content():

    content_id = getattr(media_player.spisestue,"media_content_id", None)
    media_playlist = getattr(media_player.spisestue,"media_playlist", None)
    group_members = getattr(media_player.spisestue, "group_members", [])
    
    other_media_players = [
        media_player.kokken,
        media_player.entre,
        media_player.stue,
                    ]    
    
    for other_media_player in other_media_players:
        other_content_id = getattr(other_media_player,"media_content_id", None)
        other_media_playlist = getattr(other_media_player,"media_playlist", None)
        
        #log.info(f"media_playlist: {media_playlist}; other_media_playlist: {other_media_playlist}; other_media_player: {other_media_player}, media_player.spisestue: {media_player.spisestue}")
        
        if (
            ((other_content_id == content_id) or (media_playlist and media_playlist == other_media_playlist))
            and media_player.spisestue == "playing" 
            and other_media_player == "playing"
            and group_members
            and other_media_player.entity_id not in group_members
        ):
            add_media_player_to_group(other_media_player.entity_id)


@state_trigger("sensor.entre_media_channel")
@state_trigger("sensor.stue_media_channel")
@state_trigger("sensor.spisestue_media_channel")
@state_trigger("sensor.kokken_media_channel")
def adjust_volume_when_classical_music_plays(var_name=None, value=None, old_value=None):

    timer_state = state.get('timer.sonos_morning_routine_running')
    
    if timer_state != "idle":
        return
    elif value and old_value and "Klassisk" not in value and "Klassisk" not in old_value:
        return
    
    room = var_name.split("_")[0].split(".")[1]
    player = f"media_player.{room}"

    step = 0.05
    
    if value and "Klassisk" in value:
        current = float(state.get(f"{player}.volume_level") or 0.0)
        new = min(current + step, 1.0)
        log.info(f"Adjusting volume for {player}")
        
        if current > 0:
            service.call("media_player", "volume_set",
                         entity_id=player, volume_level=new)

    elif old_value and "Klassisk" in old_value:
        current = float(state.get(f"{player}.volume_level") or 0.0)
        if current > 0.05:
            new = current - step
        elif current > 0:
            new = 0.01
        else:
            new = 0
        if new != current:
            log.info(f"Adjusting volume for {player}")
            service.call("media_player", "volume_set",
                         entity_id=player, volume_level=new)


@state_trigger("media_player.kokken.queue_position")
@state_trigger("media_player.entre.queue_position")
@state_trigger("media_player.spisestue.queue_position")
@state_trigger("media_player.stue.queue_position")
def set_repeat_to_true(var_name=None):
    """
    Makes sure repeat is always set to True
    """
    media_players = get_media_players()
    
    if var_name in [m.entity_id for m in media_players]:
        media_player.repeat_set(entity_id = var_name, repeat="all")


@state_trigger("media_player.kokken_2")
@state_trigger("media_player.entre_2")
@state_trigger("media_player.spisestue_2")
@state_trigger("media_player.stue_2")
def set_repeat_to_true_for_music_assistant_speakers(var_name=None):
    """
    Makes sure repeat is always set to True for music assistant duplicates
    """
    media_players = get_media_players()
    
    if var_name in [m.entity_id + "_2" for m in media_players]:
        media_player.repeat_set(entity_id = var_name, repeat="all")


@service    
@time_trigger("cron(0 3 * * *)")
def update_random_album():
    for i in range(20):
        album = music_assistant.get_library(
            config_entry_id="01KJD55JFR0EVEB6YP6869PN0Y",
            media_type= "album",
            limit= 1,
            order_by= "random",
            album_type=["album"]
        )["items"][0]
        
        if album["explicit"] != True:
            log.info(f'Found a non-explicit album: {album["name"]}')
            break
        else:
            log.info(f'{album["name"]} is too explicit...')
    
    input_text.random_album_uri = album["uri"]
    input_text.random_album_thumbnail = album["image"]
    input_text.random_album_name = album["name"]
    
    
    
    
    
    