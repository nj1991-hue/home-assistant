import aiohttp
import asyncio
import aiofiles
from bs4 import BeautifulSoup
import re
import time
import random
import datetime, time
import json
from utils import download_file, fetch,  get_album_art, determine_if_song_exists, media_string_is_valid

state.persist('pyscript.media_metadata')
state.persist('pyscript.dab_radio_art_urls')

sonos_media = None
#default_radio_station = "NPO Radio 2"
#default_radio_station = "Random album"
default_radio_station = "Random station"

# Group leader
main_media_player = "media_player.kokken"

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

    file_path = "/config/json/sonos/media.json"
    json_data = json.dumps(sonos_media_dict, indent=4, ensure_ascii=False)

    async with aiofiles.open(file_path, mode="w", encoding="utf-8") as f:
        await f.write(json_data)
        
    sonos_media = None


def get_sonos_media():
    global sonos_media
    
    if not sonos_media:
        file_path = "/config/json/sonos/media.json"
    
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
    
    

def get_media_player(entity_id):
    """
    returns a media player given its entity ID
    """
    media_players = [
        media_player.kokken,
        media_player.entre,
        media_player.stue,
        media_player.spisestue,
    ]

    media_player_dict={player.entity_id: player for player in media_players}
    return media_player_dict[entity_id]

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


def set_media_metadata_attributes(entity_id, **kwargs):
    attrs = state.getattr("pyscript.media_metadata") or {}

    room = entity_id.split('.')[-1]

    for key, value in kwargs.items():
        attrs[f"{room}_{key}"]=value

    state.set("pyscript.media_metadata", "ok", attrs)
    
def get_media_metadata_attribute(entity_id, attribute):
    
    attrs = state.getattr("pyscript.media_metadata") or {}
    room = entity_id.split('.')[-1]
    return attrs.get(f"{room}_{attribute}")
    


@state_trigger("media_player.kokken.*")
@state_trigger("media_player.stue.*")
@state_trigger("media_player.spisestue.*")
@state_trigger("media_player.entre.*")
def set_meta_data(var_name=None):
    set_sonos_meta_data([var_name])

@state_trigger("media_player.argon_radio_2i_305890754e1c.*")
@state_trigger("media_player.argon_radio_2i_305890754e1c")
def set_sonos_metadata_when_radio_changes_state_or_attribute(var_name = None):
    task.unique("set_sonos_metadata_when_radio_changes_state_or_attribute")

    dab_radio_attrs = state.getattr(var_name)
    dab_media_title = dab_radio_attrs.get("media_title")

    set_sonos_meta_data([
        "media_player.kokken",
        "media_player.stue",
        "media_player.spisestue",
        "media_player.entre",
    ])


