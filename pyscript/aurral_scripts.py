"""
Aurral -> Sonos, straight from the Aurral Subsonic API (no Music Assistant).

DRAFT, not yet tested against a Sonos. Copy to /config/pyscript/aurral_scripts.py.

Setup
-----
1. configuration.yaml, under the existing `pyscript: global:` block:

       aurral_url: "http://192.168.1.XXX:3001"   # an address BOTH HA and the Sonos speakers can reach
       aurral_username: !secret aurral_username
       aurral_password: !secret aurral_password

   and add `pyscript.aurral_metadata` to `recorder: exclude: entities:`
   (its attributes get big and change every refresh).

2. Sign in to the Aurral web UI once with that account. Token auth (used here so
   the password never ends up in the URLs handed to Sonos) only works after
   Aurral has stored a Subsonic password for the account, otherwise error 41.

3. Reload pyscript, then run `pyscript.update_aurral_metadata` once.
   Covers are cached in /config/www/aurral/ and served as /local/aurral/...

What it publishes
-----------------
pyscript.aurral_metadata, with for every <key>:
    <key>_id, <key>_type ("album"/"playlist"), <key>_name, <key>_artist, <key>_thumbnail

Keys:
    recently_added_album_1 .. _7    newest monitored albums in the Aurral Library
    random_album                    one random monitored album, re-rolled every refresh
                                    (albums: only status "monitored"; playlists: all of them)
    playlist_1 .. _8                playlists + Flows, most recently changed first
    playlist_<slug>                 every playlist/Flow by name, for pinned buttons,
                                    e.g. "Daily Mix 1" -> playlist_daily_mix_1

Dashboard button template (button_card_templates, next to music_assistant_button)
---------------------------------------------------------------------------------
  aurral_button:
    template: square_button
    show_name: false
    show_icon: false
    show_entity_picture: true
    variables:
      item: ""
      entity_id: media_player.kokken
    entity_picture: |
      [[[ return states['pyscript.aurral_metadata'].attributes[variables.item + '_thumbnail'] ]]]
    tap_action:
      action: call-service
      service: pyscript.play_aurral_on_sonos
      data:
        entity_id: "[[[ return variables.entity_id ]]]"
        item: "[[[ return variables.item ]]]"
    hold_action:
      action: call-service
      service: pyscript.play_aurral_on_sonos
      data:
        entity_id: "[[[ return variables.entity_id ]]]"
        item: "[[[ return variables.item ]]]"
        enqueue: add

  A button:
    type: custom:button-card
    template: aurral_button
    variables:
      item: recently_added_album_1      # or playlist_1, playlist_daily_mix_1, random_album
"""

import aiohttp
import hashlib
import os
import random
import re
import secrets
from urllib.parse import quote, urlencode

state.persist("pyscript.aurral_metadata")

COVER_DIR = "/config/www/aurral"
COVER_SIZE = 600
NEWEST_ALBUMS = 7
LATEST_PLAYLISTS = 8
MAX_TRACKS = 150  # one Sonos queue call per track, so keep this sane

CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/avif": "avif",
}


# ---------------------------------------------------------------------------
# Aurral Subsonic API
# ---------------------------------------------------------------------------

def _config(name):
    return pyscript.config["global"][name]


def _base_url():
    return _config("aurral_url").rstrip("/")


def _auth():
    # Salted token: md5(password + salt). Aurral checks it against the stored Subsonic password.
    salt = secrets.token_hex(6)
    return {
        "u": _config("aurral_username"),
        "s": salt,
        "t": hashlib.md5((_config("aurral_password") + salt).encode()).hexdigest(),
        "v": "1.16.1",
        "c": "home-assistant",
    }


def _query(**params):
    return {k: str(v) for k, v in {**_auth(), **params}.items()}


async def _get(endpoint, **params):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{_base_url()}/rest/{endpoint}",
            params=_query(f="json", **params),
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            data = await response.json(content_type=None)

    body = data["subsonic-response"]
    if body["status"] != "ok":
        error = body.get("error", {})
        raise Exception(f"Aurral {endpoint} failed ({error.get('code')}): {error.get('message')}")
    return body


