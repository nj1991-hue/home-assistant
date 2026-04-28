
def mute_or_play(media_player_obj):
    if media_player_obj == "playing":
        mute = not media_player_obj.is_volume_muted
        
        if mute:
            log.info(f"Muting {media_player_obj.entity_id}")
        else:
            log.info(f"Unmuting {media_player_obj.entity_id}")
        media_player.volume_mute(entity_id=media_player_obj.entity_id, is_volume_muted=mute)

    elif media_player_obj == "idle":
        media_player.play_media(
            media_content_id="x-rincon-stream:RINCON_804AF2CAFA8001400", 
            media_content_type="music",
            entity_id=media_player_obj.entity_id
        )

    else:
        log.info(f"Starting playback on {media_player_obj.entity_id}")
        media_player.media_play(entity_id=media_player_obj.entity_id)


@event_trigger("esphome.ir_signal")
def handle_edifier_remote_events(**kwargs):
    event_name = kwargs.get("name", "")
    media_player_obj = media_player.entre
    
    log.info(f"Received {event_name} event from edifier remote")
    
    if event_name == "toggle_power":
        mute_or_play(media_player_obj)
    elif event_name == "volume_up":
        if media_player_obj.is_volume_muted:
            log.info(f"Unmuting {media_player_obj.entity_id}")
            media_player.volume_mute(entity_id=media_player_obj.entity_id, is_volume_muted=False)
        else:
            log.info(f"Increasing volume on {media_player_obj.entity_id}")
            current_volume = media_player_obj.volume_level
            new_volume = current_volume+0.02
            service.call("media_player", "volume_set", entity_id=media_player_obj.entity_id, volume_level=new_volume)
            
    elif event_name == "volume_down":
        log.info(f"Decreasing volume on {media_player_obj.entity_id}")
        current_volume = media_player_obj.volume_level
        new_volume = max(current_volume - 0.02, 0.01)
        service.call("media_player", "volume_set", entity_id=media_player_obj.entity_id, volume_level=new_volume)

@event_trigger("esphome.ir_touch")
def handle_ir_blaster_touch_event(**kwargs):
    event_name = kwargs.get("name", "")
    media_player_obj = media_player.entre
    mute_or_play(media_player_obj)