def set_sonos_meta_data(entity_ids):
    
    dab_radio_attrs = None
    dr_media_headers = {}
    
    for entity_id in entity_ids:
    
        media_players = [m.entity_id for m in get_media_players()]
    
        attrs = state.getattr(entity_id)
        sonos_media_content_id = attrs.get("media_content_id", "")
        sonos_media_artist = attrs.get("media_artist")
        sonos_media_title = attrs.get("media_title")
        sonos_source = attrs.get("source")
        sonos_media_channel = attrs.get("media_channel")
        sonos_media_playlist = attrs.get("media_playlist")
        
        media_header = None
        media_title = None
        media_subtitle = None
        
        if "x-rincon-stream:RINCON_804AF2CAFA8001400" in sonos_media_content_id:
            dab_radio_attrs = dab_radio_attrs or state.getattr("media_player.argon_radio_2i_305890754e1c")

            dab_channel = dab_radio_attrs.get("media_content_id")
            dab_source = dab_radio_attrs.get("source")
            dab_media_title = dab_radio_attrs.get("media_title")

            if media_player.argon_radio_2i_305890754e1c != "playing":
                media_title = str(media_player.argon_radio_2i_305890754e1c)
                media_subtitle = '-'
            
            elif dab_media_title and "-" in dab_media_title:
                now_playing = dab_media_title.split("-")[1].strip()
                
                now_playing = ' - '.join([t.strip() for t in dab_media_title.split("-")[1:]])
                
                if " / " in now_playing:
                    media_subtitle = now_playing.split(" / ")[0].strip()
                    media_title=now_playing.split(" / ")[1].strip()
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
                    
                if " - " in media_subtitle and media_player.argon_radio_2i_305890754e1c == "playing":
                    media_title = media_subtitle.split(" - ")[0].strip()
                    media_subtitle = media_subtitle.replace(f"{media_title} - ","")
            elif dab_source == "Local Music":
                media_header = getattr(media_player.argon_radio_2i_305890754e1c, "media_album_name", "Apple music playlist")
                media_title = getattr(media_player.argon_radio_2i_305890754e1c, "media_artist", "-")
                media_subtitle = getattr(media_player.argon_radio_2i_305890754e1c, "media_title", "-")                
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
                dr_media_header_url = f"https://www.dr.dk/lyd/playlister/{playlist}"
                if dr_media_header_url in dr_media_headers:
                    media_title = dr_media_headers[dr_media_header_url]
                else:
                    media_title = await get_dr_media_header(dr_media_header_url)
                    dr_media_headers[dr_media_header_url] = media_title
                

        if not media_header:
            media_header = sonos_media_channel or sonos_media_playlist or sonos_source or "???"
            
        if not media_title:
            media_title = sonos_media_artist or "-"
            
        if not media_subtitle:
            media_subtitle = sonos_media_title or "-"
    
        if input_text.resume_npo_radio_2_after_commercials == "True" and media_header == get_media_name(input_text.npo_radio_2_filler_playlist_id):
            media_header = "NPO Radio 2 (Reklame)"
            
        set_media_metadata_attributes(
            entity_id=entity_id,
            media_header=media_header,
            media_title=media_title,
            media_subtitle=media_subtitle
        )
    

@state_trigger("pyscript.media_metadata.kokken_media_title")
def add_song_to_kokken_history():
    
    task.unique("add_song_to_kokken_history")
    asyncio.sleep(5) # Only add song when it is playing for 5 seconds or more

    song_title = pyscript.media_metadata.kokken_media_title
    artist_name = pyscript.media_metadata.kokken_media_subtitle

    if media_string_is_valid(artist_name) and media_string_is_valid(song_title):
        input_text.kokken_song_history = f"{song_title} | {artist_name}"

@service
@state_trigger("pyscript.media_metadata.kokken_media_subtitle")
@state_trigger("pyscript.media_metadata.kokken_media_header")
def set_kokken_art():
    set_sonos_art("media_player.kokken")


@state_trigger("media_player.argon_radio_2i_305890754e1c.entity_picture")
def store_dab_radio_preset_image():
    task.unique("store_dab_radio_preset_image")
    asyncio.sleep(4) # Wait for the data to stabilize
    channel = getattr(media_player.argon_radio_2i_305890754e1c, "media_content_id", None)
    entity_picture = getattr(media_player.argon_radio_2i_305890754e1c, "entity_picture", None)
    source = getattr(media_player.argon_radio_2i_305890754e1c, "source", None)
    
    if not channel or not entity_picture:
        return
    
    if source != "Internet radio":
        return
    
    machine_friendly_channel = channel.replace(" ","_").replace("/","-")
    filename = machine_friendly_channel + ".png"
    await download_file(entity_picture, f"/config/www/{filename}")

    attrs = state.getattr("pyscript.dab_radio_art_urls") or {}

    attrs[channel] = f"/local/{filename}?v={time.time()}"
    state.set("pyscript.dab_radio_art_urls", "ok", attrs)