def _stream_url(song_id):
    # Sonos only queues URLs whose *path* ends in .mp3 (else UPnP 804/714), and Aurral's
    # is /rest/stream.view. So set `aurral_stream_url` in pyscript global config to the
    # nginx proxy (aurral_sonos_proxy.conf), which serves the same stream at /sonos/track.mp3.
    # The dummy x=track.mp3 (ignored by Aurral) keeps the whole URL ending in .mp3 too.
    # mp3 320 plays on every Sonos; Aurral transcodes on the fly.
    stream_url = pyscript.config["global"].get("aurral_stream_url") or f"{_base_url()}/rest/stream.view"
    return f"{stream_url}?" + urlencode(
        _query(id=song_id, format="mp3", maxBitRate=320)
    ) + "&x=track.mp3"


async def _monitored_albums(sort, count):
    """Monitored albums, as Subsonic album objects.

    The Subsonic API doesn't know about monitoring, so ask Aurral's own library API
    (the same query as Library > Albums with the "Monitored" filter) and look each
    album up in Subsonic for its id, name and cover.
    """
    async with aiohttp.ClientSession(
        auth=aiohttp.BasicAuth(_config("aurral_username"), _config("aurral_password"))
    ) as session:
        async with session.get(
            f"{_base_url()}/api/library",
            params={
                "kind": "albums",
                "status": "monitored",
                "sort": sort,  # "newest" (recently added first) or "random"
                "availableOnly": "true",
                "page": "1",
                "pageSize": str(count),
            },
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            if response.status != 200:
                raise Exception(f"Aurral /api/library failed (HTTP {response.status}): {await response.text()}")
            page = await response.json()

    albums = []
    for item in page.get("items", []):
        # Same id Aurral's Subsonic API uses: "album:" + encodeURIComponent(identityKey), colons kept.
        album_id = "album:" + quote(str(item["identityKey"]), safe="!*'():")
        try:
            albums.append(_get("getAlbum", id=album_id)["album"])
        except Exception as e:
            log.warning(f"Aurral: skipping {item.get('artistName')} - {item.get('title')}: {e}")
    return albums


def _album_songs(album_id):
    return _get("getAlbum", id=album_id)["album"].get("song", [])


def _playlist_songs(playlist_id):
    return _get("getPlaylist", id=playlist_id)["playlist"].get("entry", [])


# ---------------------------------------------------------------------------
# Cover art cache: /config/www/aurral/<hash>.<ext>  ->  /local/aurral/<hash>.<ext>
# Downloaded once, so the dashboard never sees Aurral credentials.
# ---------------------------------------------------------------------------

@pyscript_compile
def _list_cover_dir():
    os.makedirs(COVER_DIR, exist_ok=True)
    return os.listdir(COVER_DIR)


@pyscript_compile
def _write_file(path, data):
    with open(path, "wb") as f:
        f.write(data)


@pyscript_compile
def _remove_file(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _cover_key(cover_id):
    return hashlib.md5(f"{cover_id}@{COVER_SIZE}".encode()).hexdigest()[:16]


async def _download_cover(cover_id, cached):
    """Return the /local URL for cover_id, downloading it if it's not in `cached` (key -> filename)."""
    key = _cover_key(cover_id)
    if key in cached:
        return f"/local/aurral/{cached[key]}"

    async with aiohttp.ClientSession() as session:
        # getCoverArt can 302 to an external image; aiohttp follows it.
        async with session.get(
            f"{_base_url()}/rest/getCoverArt.view",
            params=_query(id=cover_id, size=COVER_SIZE),
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            if response.status != 200 or not response.content_type.startswith("image/"):
                log.warning(f"Aurral: no cover for {cover_id} (HTTP {response.status}, {response.content_type})")
                return None
            extension = CONTENT_TYPE_EXTENSIONS.get(response.content_type, "jpg")
            data = await response.read()

    filename = f"{key}.{extension}"
    task.executor(_write_file, f"{COVER_DIR}/{filename}", data)
    cached[key] = filename
    return f"/local/aurral/{filename}"


# ---------------------------------------------------------------------------
# Metadata for the dashboard
# ---------------------------------------------------------------------------

def _cover(item, cached, used):
    if not item.get("coverArt"):
        return None
    url = _download_cover(item["coverArt"], cached)
    if url:
        used.add(url.rsplit("/", 1)[-1])
    return url


def _playlist_cover(playlist, cached, used):
    """The playlist's own cover, or else the cover of its first track that has one.

    Aurral only has a playlist cover once it has saved one (imported original, upload,
    or a generated one), so new or imported playlists can come back without any.
    """
    thumbnail = _cover(playlist, cached, used)
    if thumbnail:
        return thumbnail
    try:
        entries = _playlist_songs(playlist["id"])
    except Exception as e:
        log.warning(f"Aurral: could not read playlist {playlist.get('name')}: {e}")
        return None
    for entry in entries[:10]:
        thumbnail = _cover(entry, cached, used)
        if thumbnail:
            return thumbnail
    return None


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _add_item(attrs, key, item_type, item, thumbnail):
    attrs[f"{key}_id"] = item["id"]
    attrs[f"{key}_type"] = item_type
    attrs[f"{key}_name"] = item.get("name") or item.get("title") or ""
    attrs[f"{key}_artist"] = item.get("artist") or item.get("owner") or ""
    attrs[f"{key}_thumbnail"] = thumbnail or "/local/404.png"


async def _artist_genres(artist_mbid):
    async with aiohttp.ClientSession(
        auth=aiohttp.BasicAuth(_config("aurral_username"), _config("aurral_password"))
    ) as session:
        async with session.get(
            f"{_base_url()}/api/artists/{artist_mbid}",
            params={"mode": "core"},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            if response.status != 200:
                return []
            return (await response.json()).get("genres", [])


def _album_genres(album):
    genres = [g["name"] for g in album.get("genres", [])]
    if not genres:
        artists = album.get("artists") or []
        mbid = artists[0].get("musicBrainzId") if artists else None
        if mbid:
            genres = _artist_genres(mbid)
    return genres


def is_not_metal(album):
    genres = _album_genres(album)
    if genres and not "metal" in str(genres).lower():
        return True
    else:
        return False

@service
@time_trigger("startup")
@time_trigger("cron(*/30 * * * *)")
def update_aurral_metadata():
    """Refresh pyscript.aurral_metadata (newest monitored albums, a random monitored album, playlists/Flows) and cache their covers."""
    try:
        newest = _monitored_albums("newest", NEWEST_ALBUMS * 2)
        randoms = _monitored_albums("random", 100)
        playlists = _get("getPlaylists")["playlists"].get("playlist", [])
    except Exception as e:
        log.warning(f"Aurral: metadata refresh failed, keeping the old metadata: {e}")
        return

    cached = {}
    for filename in task.executor(_list_cover_dir):
        cached[filename.split(".")[0]] = filename
    used = set()

    attrs = state.getattr("pyscript.aurral_metadata") or {"friendly_name": "Aurral metadata"}
    # Newest albums: skip ones without art so the buttons never go blank.
    i = 0
    spotlight_album_found = False
    
    for album in newest:
        if i >= NEWEST_ALBUMS:
            break
        thumbnail = _cover(album, cached, used)
        if thumbnail:
            i += 1
            _add_item(attrs, f"recently_added_album_{i}", "album", album, thumbnail)
            
            if is_not_metal(album) and not spotlight_album_found:
                _add_item(attrs, f"spotlight_album", "album", album, thumbnail)
                spotlight_album_found = True

    for album in randoms:
        thumbnail = _cover(album, cached, used)
        genres = _album_genres(album)
        if thumbnail and is_not_metal(album) and album["id"] != attrs.get("spotlight_album_id"):
            _add_item(attrs, "random_album", "album", album, thumbnail)
            break

    # Most recently changed first (no lambda: pyscript lambdas don't mix well with builtins like sorted).
    by_date = [(p.get("changed") or p.get("created") or "", i) for i, p in enumerate(playlists)]
    by_date.sort(reverse=True)
    playlists = [playlists[i] for _, i in by_date]
    for i, playlist in enumerate(playlists):
        thumbnail = _playlist_cover(playlist, cached, used)
        if i < LATEST_PLAYLISTS:
            _add_item(attrs, f"playlist_{i + 1}", "playlist", playlist, thumbnail)
        _add_item(attrs, f"playlist_{_slug(playlist['name'])}", "playlist", playlist, thumbnail)

    # Drop covers nothing points at any more (e.g. a Flow that got new art).
    for filename in cached.values():
        if filename not in used:
            task.executor(_remove_file, f"{COVER_DIR}/{filename}")

    state.set("pyscript.aurral_metadata", "ok", attrs)
    log.info(f"Aurral: metadata updated ({len(playlists)} playlists, {len(used)} covers)")


@state_trigger("sensor.shellywalldisplay_0206039b2b83_illuminance_level")
def update_aurral_metadata_when_shelly_lid_is_closed(value=None):
    if value and "dark" in value.lower():
        update_aurral_metadata()


# ---------------------------------------------------------------------------
# Playing on Sonos
# ---------------------------------------------------------------------------

def _sonos_play_media(entity_id, url, enqueue):
    """Put one track in the Sonos queue and wait for it, so the queue keeps the album order.

    pyscript service calls are fire-and-forget unless blocking=True. Returns False
    instead of raising when Sonos refuses a track, so one bad track doesn't stop the rest.
    """
    try:
        service.call("media_player", "play_media", blocking=True, entity_id=entity_id,
                     media_content_type="music", media_content_id=url, enqueue=enqueue)
        return True
    except Exception as e:
        log.warning(f"Aurral: {entity_id} refused {url.split('&id=')[-1].split('&')[0]}: {e}")
        return False


def _group_coordinator(entity_id):
    """The speaker that owns the queue of entity_id's group (HA lists it first in group_members).

    Only the coordinator can start its queue (sonos.play_queue fails on a group member).
    """
    members = (state.getattr(entity_id) or {}).get("group_members") or []
    return members[0] if members else entity_id


def _play_songs_on_sonos(entity_id, songs, enqueue=None, shuffle=False):
    coordinator = _group_coordinator(entity_id)
    if coordinator != entity_id:
        log.info(f"Aurral: {entity_id} is grouped, using the group coordinator {coordinator}")
        entity_id = coordinator

    songs = list(songs)
    if shuffle:
        random.shuffle(songs)
    urls = [_stream_url(s["id"]) for s in songs[:MAX_TRACKS]]
    if not urls:
        log.warning(f"Aurral: nothing to play on {entity_id}")
        return

    if enqueue == "add" and state.get(entity_id) == "playing":
        # Hold action: append to the Sonos queue.
        _add_to_queue(entity_id, urls)
        return

    # Note: HA's enqueue="replace" does NOT use the Sonos queue for a plain URL; it plays
    # the URL on its own (play_uri), so playback stops after that track. Instead: empty
    # the queue, add the first track, play the queue from the start, then add the rest.
    try:
        service.call("media_player", "clear_playlist", blocking=True, entity_id=entity_id)
    except Exception as e:
        log.warning(f"Aurral: could not clear the queue of {entity_id}: {e}")

    started = False
    while urls and not started:
        started = _sonos_play_media(entity_id, urls.pop(0), "add")
    if not started:
        log.warning(f"Aurral: {entity_id} refused every track (is aurral_stream_url set to the proxy?)")
        return
    service.call("sonos", "play_queue", blocking=True, entity_id=entity_id, queue_position=0)
    input_boolean.turn_off(entity_id="input_boolean.allow_sonos_popup_on_shelly")

    # Let the (group) speaker actually start before adding more: while it is still
    # switching, Sonos can reject AddURIToQueue.
    for _ in range(15):
        if state.get(entity_id) == "playing":
            break
        task.sleep(1)
    else:
        # Same AirPlay quirk as script.force_play_media: nudge it if it didn't start.
        media_player.media_play(entity_id=entity_id)

    _add_to_queue(entity_id, urls)


def _add_to_queue(entity_id, urls):
    """Append urls to the Sonos queue in order, retrying each refused track once."""
    added = 0
    for url in urls:
        if _sonos_play_media(entity_id, url, "add"):
            added += 1
            continue
        task.sleep(2)
        if _sonos_play_media(entity_id, url, "add"):
            added += 1
    # (HA's queue_size attribute only refreshes on the next playback event, so don't log it here.)
    log.info(f"Aurral: added {added} of {len(urls)} tracks to the queue of {entity_id}")


@service
def play_aurral_on_sonos(entity_id, item, enqueue=None, shuffle=False):
    """Play an item from pyscript.aurral_metadata (e.g. recently_added_album_1, playlist_1) on a Sonos speaker.

    enqueue: "add" appends to the Sonos queue instead of replacing it.
    shuffle: shuffle the tracks first.
    """
    task.unique(f"play_aurral_on_sonos_{entity_id}")
    
    metadata = state.getattr("pyscript.aurral_metadata") or {}
    item_id = metadata.get(f"{item}_id")
    item_type = metadata.get(f"{item}_type")
    if not item_id:
        log.warning(f"Aurral: unknown item {item}; run pyscript.update_aurral_metadata")
        return

    songs = _album_songs(item_id) if item_type == "album" else _playlist_songs(item_id)
    
    if enqueue:
        input_boolean.turn_on(entity_id="input_boolean.album_added_to_queue")
        input_text.set_value(entity_id="input_text.next_album", value=item)
        
        queue_size = state.getattr(entity_id).get("queue_size")
        if queue_size:
            input_number.set_value(entity_id="input_number.next_album_queue_id", value=queue_size+1)
        
    else:
        input_boolean.turn_off(entity_id="input_boolean.album_added_to_queue")
        input_number.set_value(entity_id="input_number.next_album_queue_id", value=0)
        name = metadata.get(f"{item}_name", "")
        input_text.set_value(entity_id="input_text.aurral_playlist_name", value=name)

    _play_songs_on_sonos(entity_id, songs, enqueue, shuffle)
        

@service
def play_aurral_album_on_sonos(entity_id, query, enqueue=None, shuffle=False):
    """Play the first Aurral album matching `query` (e.g. "Kind of Blue") on a Sonos speaker."""
    task.unique(f"play_aurral_on_sonos_{entity_id}")

    albums = _get("search3", query=query, albumCount=1, artistCount=0, songCount=0)["searchResult3"].get("album", [])
    if not albums:
        log.warning(f"Aurral: no album matches {query}")
        return
    _play_songs_on_sonos(entity_id, _album_songs(albums[0]["id"]), enqueue, shuffle)


@service
def play_aurral_playlist_on_sonos(entity_id, name, enqueue=None, shuffle=False):
    """Play an Aurral playlist or Flow by name (case-insensitive) on a Sonos speaker."""
    task.unique(f"play_aurral_on_sonos_{entity_id}")

    playlist_id = None
    for playlist in _get("getPlaylists")["playlists"].get("playlist", []):
        if playlist["name"].lower() == name.lower():
            playlist_id = playlist["id"]
            break
    if not playlist_id:
        log.warning(f"Aurral: no playlist called {name}")
        return
    _play_songs_on_sonos(entity_id, _playlist_songs(playlist_id), enqueue, shuffle)



@state_trigger("media_player.kokken.media_content_id")
def reset_album_added_to_queue_when_media_content_id_changes():
    media_content_id = getattr(media_player.kokken, "media_content_id", "")
    if "192.168.1.140:3002" not in media_content_id:
        input_boolean.turn_off(entity_id="input_boolean.album_added_to_queue")

@state_trigger("media_player.kokken.queue_position")
def reset_album_added_to_queue_when_queue_position_changes():
    queue_position = getattr(media_player.kokken, "queue_position")
    if queue_position and queue_position >= float(input_number.next_album_queue_id):
        input_boolean.turn_off(entity_id="input_boolean.album_added_to_queue")


# ---------------------------------------------------------------------------
# Latest albums with genres (Developer tools > Actions, tick "return response")
# ---------------------------------------------------------------------------

@service(supports_response="only")
def aurral_latest_albums(count=5):
    """Return the albums most recently added to the Aurral Library, with genres."""
    albums = _get("getAlbumList2", type="newest", size=int(count))["albumList2"].get("album", [])
    return {
        "albums": [
            {
                "artist": a.get("artist"),
                "album": a.get("name"),
                "year": a.get("year"),
                "genres": [g["name"] for g in a.get("genres", [])],
                "added": a.get("created"),
                "id": a["id"],
            }
            for a in albums
        ]
    }
