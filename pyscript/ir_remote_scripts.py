def play_dab_preset(preset):
    media_player.play_media(
        entity_id="media_player.argon_radio_2i_305890754e1c",
        media_content_id=preset,
        media_content_type="channel"
    )


def mute_or_unmute(media_player_obj):
    mute = not media_player_obj.is_volume_muted
    
    if mute:
        log.info(f"Muting {media_player_obj.entity_id}")
    else:
        log.info(f"Unmuting {media_player_obj.entity_id}")
    media_player.volume_mute(entity_id=media_player_obj.entity_id, is_volume_muted=mute)

def media_play(media_player_obj):
    
    if media_player_obj == "playing" and media_player_obj.is_volume_muted:
        media_player.volume_mute(entity_id=media_player_obj.entity_id, is_volume_muted=False)
    elif media_player_obj == "idle":
        media_player.play_media(
            media_content_id="x-rincon-stream:RINCON_804AF2CAFA8001400", 
            media_content_type="music",
            entity_id=media_player_obj.entity_id
        )

    else:
        log.info(f"Starting playback on {media_player_obj.entity_id}")
        media_player.media_play(entity_id=media_player_obj.entity_id)

def pause_or_play(media_player_obj, mute_instead_of_pause = False):
    if media_player_obj == "playing":
        if mute_instead_of_pause:
            mute_or_unmute(media_player_obj)
        else:
            media_player.media_pause(entity_id=media_player_obj.entity_id)
    else:
        media_play(media_player_obj)


def play_next_song_or_station(media_player_obj, inverse=False):
    
    if "x-rincon-stream:RINCON_804AF2CAFA8001400" in media_player_obj.media_content_id:

        if media_player.argon_radio_2i_305890754e1c.source == "Local Music":
            if inverse:
                media_player.media_previous_track(entity_id="media_player.argon_radio_2i_305890754e1c_3")
            else:
                media_player.media_next_track(entity_id="media_player.argon_radio_2i_305890754e1c_3")
        else:
            log.info("Playing next radio station")
            current_preset = media_player.argon_radio_2i_305890754e1c.media_content_id
    
            if current_preset.startswith("Internet radio/preset"):
                current_preset_number = int(current_preset.split("/")[-1])
                
                if inverse:
                    if current_preset_number == 1:
                        next_preset_number = 10
                    else:
                        next_preset_number = current_preset_number - 1
                else:
                    if current_preset_number < 10:
                        next_preset_number = current_preset_number + 1
                    else:
                        next_preset_number = 1
                    
                play_dab_preset(f"Internet radio/preset/{next_preset_number}")
            else:
                play_dab_preset(f"Internet radio/preset/1")
    else:
        if inverse:
            media_player.media_previous_track(entity_id=media_player_obj.entity_id)
        else:
            media_player.media_next_track(entity_id=media_player_obj.entity_id)

                
            


@event_trigger("esphome.ir_signal")
def handle_ir_remote_events(**kwargs):
    task.unique("handle_ir_remote_events", kill_me=True)
    event_name = kwargs.get("name", "")
    media_player_obj = media_player.entre
    
    log.info(f"Received {event_name} event from edifier remote")
    
    if event_name == "toggle_power":
        pause_or_play(media_player_obj, mute_instead_of_pause=True)
    elif event_name == "volume_up":
        if media_player_obj.is_volume_muted:
            log.info(f"Unmuting {media_player_obj.entity_id}")
            media_player.volume_mute(entity_id=media_player_obj.entity_id, is_volume_muted=False)
        else:
            log.info(f"Increasing volume on {media_player_obj.entity_id}")
            current_volume = media_player_obj.volume_level
            new_volume = current_volume + 0.02
            service.call("media_player", "volume_set", entity_id=media_player_obj.entity_id, volume_level=new_volume)
            
    elif event_name == "volume_down":
        log.info(f"Decreasing volume on {media_player_obj.entity_id}")
        current_volume = media_player_obj.volume_level
        new_volume = max(current_volume - 0.02, 0.01)
        service.call("media_player", "volume_set", entity_id=media_player_obj.entity_id, volume_level=new_volume)

    elif event_name == "pause":
        media_player.volume_mute(entity_id=media_player_obj.entity_id, is_volume_muted=True)
    elif event_name == "play":
        media_play(media_player_obj)
    elif event_name == "mute":
        media_player.volume_mute(entity_id=media_player_obj.entity_id, is_volume_muted=not media_player_obj.is_volume_muted)
    elif event_name == "stop":
        media_player.media_pause(entity_id=media_player_obj.entity_id)
    elif event_name in ["next_song", "skip_to_end"]:
        play_next_song_or_station(media_player_obj)
    elif event_name in ["last_song", "skip_to_last"]:
        play_next_song_or_station(media_player_obj, inverse=True)
    elif "preset" in event_name:
        preset_number = int(event_name.split("_")[-1])
        if preset_number == 0:
            play_dab_preset("Internet radio/preset/10")
        else:
            play_dab_preset(f"Internet radio/preset/{preset_number}")
            



@event_trigger("esphome.ir_touch")
def handle_ir_blaster_touch_event(**kwargs):
    event_name = kwargs.get("name", "")
    media_player_obj = media_player.entre
    pause_or_play(media_player_obj)