def set_sonos_art(entity_id):

    attrs = state.getattr(entity_id)
    sonos_media_content_id = attrs.get("media_content_id")
    sonos_media_artist = attrs.get("media_artist")
    sonos_media_title = attrs.get("media_title")
    sonos_entity_picture = attrs.get("entity_picture")

    art_url = None
    
    if not sonos_media_content_id:
        return

    if "x-rincon-stream:RINCON_804AF2CAFA8001400" in sonos_media_content_id:
        dab_channel = getattr(media_player.argon_radio_2i_305890754e1c, "media_content_id", None)
        dab_source = getattr(media_player.argon_radio_2i_305890754e1c, "source", None)
        dab_media_title = getattr(media_player.argon_radio_2i_305890754e1c, "media_title", None)
        dab_art_url = getattr(media_player.argon_radio_2i_305890754e1c, "entity_picture", None)

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
        elif dab_art_url:
            art_url = dab_art_url
        if not art_url:
            if dab_source == "AUX in":
                art_url = "https://i.pinimg.com/736x/94/ca/e0/94cae02ce1205a5ebefba850c0ccbf47.jpg"
            else:
                art_url = "https://img.freepik.com/premium-vector/retro-radio-receiver-square-vector-icon_92926-93.jpg"
    elif sonos_entity_picture and not "bauerdk" in sonos_media_content_id:
        art_url = sonos_entity_picture
    elif sonos_media_artist and sonos_media_title:
        if "bauerdk" in sonos_media_content_id:
            # Radio 100 and Radio Vinyl switch media_artist and media_title up
            song_title = sonos_media_artist
            artist = sonos_media_title
        else:
            artist = sonos_media_artist
            song_title = sonos_media_title

        # Get album art from iTunes
        art_url = get_album_art(artist, song_title)

    # Radio 100
    if not art_url and "bauerdk" in sonos_media_content_id:
        art_url = "https://play-lh.googleusercontent.com/zx_nqIaKsrcwKVBkqjrAapFyKk1mdA-ZodUyXig-Tt0RDLnuyeQgUPl1sK3SDbnX3A"
            
    if art_url:
        filename = "sonos_art.png"
        await download_file(art_url,f"/config/www/{filename}")
        
        set_media_metadata_attributes(
            entity_id=entity_id,
            art_url = f"/local/{filename}?v={time.time()}" # Add a "version" parameter to force a refresh
        )

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
def play_lucky_station(entity_id):
    task.unique("play_lucky_station")
    station_to_play = get_lucky_station()
    media_content_type = "favorite_item_id" if "FV:" in station_to_play else "music"

    media_player.play_media(
        media_content_id=station_to_play, 
        media_content_type=media_content_type,
        entity_id=entity_id
    )
    
    media_player.shuffle_set(entity_id = entity_id, shuffle=True)
    asyncio.sleep(15) # Give automations a chance to reset kokken_feels_lucky
    set_media_metadata_attributes(entity_id, feels_lucky=True)
    service.call('timer', 'start', entity_id='timer.lucky_station_change_timer')
    service.call('timer', 'start', entity_id='timer.lucky_station_force_change_timer')



@state_trigger("timer.lucky_station_force_change_timer")
@state_trigger("media_player.kokken.media_title")
def change_lucky_station_in_kokken():
    task.unique("play_lucky_station", kill_me=True)
    timer_state = state.get('timer.lucky_station_change_timer')
    force_timer_state = state.get('timer.lucky_station_force_change_timer')
    morning_routine_timer_state = state.get('timer.sonos_morning_routine_running')
    
    media_state = state.get('media_player.kokken')
    kokken_feels_lucky = get_media_metadata_attribute("media_player.kokken", "feels_lucky")
    log.info(f"Running change_lucky_station_in_kokken - timer_state = {timer_state}; "
              f"media_state = {media_state}; kokken_feels_lucky = {kokken_feels_lucky}; "
              f"force_timer_state = {force_timer_state}")
    if (
        kokken_feels_lucky 
        and timer_state == "idle" 
        and media_state == "playing" 
        and morning_routine_timer_state == "idle"
        ):
        log.info("playing lucky station in kokken")
        play_lucky_station("media_player.kokken")


@state_trigger("pyscript.media_metadata.kokken_media_header")
def reset_sonos_feels_lucky_when_kokken_media_header_changes():
    reset_sonos_feels_lucky("kokken")
    
@state_trigger("pyscript.media_metadata.stue_media_header")
def reset_sonos_feels_lucky_when_stue_media_header_changes():
    reset_sonos_feels_lucky("stue")

@state_trigger("pyscript.media_metadata.spisestue_media_header")
def reset_sonos_feels_lucky_when_spisestue_media_header_changes():
    reset_sonos_feels_lucky("spisestue")

@state_trigger("pyscript.media_metadata.entre_media_header")
def reset_sonos_feels_lucky_when_entre_media_header_changes():
    reset_sonos_feels_lucky("entre")

