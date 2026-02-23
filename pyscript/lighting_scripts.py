import asyncio
import random
import datetime

@service
def sun_is_down():
    """
    Returns True if the sun is down, False if it is up.
    """
    return sensor.sun_next_dusk > sensor.sun_next_dawn
    
@service
def sun_is_up():
    """
    Returns True if the sun is up, False if it is down.
    """
    return not sun_is_down()
    

@state_trigger("input_text.home_state")
def turn_stue_light_off(value = None):
    task.unique("turn_stue_light_off")
    plug_entity_id = "switch.aqara_smart_plug_eu_001"
    if "away" in value.lower() or "night" in value.lower():

        # Turn the switch off - the light will turn off
        log.info(f"Turning {plug_entity_id} off")
        switch.turn_off(entity_id=plug_entity_id)

        # Turn the switch back on - the light will not turn on
        asyncio.sleep(10)
        switch.turn_on(entity_id=plug_entity_id)
        
        
@service
@time_trigger("cron(* * * * *)")
def make_sure_plug_is_always_on():
    task.unique("turn_stue_light_off", kill_me=True)
    plug_entity_id = "switch.aqara_smart_plug_eu_001"
    plug_state = state.get(plug_entity_id)

    if plug_state == "off":
        log.info("Turning plug on")
        switch.turn_on(entity_id=plug_entity_id)


@service
@time_trigger("cron(*/30 * * * *)")
def simulate_lights_when_away():
    entity_ids = ["light.entre"]

    # Only run when on holiday.
    if input_text.on_holiday != "True":
        return
    
    now = datetime.datetime.now()
    hour = now.hour

    for entity_id in entity_ids:
        if sun_is_up():
            log.info(f"Turning light off in {entity_id} because the sun is up")
            light.turn_off(entity_id=entity_id)  
        elif hour < 17:
            log.info(f"Turning light off in {entity_id} because hour < 17")
            light.turn_off(entity_id=entity_id)  
        elif hour > 23:
            log.info(f"Turning light off in {entity_id} because hour > 23")
            light.turn_off(entity_id=entity_id)  
        else:
            if random.choice([True, False]):
                log.info(f"Turning light on in {entity_id}")
                light.turn_on(entity_id=entity_id)
            else:
                log.info(f"Turning light off in {entity_id}")

                light.turn_off(entity_id=entity_id)