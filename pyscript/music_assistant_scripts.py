import aiohttp
import asyncio
from utils import post, get_genre

state.persist('pyscript.music_assistant_metadata')

async def get_music_assistant_access_token():
    url = "http://localhost:8095/auth/login"
    data = {
      "provider_id": "builtin",
      "credentials": {
        "username": pyscript.config["global"]["music_assistant_username"],
        "password": pyscript.config["global"]["music_assistant_password"]
      }
    }
    
    async with aiohttp.ClientSession() as session:
        response_data = await post(session, url, json=data)

    if "token" in response_data:
        return response_data["token"]
    else:
        log.warning(f"Error obtaining access token: {response_data}")
        return None
    

def run_music_assistant_command(command, **kwargs):
    """
    Runs a music assistant command on the API
    
    A list of commands can be found at http://192.168.1.199:8095/api-docs/commands
    """
    token = get_music_assistant_access_token()
    
    url = "http://localhost:8095/api"

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "command": command,
        "args": kwargs
    }
    
    async with aiohttp.ClientSession() as session:
        response_data = await post(session, url, json=payload, headers=headers)
    return response_data


def add_item_to_music_assistant_metadata(key, album):
    set_music_assistant_metadata_attributes(**{
        f"{key}_uri": album["uri"],
        f"{key}_name": album["name"],
        f"{key}_thumbnail": album["image"] or "/local/404.png",
    })

def set_music_assistant_metadata_attributes(**kwargs):
    attrs = state.getattr("pyscript.music_assistant_metadata") or {}

    for key, value in kwargs.items():
        attrs[key]=value

    state.set("pyscript.music_assistant_metadata", "ok", attrs)

def update_random_album():
    for i in range(30):
        album = music_assistant.get_library(
            config_entry_id="01KJD55JFR0EVEB6YP6869PN0Y",
            media_type= "album",
            limit= 1,
            order_by= "random",
            album_type=["album"]
        )["items"][0]
        
        if not album["artists"]:
            continue
        if not album["image"]:
            continue
        
        genre = get_genre(album["artists"][0]["name"], album["name"])
        
        if not genre:
            continue
        
        if (album["explicit"] != True) and ("metal" not in genre.lower()):
            log.info(f'Found a non-explicit non-metal album: {album["name"]}; genre = {genre}')

            add_item_to_music_assistant_metadata(f"random_album", album)
            break
        else:
            log.info(f'{album["name"]} is too explicit... Genre = {genre}')
    

def update_recently_added_albums():
    album_response = music_assistant.get_library(
        config_entry_id="01KJD55JFR0EVEB6YP6869PN0Y",
        media_type= "album",
        limit= 25,
        order_by= "timestamp_added_desc",
    )["items"]
    
    albums = [a for a in album_response if a["image"]]

    for i in range(7):
        add_item_to_music_assistant_metadata(f"recently_added_album_{i+1}", albums[i])

    for album in albums:
        genre = get_genre(album["artists"][0]["name"], album["name"])
        if genre and "metal" not in genre.lower():
            add_item_to_music_assistant_metadata("spotlight_album", album)
            break

def update_recently_added_playlists():
    playlists = music_assistant.get_library(
        config_entry_id="01KJD55JFR0EVEB6YP6869PN0Y",
        media_type= "playlist",
        limit= 25,
        order_by= "timestamp_added_desc",
    )["items"]

    for i in range(4):
        add_item_to_music_assistant_metadata(f"recently_added_playlist_{i+1}", playlists[i])


@state_trigger("media_player.argon_radio_2i_305890754e1c_3")
def dont_stop_the_music_for_music_assistant_speakers():
    """
    Makes sure Music Assitant speakers never stop playing
    """
    dont_stop_the_music("Argon Radio 2i 305890754e1c")


@service    
@time_trigger("cron(0 3 * * *)")
@state_trigger("input_text.apple_music_provider_status")
@time_trigger("startup")
def update_music_assistant_uris():
    update_random_album()
    update_recently_added_albums()
    update_recently_added_playlists()


@state_trigger("input_text.home_state")
def sync_music_assistant_when_we_get_home_or_wake_up(old_value = None):
    old_home_state = old_value.lower()
    if "away" in old_home_state or "night" in old_home_state:
        log.info("Refreshing music database")
        run_music_assistant_command("music/sync")

@state_trigger("sensor.shellywalldisplay_0008225bc076_illuminance_level")
def update_albums_and_playlists_when_shelly_lid_is_closed(value = None):
    if value and "dark" in value.lower():
        update_recently_added_playlists()
        update_recently_added_albums()

@service
def sync_music_assistant_library():
    log.info("Refreshing music database")
    run_music_assistant_command("music/sync")
    asyncio.sleep(4)
    update_recently_added_playlists()
    update_recently_added_albums()
        

@service
def get_music_assistant_provider_data(provider):

    for provider_data in run_music_assistant_command("config/providers"):
        if provider_data["domain"] == provider:
            return provider_data
    
@service
def dont_stop_the_music(player_name):
    """
    Set don't stop the music = True for a music assistant player
    """
    
    player_info = run_music_assistant_command(
        "players/get_by_name",
        name = player_name)
    
    player_id = player_info["player_id"]
    
    player_queue = run_music_assistant_command(
        "player_queues/get_active_queue",
        player_id = player_id)
    
    queue_id = player_queue["queue_id"]

    run_music_assistant_command(
        "player_queues/repeat",
        queue_id = queue_id,
        repeat_mode = "off"
    )
    
    run_music_assistant_command(
        "player_queues/dont_stop_the_music",
        queue_id = queue_id,
        dont_stop_the_music_enabled = True
    )

def set_apple_music_provider_status():
    provider_data = get_music_assistant_provider_data("apple_music")
    last_error = provider_data["last_error"]
    
    if last_error:
        input_text.apple_music_provider_status = last_error[:255]
    else:
        if media_player.argon_radio_2i_305890754e1c_3 == "unavailable":
            input_text.apple_music_provider_status = "UNAVAILABLE"
        else:
            input_text.apple_music_provider_status = "OK"

    
@state_trigger("media_player.argon_radio_2i_305890754e1c_3")
def update_apple_music_provider_status_when_radio_changes_state(value = None, old_value=None):
    if old_value == "unavailable" or value == "unavailable":
        set_apple_music_provider_status()

@state_trigger("sensor.shellywalldisplay_0008225bc076_illuminance_level")
def update_apple_music_provider_status_when_shelly_lid_is_closed(value=None):
    if value and "dark" in value.lower():
        set_apple_music_provider_status()
    
    

        
        



