def reset_sonos_feels_lucky(room):
    now = datetime.datetime.now().time()

    if now > datetime.time(4, 30):
        log.info(f"Resetting lucky state for {room}")
        set_media_metadata_attributes(f"media_player.{room}", feels_lucky=False)

@service
def toggle_sonos_feels_lucky(entity_id):
    feels_lucky = get_media_metadata_attribute(entity_id, "feels_lucky")
    
    if feels_lucky:
        set_media_metadata_attributes(entity_id, feels_lucky=False)
    else:
        set_media_metadata_attributes(entity_id, feels_lucky=True)
        service.call('timer', 'start', entity_id='timer.lucky_station_change_timer')
        service.call('timer', 'start', entity_id='timer.lucky_station_force_change_timer')
        
@service
def disable_sonos_feels_lucky(entity_id):
    set_media_metadata_attributes(entity_id, feels_lucky=False)

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
        #return None, None, None
        is_active = False
        artist = None
        title = None
    else:
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
            song_exists = determine_if_song_exists(dab_media_title_artist, dab_media_title_title)
        except Exception as e:
            log.warning(f"Error while connecting to itunes: {e}")
            song_exists = False
    else:
        dab_media_title_artist = "-"
        dab_media_title_title = "-"
        song_exists = False
    
    is_playing = artist_in_media_title or (song_exists and npo_radio_2_is_playing())
            
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
        timeout = 9 * 60
    
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
    
def start_npo_radio_2_filler_playlist(media_player_obj):
    input_text.resume_npo_radio_2_after_commercials = "True"
    media_player.shuffle_set(entity_id = media_player_obj.entity_id, shuffle=True)
    media_player.play_media(
        media_content_id=input_text.npo_radio_2_filler_playlist_id, 
        media_content_type="favorite_item_id",
        entity_id=media_player_obj.entity_id
    )
    asyncio.sleep(2)
    media_player.shuffle_set(entity_id = media_player_obj.entity_id, shuffle=True)    
    
    
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
            start_npo_radio_2_filler_playlist(media_player_obj)
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
            media_player.play_media(
                media_content_id="x-rincon-stream:RINCON_804AF2CAFA8001400", 
                media_content_type="music",
                entity_id=media_player_obj.entity_id
            )
            input_text.resume_npo_radio_2_after_commercials = "False"
            
            dab_channel = getattr(media_player.argon_radio_2i_305890754e1c, "media_content_id", None)
            if media_player.argon_radio_2i_305890754e1c == "off":
                service.call('timer', 'start', entity_id='timer.radio_turned_on_by_automation')
                play_dab_preset("Internet radio/preset/2")
            elif dab_channel != "Internet radio/preset/2":
                play_dab_preset("Internet radio/preset/2")
            else:
                log.info(f"No need to start the radio or switch channel, dab_channel='{dab_channel}'")
                
            
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
        

@service
def add_media_player_to_group(entity_id):
    global main_media_player
    
    if binary_sensor.someone_is_watching_tv == "on" and entity_id == "media_player.stue":
        return
    if entity_id == main_media_player:
        return

    group_members = state.getattr(main_media_player).get("group_members")

    if group_members and entity_id not in group_members:
        main_player=group_members[0]
        players_to_join = [main_player, entity_id]
    
        log.info(f"Joining {players_to_join} into {main_player}")
    
        media_player.join(entity_id = main_player, group_members=players_to_join)


@service    
def remove_media_player_from_group(entity_id):
    media_player.unjoin(entity_id=entity_id)


@service
def toggle_media_player_in_group(entity_id):
    global main_media_player
    group_members = state.getattr(main_media_player).get("group_members")
    
    if not group_members:
        log.warning(f"{entity_id} has no group_members attribute")
        return
    
    if entity_id in group_members:
        remove_media_player_from_group(entity_id)
    else:
        add_media_player_to_group(entity_id)


