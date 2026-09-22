import asyncio

TAG = "kokken-now-playing"


def get_metadata():
    """Pull header/title/subtitle off the pyscript.media_metadata entity."""
    header = state.getattr("pyscript.media_metadata").get("kokken_media_header")
    title = state.getattr("pyscript.media_metadata").get("kokken_media_title")
    subtitle = state.getattr("pyscript.media_metadata").get("kokken_media_subtitle")
    return header, title, subtitle


def notify(title, message):
    data = {
        "tag": TAG,
        "notification_icon": "mdi:music",
        "notification_icon_color": "#30D158",
        "background_color": "#101820",
        "text_color": "#FFFFFF",
        "silent": True,
        "live_update": True,
    }

    service.call(
        "notify",
        "mobile_app_nick_s_iphone",
        title=title,
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
@state_trigger("pyscript.media_metadata.*")
def kitchen_now_playing(**kwargs):
    task.unique("kitchen_live_activity")
    log.info("Updating now-playing")

    player_state = state.get("media_player.kokken")
    home_state = state.get("device_tracker.nick_s_iphone")

    if player_state == "playing" and home_state == "Home":
    
        header, title, subtitle = get_metadata()
        message = f"{title} — {subtitle}" if subtitle else title

        notify(
            title=header,
            message=message,
        )

    else:
        clear_notification()

@state_trigger("device_tracker.nick_s_iphone")
def clear_notifications_when_leaving_the_house(value=None):
    if value and "away" in value.lower():
        clear_notification()
        
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    