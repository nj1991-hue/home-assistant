import asyncio

TAG = "kokken-now-playing"


def get_metadata():
    """Pull header/title/subtitle off the pyscript.media_metadata entity."""
    header = state.getattr("pyscript.media_metadata").get("kokken_media_header")
    title = state.getattr("pyscript.media_metadata").get("kokken_media_title")
    subtitle = state.getattr("pyscript.media_metadata").get("kokken_media_subtitle")
    return header, title, subtitle


def notify(header, message):
    data = {
        "tag": TAG,
        "notification_icon": "mdi:music",
        "notification_icon_color": "#30D158",
        "background_color": "#101820",
        "text_color": "#FFFFFF",
        "silent": True,
        "live_update": True,
        "critical_text": header,
    }

    service.call(
        "notify",
        "mobile_app_nick_s_iphone",
        title="Now playing",
        message=message,
        data=data,
    )


def clear_notification():
    service.call(
        "notify",
        "mobile_app_nick_s_iphone",
        message="clear_notification",
        data={"tag": TAG},
    )


@state_trigger("media_player.kokken")
@state_trigger("pyscript.media_metadata.kokken_media_header")
@state_trigger("pyscript.media_metadata.kokken_media_title")
@state_trigger("pyscript.media_metadata.kokken_media_subtitle")
def kitchen_now_playing(**kwargs):
    task.unique("kitchen_live_activity")
    asyncio.sleep(3)
    
    player_state = state.get("media_player.kokken")
    home_state = state.get("device_tracker.nick_s_iphone")
    
    if player_state == "playing" and home_state == "home":
        log.info("Updating now-playing notification")
    
        header, title, subtitle = get_metadata()
        message = f"{title} — {subtitle}"

        notify(header, message)
    else:
        log.info("Clearing now-playing notification. Unless something happens in the coming 60-seconds")
        asyncio.sleep(60)
        clear_notification()
        

@state_trigger("device_tracker.nick_s_iphone")
def clear_notifications_when_leaving_the_house(value=None):
    if value and value != "home":
        clear_notification()
        

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    