@service
@time_trigger("cron(*/5 * * * *)")  
def group_if_same_content():
    global main_media_player

    content_id = state.getattr(main_media_player).get("media_content_id")
    media_playlist = state.getattr(main_media_player).get("media_playlist")
    group_members = state.getattr(main_media_player).get("group_members") or []

    all_media_players = [
        "media_player.kokken",
        "media_player.entre",
        "media_player.stue",
        "media_player.spisestue",
                    ]    

    other_media_player_objects = [get_media_player(e) for e in all_media_players if e != main_media_player]
    main_media_player_obj = get_media_player(main_media_player)
    
    for other_media_player_obj in other_media_player_objects:
        other_content_id = getattr(other_media_player_obj,"media_content_id", None)
        other_media_playlist = getattr(other_media_player_obj,"media_playlist", None)
        
        if (
            ((other_content_id == content_id) or (media_playlist and media_playlist == other_media_playlist))
            and main_media_player_obj == "playing" 
            and other_media_player_obj == "playing"
            and group_members
            and other_media_player_obj.entity_id not in group_members
        ):
            add_media_player_to_group(other_media_player_obj.entity_id)


def adjust_volume_for_quiet_music(var_name, value, old_value, keywords):
    
    timer_state = state.get('timer.sonos_morning_routine_running')
    
    def keyword_in(value):
        for keyword in keywords:
            if keyword in value:
                return True
        return False

    if timer_state != "idle":
        return
    elif value and old_value and not keyword_in(value) and not keyword_in(old_value):
        return
    elif value and old_value and keyword_in(value) and keyword_in(old_value):
        return
    
    room = var_name.split("_")[0].split(".")[1]
    player = f"media_player.{room}"

    step = 0.05
    
    if value and keyword_in(value):
        current = float(state.get(f"{player}.volume_level") or 0.0)
        new = min(current + step, 1.0)
        log.info(f"Adjusting volume for {player}")
        
        if current > 0:
            service.call("media_player", "volume_set",
                         entity_id=player, volume_level=new)

    elif old_value and keyword_in(old_value):
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
    

@state_trigger("sensor.entre_media_channel")
@state_trigger("sensor.stue_media_channel")
@state_trigger("sensor.spisestue_media_channel")
@state_trigger("sensor.kokken_media_channel")
def adjust_volume_when_quiet_music_plays(var_name=None, value=None, old_value=None):
    adjust_volume_for_quiet_music(var_name, value, old_value, ["Klassisk","P8 Jazz"])

# Commented out because repeat_set occasionally pauses playback
#@state_trigger("media_player.kokken.queue_position")
#@state_trigger("media_player.entre.queue_position")
#@state_trigger("media_player.spisestue.queue_position")
#@state_trigger("media_player.stue.queue_position")
def set_repeat_to_true(var_name=None):
    """
    Makes sure repeat is always set to True
    """
    media_players = get_media_players()
    
    if var_name in [m.entity_id for m in media_players]:
        media_player.repeat_set(entity_id = var_name, repeat="all")


    
    
@state_trigger("media_player.argon_radio_2i_305890754e1c.source")
def update_last_dab_radio_source():
    dab_source = getattr(media_player.argon_radio_2i_305890754e1c, "source", None)

    if not dab_source:
        return
    
    input_text.last_dab_radio_source = dab_source
    
    
def wait_for(obj, attribute, is_or_is_not, desired_value, timeout=20):
    """
    Waits for an attribute to obtain a certain value and then returns the value
    of the attribute
    """
    value = None
    
    for i in range(timeout*2):

        if attribute == "state":
            value = state.get(obj.entity_id)
        else:
            value = state.getattr(obj.entity_id).get(attribute)        
        
        if is_or_is_not == "is" and value == desired_value:
            return value
        elif is_or_is_not == "is_not" and value != desired_value:
            return value
        log.info(f"{obj.entity_id}.{attribute} {is_or_is_not} {desired_value} == False. It is {value}. Sleeping")
        asyncio.sleep(0.5)
    raise Exception(f"Timeout while waiting for {obj.entity_id}.{attribute}  {is_or_is_not} {desired_value}")
    
    
def play_dab_preset(preset):
    media_player.play_media(
        entity_id="media_player.argon_radio_2i_305890754e1c",
        media_content_id=preset,
        media_content_type="channel"
    )


