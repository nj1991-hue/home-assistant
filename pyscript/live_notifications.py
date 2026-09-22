import asyncio

NOTIFY_SERVICE = "notify.mobile_app_nick_s_iphone"
PLAYER = "media_player.kokken"
META = "pyscript.media_metadata"
TAG = "kokken-now-playing"


def get_metadata():
    """Pull header/title/subtitle off the pyscript.media_metadata entity."""
    header = state.getattr(META).get("kokken_media_header")
    title = state.getattr(META).get("kokken_media_title")
    subtitle = state.getattr(META).get("kokken_media_subtitle")
    return header, title, subtitle


def notify(title, message, live=True):
    data = {
        "tag": TAG,
        "notification_icon": "mdi:music",
        "notification_icon_color": "#30D158",
        "background_color": "#101820",
        "text_color": "#FFFFFF",
    }
    if live:
        data["live_update"] = True
    data["silent"] = True

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

    player_state = state.get(PLAYER)

    if player_state == "playing":
        task.sleep(0.8)  # let media_title/artist settle
        if state.get(PLAYER) != "playing":
            return  # bailed, state changed during the delay

        header, title, subtitle = get_metadata()
        message = f"{title} — {subtitle}" if subtitle else title

        notify(
            title=header,
            message=message,
        )

    elif player_state == "paused":
        header, title, subtitle = get_metadata()
        message = f"⏸ {title} — {subtitle}" if subtitle else f"⏸ {title}"

        notify(
            title=header,
            message=message,
        )

        task.sleep(90)
        if state.get(PLAYER) != "playing":
            clear_notification()

    else:  # idle / off / paused-timeout etc.
        clear_notification()


    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    