@service
def handle_radio_playback(trigger_entity_id):
    global default_radio_station
    log.info(f"Handling radio playback for {trigger_entity_id}")
    media_player_obj = get_media_player(trigger_entity_id)
    media_content_id = wait_for(media_player_obj, "media_content_id", "is_not", None)

    if "x-rincon-stream:RINCON_804AF2CAFA8001400" not in media_content_id:
        log.info(f"{media_player_obj} is not playing line-in. Returning")
        return
    
    if media_player.argon_radio_2i_305890754e1c == "off":
        service.call('timer', 'start', entity_id='timer.radio_turned_on_by_automation')
        
        if input_text.reset_radio == "True":
            log.info(f"Resetting radio to {default_radio_station}. It is probably the first time it is turned on today")

            now = datetime.datetime.now()
            weekday = now.weekday()

            
            if default_radio_station == "NPO Radio 2":
                if weekday in [5, 6]: # weekend
                    play_dab_preset("Internet radio/preset/7") # KYA
                else:
                    play_dab_preset("Internet radio/preset/2") # NPO Radio 2
            elif default_radio_station == "Random album":
            
                if weekday in [5, 6]: # weekend
                    play_dab_preset("Internet radio/preset/5") # Paradise radio
                else:
                    if input_text.apple_music_provider_status == "OK":
                        music_assistant.play_media(entity_id= "media_player.argon_radio_2i_305890754e1c_3", media_id = pyscript.music_assistant_metadata.random_album_uri)
                        return
                    else:
                        play_dab_preset("Internet radio/preset/5") # Paradise radio
            elif default_radio_station == "Random station":
                station_to_play=random.choice([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
                play_dab_preset(f"Internet radio/preset/{station_to_play}")

            else:
                log.warning(f"Unsupported value for default_radio_station: {default_radio_station}; Playing p3")
                play_dab_preset("DAB/preset/3")

            input_text.reset_radio = "False"
        else:
            if input_text.last_dab_radio_source == "Local Music" and input_text.apple_music_provider_status == "OK":
                log.info("Resuming Music Assistant playback")
                media_player.media_play(entity_id="media_player.argon_radio_2i_305890754e1c_3")
                return
            else:
                log.info("Turning on radio")
                media_player.turn_on(entity_id="media_player.argon_radio_2i_305890754e1c")
        
        dab_source = wait_for(media_player.argon_radio_2i_305890754e1c, "source", "is_not", None)
        
        log.info(f"Obtained DAB source: {dab_source}")
        
        if media_player.argon_radio_2i_305890754e1c.media_title == "Music Assistant":
            log.info("DAB radio is playing Music Assistant. Returning")
            return
        
        dab_source = media_player.argon_radio_2i_305890754e1c.source
        if dab_source != "Internet radio" and dab_source != "DAB":
            log.info("DAB radio is neither playing internet radio or DAB; Defaulting to P3")
            play_dab_preset("DAB/preset/3")
        elif (
            dab_source == "Internet radio" 
            and input_text.commercials_on_npo_radio_2 == "True" 
            and binary_sensor.npo_radio_2_is_playing == "on"
        ):
            log.info("DAB radio is playing NPO radio 2 but there are commercials. Starting filler playlist")
            start_npo_radio_2_filler_playlist(media_player_obj)
        log.info("Handled radio playback successfully")

    elif media_player.argon_radio_2i_305890754e1c == "unavailable":
        media_player.play_media(
            media_content_id="FV:2/73", # Radio Vinyl 
            media_content_type="favorite_item_id",
            entity_id=trigger_entity_id
        )
    elif (
        input_text.commercials_on_npo_radio_2 == "True" 
        and binary_sensor.npo_radio_2_is_playing == "on"
        and input_text.resume_npo_radio_2_after_commercials == "True"
    ):
        # We end up here if:
        # - The radio is already playing
        # - It is playing NPO radio 2
        # - Commercials are playing
        # 
        # This can happen if, for example, NPO Radio 2 is playing in the entre, but nowhere else.
        # Then when pressing play on another speaker, the radio does not need to be turned on.
        # But rather than play the radio signal, we would like to play the filler playlist.
        # Because there are commercials on the radio.
        log.info("Starting filler playlist because NPO radio 2 is already playing and we are in a commercial break")
        start_npo_radio_2_filler_playlist(media_player_obj)
        wait_for(media_player_obj, "media_playlist", "is_not", None)
        wait_for(media_player_obj, "state", "is", "playing")
        group_if_same_content()
    
            


    
    
    
    
    
    
    
    
    
    
    
    