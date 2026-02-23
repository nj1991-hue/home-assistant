import re
import time
import json
import datetime
import asyncio
import aiohttp
import aiofiles

entities_to_turn_on = {}

get_tado_rooms_devices_last_called = None

tado_key_dict = {
    "TV Stue": "stue",
    "Spisestue": "spisestue",
    "Køkken": "kokken",
    "Orangerie": "orangerie",
    #"Toilet": "toilet",
    "Soveværelse": "nania",
    " Sashas værelse": "sasha",
    "Mattias værelse": "mattias",
    "Kontor": "kontor",
    "Entre": "entre"
}

@service
def increment_request_counter():
    counter.increment(entity_id="counter.tado_api_requests")

@service
@time_trigger("cron(0 0 * * *)")
def reset_request_counter():
    counter.reset(entity_id="counter.tado_api_requests")


def get_entity_dict():
    return {
        "stue": climate.smart_radiator_stue,
        "spisestue": climate.smart_radiator_spisestue,
        "kokken": climate.smart_radiator_kokken,
        "orangerie": climate.smart_radiator_orangerie,
        #"toilet": climate.smart_radiator_toilet,
        "nania": climate.smart_radiator_nania,
        "sasha": climate.smart_radiator_sasha,
        "mattias": climate.smart_radiator_mattias,
        "kontor": climate.smart_radiator_kontor,
        "entre": climate.smart_radiator_entre,
    }

def get_hour(time_string):
    return int(time_string.split(":")[0])


def get_away_temperature(room):
    if room == "entre":
        return 18
    else:
        return 15


def get_away_temperature_from_api(room):
    response = service.call("shell_command", 
                     "get_tado_away_schedule_json", 
                     blocking=True,
                     return_response=True,
                     room = room)
                     
    stdout = json.loads(response["stdout"])
    
    return float(stdout["awayTemperatureCelsius"])


def get_schedule_temperature_from_dict(room, home_state):
    
    # key : [morning, afternoon, evening, night temperature]
    schedule = {
        "stue": [20, 20, 20, 18],
        "spisestue": [20, 20, 20, 18],
        "kokken": [21, 21, 21, 18],
        "orangerie": [20, 20, 20, 18],
        "toilet": [19, 19, 19, 18],
        "nania": [18, 18, 18, 18],
        "sasha": [16, 16, 20, 20],
        "mattias": [16, 16, 19.5, 19.5],
        "kontor": [16, 16, 16, 16],
        "entre": [20, 20, 20, 20],
    }
    away_temperature = get_away_temperature(room)

    temperatures = schedule[room]
    
    home_state=home_state.lower()
    
    if "morning" in home_state:
        temperature = temperatures[0]
    elif "afternoon" in home_state:
        temperature = temperatures[1]
    elif "evening" in home_state:
        temperature = temperatures[2]
    elif "night" in home_state:
        temperature = temperatures[3]
    elif home_state == "away":
        temperature = away_temperature
    else:
        temperature = None
        
    return temperature



def get_schedule_temperature_from_api(room, home_state):
    response = service.call("shell_command", 
                     "get_tado_schedule_json", 
                     blocking=True,
                     return_response=True,
                     room = room)
                     
    stdout = response["stdout"]

    if "schedule" not in stdout:
        log.warning(f"Falling back to dict; stdout does not contain the schedule: {stdout}")
        return get_schedule_temperature_from_dict(room, home_state)

    schedule = json.loads(stdout)["schedule"]

    day_to_look_for = datetime.date.today().strftime("%A").lower()
    home_state = home_state.lower()

    away_temperature = get_away_temperature_from_api(room)

    if "morning" in home_state:
        time_to_look_for = "09:00"
    elif "afternoon" in home_state:
        time_to_look_for = "13:00"
    elif "evening" in home_state:
        time_to_look_for = "20:00"
    elif "night" in home_state:
        time_to_look_for = "01:00"
    elif "away" in home_state:
        temperature =  away_temperature
        time_to_look_for = None
    else:
        temperature = None
        time_to_look_for = None
    
    if time_to_look_for:
        hour_to_look_for = get_hour(time_to_look_for)
        
        for entry in schedule:
            start_hour = get_hour(entry["start"])
            end_hour = get_hour(entry["end"])
            day = entry["dayType"].lower()
        
            if (
                hour_to_look_for > start_hour
                and hour_to_look_for <= end_hour
                and day_to_look_for == day
            ):
                temperature = float(entry["setting"]["temperature"]["value"])
                break
    return temperature


@service
def set_home_state_to_home():
    
    hour = datetime.datetime.now().hour
    
    if hour < 12:
        home_state = "Home - Morning"
    else:
        if hour < 17:
            home_state = "Home - Afternoon"
        else:
            home_state = "Home - Evening"
            
    log.info(f"Setting home_state to '{home_state}'")
    input_text.home_state = home_state


@service
@state_trigger("input_text.home_state")
def set_tado_temperature_according_to_schedule(old_value = None):
    """
    Set tado temperature based on schedule.
    """
    if old_value:
        # Automation was triggered by home-state
        old_home_state = old_value.lower()
    else:
        # Automation was triggered as a service
        old_home_state = ""
        set_home_state_to_home() # A triggered service means someone is home
        get_tado_schedule() # Update the schedule using an API call

    home_state = input_text.home_state.lower()

    if "away" in old_home_state and "away" not in home_state:
        change_presence_to_home()
    elif "away" not in old_home_state and "away" in home_state:
        change_presence_to_away()

    entity_dict = get_entity_dict()
    for thermostat in entity_dict.keys():
        thermostat_entity = entity_dict[thermostat]
        if not hasattr(thermostat_entity, "temperature"):
            log.warning(
                f"Could not set temperature according to schedule for {thermostat}; "
                f"entity = {thermostat_entity}"
            )
            continue
        
        temperature = get_schedule_temperature_from_api(thermostat, home_state)
    
        old_temperature = get_schedule_temperature_from_api(thermostat, old_home_state)
        old_tado_temperature = float(thermostat_entity.temperature)

        if (
            old_temperature 
            and old_temperature != old_tado_temperature
            and "home" in old_home_state
            and "home" in home_state
            and "night" not in home_state
            and "night" not in old_home_state
            and old_temperature == temperature
            ):
            log.info(f"Not setting temperature at {thermostat} because it was manually set to {old_tado_temperature}")
        else:
            log.info(f"setting temperature to {temperature} at {thermostat} because home state = {home_state}")

            room = thermostat_entity.entity_id.split("_")[-1]
            helper_entity_id = f"input_number.{room}_temperature_helper"
            
            input_number.set_value(entity_id=helper_entity_id, value = temperature)


@state_trigger("binary_sensor.aqara_door_and_window_sensor_kontor")
@state_trigger("binary_sensor.aqara_door_and_window_sensor_mattias")
@state_trigger("binary_sensor.aqara_door_and_window_sensor_sasha")
@state_trigger("binary_sensor.aqara_door_and_window_sensor_nania")
@state_trigger("binary_sensor.aqara_door_and_window_sensor_kontor_right")
def set_aqara_window_helper(value=None, var_name=None, old_value=None):
    
    helper_name = (var_name + "_helper").replace("binary_sensor.","input_text.")
    task.unique(var_name)
    
    if value == "off":
        asyncio.sleep(30)

    service.call("input_text", "set_value", entity_id=helper_name, value=value)

        
@state_trigger("binary_sensor.kokkenvindue_opening")
@state_trigger("binary_sensor.badevaerelse_vindue_opening")
@state_trigger("binary_sensor.spisestue_venstre_vindue_opening")
@state_trigger("binary_sensor.spisestue_hojre_vindue_opening")
@state_trigger("binary_sensor.spisestue_terrassedor_opening")
@state_trigger("binary_sensor.stuevindue_mod_vej_opening")
@state_trigger("binary_sensor.stuevindue_mod_nabo_have_opening")
@state_trigger("binary_sensor.mellemgang_terrassedor_opening")
@state_trigger("binary_sensor.fordor_opening")
@state_trigger("input_text.aqara_door_and_window_sensor_kontor_helper")
@state_trigger("input_text.aqara_door_and_window_sensor_mattias_helper")
@state_trigger("input_text.aqara_door_and_window_sensor_sasha_helper")
@state_trigger("input_text.aqara_door_and_window_sensor_nania_helper")
@state_trigger("input_text.aqara_door_and_window_sensor_kontor_right_helper")
def turn_tado_off_when_windows_open(value=None, var_name=None, old_value=None):
    global entities_to_turn_on

    windows_to_check = [
        binary_sensor.kokkenvindue_opening,
        binary_sensor.badevaerelse_vindue_opening,
        binary_sensor.spisestue_venstre_vindue_opening,
        binary_sensor.spisestue_hojre_vindue_opening,
        binary_sensor.spisestue_terrassedor_opening,
        binary_sensor.stuevindue_mod_vej_opening,
        binary_sensor.stuevindue_mod_nabo_have_opening,
        binary_sensor.mellemgang_terrassedor_opening,
        binary_sensor.fordor_opening,
        binary_sensor.aqara_door_and_window_sensor_kontor,
        binary_sensor.aqara_door_and_window_sensor_kontor_right,
        binary_sensor.aqara_door_and_window_sensor_mattias,
        binary_sensor.aqara_door_and_window_sensor_sasha,
        binary_sensor.aqara_door_and_window_sensor_nania,
        ]


    entities_to_turn_off_dict = {
        ".*mattias.*": [climate.smart_radiator_mattias],
        ".*sasha.*": [climate.smart_radiator_sasha],
        ".*kontor.*": [climate.smart_radiator_kontor],
        ".*nania.*": [climate.smart_radiator_nania],
        #".*badevaerelse.*": [climate.smart_radiator_toilet],
        r"\b(.*kokken.*|.*mellemgang.*|.*fordor.*|.*stue.*)\b": [
            climate.smart_radiator_kokken,
            climate.smart_radiator_orangerie,
            #climate.smart_radiator_toilet,
            climate.smart_radiator_stue,
            climate.smart_radiator_spisestue
        ],
    }

    for pattern, entities in entities_to_turn_off_dict.items():
        if re.match(pattern, var_name):
            for entity in entities:
                if value == "on" and old_value == "off":
                    if entity == "heat":
                        log.info(f"Turning {entity.entity_id} off because {var_name} is open")
                        climate.turn_off(entity_id=entity.entity_id)
                        entities_to_turn_on[entity.entity_id] = True
                    else:
                        log.info(f"{entity.entity_id} is already off")
                elif value == "off" and old_value == "on":
                    open_windows = 0
                    
                    for window in windows_to_check:
                        if re.match(pattern, window.entity_id):
                            if window == "on":
                                log.info(f"{window.entity_id} is still open")
                                open_windows += 1
                    
                    if open_windows == 0:
                        turn_entity_on = entities_to_turn_on.pop(entity.entity_id, False)
                        if turn_entity_on:
                            log.info(f"Turning {entity.entity_id} on because {var_name} was closed")
                            climate.turn_on(entity_id=entity.entity_id)
                        else:
                            log.info(f"{entity.entity_id} was not turned on; It was off when a window was opened")
                    else:
                        log.info(
                            "climate entity not turned on; "
                            f"Number of open windows = {open_windows}."
                        )
                else:
                    log.debug(f"'{value}' is neither 'on' or 'off' ")


def get_tado_rooms_and_devices():
    global get_tado_rooms_devices_last_called
 
    if (
        get_tado_rooms_devices_last_called is None 
        or (time.time() - get_tado_rooms_devices_last_called) > 30
    ):
        get_tado_rooms_devices_last_called = time.time()
        increment_request_counter()
        service.call("shell_command", "get_tado_rooms_devices", blocking=True, home_id = pyscript.config["global"]["tado_home_id"])
    response = service.call("shell_command", "get_tado_rooms_devices_json", blocking=True, return_response=True)
    
    if response['stdout']:
        return json.loads(response["stdout"])
    else:
        #log.warning(f"No stdout in response: {response}")
        return None
    
@service
def check_tado_response():
    response = service.call("shell_command","get_tado_response_json", return_response=True)

    tado_response = json.loads(response["stdout"])
    
    if "refresh_token" in tado_response:
        input_text.tado_api_status = "ok"
    else:
        error = str(tado_response)
        input_text.tado_api_status = error[:255]  

#@state_trigger("climate.smart_radiator_toilet == 'heat'")
@state_trigger("climate.smart_radiator_entre == 'heat'")
@service
@time_trigger("cron(*/2 * * * *)")
@state_trigger("climate.smart_radiator_stue == 'heat'")
@state_trigger("climate.smart_radiator_spisestue == 'heat'")
@state_trigger("climate.smart_radiator_kokken == 'heat'")
@state_trigger("climate.smart_radiator_orangerie == 'heat'")
@state_trigger("climate.smart_radiator_nania == 'heat'")
@state_trigger("climate.smart_radiator_sasha == 'heat'")
@state_trigger("climate.smart_radiator_mattias == 'heat'")
@state_trigger("climate.smart_radiator_kontor == 'heat'")
async def adjust_offset(var_name = None):
    global tado_key_dict

    if var_name:
        log.info(f"Offset adjustment triggered by {var_name}")
    else:
        log.debug(f"Offset adjustment triggered")
    
    entity_dict = get_entity_dict()   
    
    temperature_sensor_dict = {
        "stue": sensor.aqara_temp_humidity_sensor_t1_temperature_stue,
        "spisestue": sensor.aqara_temp_humidity_sensor_spisestue_temperature,
        "mattias": sensor.aqara_temp_humidity_sensor_t1_temperature_mattias,
        "kokken": sensor.aqara_temp_humidity_sensor_t1_temperature_kokken,
        "orangerie": sensor.aqara_temp_humidity_sensor_t1_temperature_orangerie,
        #"toilet": sensor.aqara_temp_humidity_sensor_t1_temperature_toilet,
        "sasha": sensor.aqara_temp_humidity_sensor_sasha_temperature,
        "nania": sensor.aqara_temp_humidity_sensor_t1_temperature_nania,
        "kontor": sensor.aqara_temp_humidity_sensor_t1_temperature_kontor,
        "entre": sensor.entre_temperature
    }

    rooms_and_devices = get_tado_rooms_and_devices()

    # Retry - in case the json file was being updated while making the previous request.
    if not rooms_and_devices:
        await asyncio.sleep(5)
        rooms_and_devices = get_tado_rooms_and_devices()

    if not rooms_and_devices:
        log.warning("Tado rooms and devices is empty - offset cannot be adjusted")
        return

    rooms = {tado_key_dict[r["roomName"]]: r for r in rooms_and_devices["rooms"]}     

    for room_name, room in rooms.items():
        
        if var_name and var_name != f"climate.smart_radiator_{room_name}":
            continue

        real_temperature = temperature_sensor_dict.get(room_name)
        if not real_temperature:
            continue
        elif real_temperature == "unavailable":
            log.warning(f"Temperature from {real_temperature.entity_id} is unavailable")
            continue
        else:
            real_temperature = float(real_temperature)
            
        log.debug(f"Real temperature in {room_name} = {real_temperature}")
        for device in room["devices"]:
            tado_temperature = device["temperatureAsMeasured"]
            device_id = device["serialNumber"]

            log.debug(f"Tado temperature on {device_id} = {tado_temperature}")

            correct_offset = round(real_temperature - tado_temperature, 1)
            current_offset = device["temperatureOffset"]

            tado_entity = entity_dict[room_name]
            if (
                abs(correct_offset - current_offset) > 0.5
                and tado_entity == "heat"
            ):
                log.info(
                    f"Setting offset on {device_id} in {room_name} to {correct_offset}"
                )
                
                increment_request_counter()
                service.call("shell_command", 
                             "set_temperature_offset", 
                              blocking=True, 
                              device=device_id,
                              offset=correct_offset,
                              home_id = pyscript.config["global"]["tado_home_id"]
                              )
            else:
                log.debug(f"No action needed; Current offset = {current_offset} and correct offset = {correct_offset}")


@service
@time_trigger("cron(0 1 * * *)")
def get_tado_schedule():
    
    zone_dict = {2: "stue",
                 7: "spisestue",
                 5: "kokken",
                 10: "orangerie",
                 #11: "toilet",
                 15: "nania",
                 12: "sasha",
                 14: "mattias",
                 13: "kontor",
                 16: "entre",
                 
                     
    }
    
    for zone, room in zone_dict.items():
    
        increment_request_counter()
        service.call("shell_command", 
                     "get_tado_schedule", 
                     blocking=True,
                     home_id = pyscript.config["global"]["tado_home_id"],
                     zone = zone, 
                     room = room)
        
        increment_request_counter()
        service.call("shell_command", 
                     "get_tado_away_schedule", 
                     blocking=True,
                     home_id = pyscript.config["global"]["tado_home_id"],
                     zone = zone, 
                     room = room)        
        
#@state_trigger("climate.smart_radiator_toilet.temperature")
@state_trigger("climate.smart_radiator_entre.temperature")
@state_trigger("climate.smart_radiator_orangerie.temperature")
@state_trigger("climate.smart_radiator_kokken.temperature")
@state_trigger("climate.smart_radiator_stue.temperature")
@state_trigger("climate.smart_radiator_spisestue.temperature")
@state_trigger("climate.smart_radiator_sasha.temperature")
@state_trigger("climate.smart_radiator_mattias.temperature")
@state_trigger("climate.smart_radiator_nania.temperature")
@state_trigger("climate.smart_radiator_kontor.temperature")
def set_tado_helper_value_when_temperature_changes(var_name=None, value=None, old_value=None):
    
    if not hasattr(value, "temperature"):
        return
    
    room = var_name.split("_")[-1]
    helper_entity_id = f"input_number.{room}_temperature_helper"
    value_to_set = float(min(max([value.temperature, 15]), 25))
    current_value = float(state.get(helper_entity_id))
    
    if value_to_set != current_value:
        log.info(f"Temperature changed from {old_value.temperature} to {value.temperature} at {var_name}. Setting {helper_entity_id} to {value_to_set}.")
        input_number.set_value(entity_id=helper_entity_id, value = value_to_set)
    


#@state_trigger("input_number.toilet_temperature_helper")
@state_trigger("input_number.entre_temperature_helper")
@state_trigger("input_number.orangerie_temperature_helper")
@state_trigger("input_number.kokken_temperature_helper")
@state_trigger("input_number.stue_temperature_helper")
@state_trigger("input_number.spisestue_temperature_helper")
@state_trigger("input_number.nania_temperature_helper")
@state_trigger("input_number.mattias_temperature_helper")
@state_trigger("input_number.sasha_temperature_helper")
@state_trigger("input_number.kontor_temperature_helper")
def set_tado_temperature_when_helper_changes_state(var_name=None, value=None):
    # If another task starts within 30 seconds - kill it
    # So we run only the latest task
    task.unique(var_name)
    task.sleep(30)

    room = var_name.split('.')[1].split("_")[0]
    tado_entity_id = f"climate.smart_radiator_{room}"
    current_temperature = float(state.getattr(tado_entity_id)["temperature"])
    new_temperature = float(value)
    
    if new_temperature != current_temperature:
        log.info(f"Temperature helper changed state to {new_temperature}. Adjusting {tado_entity_id}.")
        climate.set_temperature(entity_id=tado_entity_id, temperature = new_temperature)
        
        
async def initiate_device_flow(session):
    url = "https://login.tado.com/oauth2/device_authorize"
    data = {
        "client_id": "1bb50063-6b0c-4d11-bd99-387f4a91cc46",
        "scope": "offline_access",
    }
    increment_request_counter()
    async with await session.post(url, data=data) as response:
        return await response.json() 
        
async def complete_device_flow(session, device_code):
    url = "https://login.tado.com/oauth2/token"
    
    data=dict(
        client_id="1bb50063-6b0c-4d11-bd99-387f4a91cc46",
        device_code=device_code,
        grant_type="urn:ietf:params:oauth:grant-type:device_code",
    )

    increment_request_counter()
    async with await session.post(url, data=data) as response:
        return await response.json() 

async def obtain_new_refresh_token(session, refresh_token):
    url = "https://login.tado.com/oauth2/token"
    
    data=dict(
        client_id="1bb50063-6b0c-4d11-bd99-387f4a91cc46",
        grant_type="refresh_token",
        refresh_token=refresh_token,
    )

    increment_request_counter()
    async with await session.post(url, data=data) as response:
        return await response.json() 

async def dump_tado_response(tado_response):
    filename = "/config/tado_response.json"
    json_object = json.dumps(tado_response)
    async with aiofiles.open(filename, mode='w') as f:
        f.write(json_object)
        
@service
def refresh_tado_token():
    filename = "/config/tado_response.json"
    async with aiofiles.open(filename, mode='r') as f:
        contents = await f.read()
        tado_response = json.loads(contents)
        refresh_token = tado_response.get("refresh_token",None)

    async with aiohttp.ClientSession() as session:
        if refresh_token:
            response = await obtain_new_refresh_token(session, refresh_token)
            await dump_tado_response(response)
        else:
            log.warning(r"Failed to refresh tado token; tado_response = {tado_response}")
    
@service
def authorize_tado_api():
    async with aiohttp.ClientSession() as session:
        device_flow_response = await initiate_device_flow(session)
        input_text.tado_verification_uri_complete = device_flow_response["verification_uri_complete"]
        
        interval = device_flow_response["interval"]
        expires_in = device_flow_response["expires_in"]
        device_code = device_flow_response["device_code"]
        
        attempts = int(expires_in / interval)
        for attempt in range(attempts):
            completed_flow_response = complete_device_flow(session,device_code)
            if "refresh_token" in completed_flow_response:
                await dump_tado_response(completed_flow_response)
                input_text.tado_verification_uri_complete = ""
                break
            await asyncio.sleep(interval)
    check_tado_response()


async def change_presence(state):
    """
    Sets Tado Home Presence to either "HOME" or "AWAY".
    Accepts: state = "HOME" or "AWAY"
    """

    home_id = pyscript.config["global"]["tado_home_id"]
    url = f"https://my.tado.com/api/v2/homes/{home_id}/presenceLock"

    # Ensure state is uppercase as expected by Tado API
    state = state.upper()
    if state not in ["HOME", "AWAY"]:
        log.warning(f"Invalid presence state '{state}' – must be 'HOME' or 'AWAY'")
        return

    # Retrieve access token
    access_token_response = service.call(
        "shell_command", "get_tado_access_token", blocking=True, return_response=True
    )
    access_token = access_token_response.get("stdout", "").strip()
    if not access_token:
        log.warning("Missing Tado access token – cannot change presence")
        return

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    payload = {"homePresence": state}

    log.info(f"Setting Tado home presence to '{state}'")

    try:
        async with aiohttp.ClientSession() as session:
            increment_request_counter()
            async with session.put(url, headers=headers, json=payload) as response:
                if response.status in (200, 204):
                    # 204 = success (no content returned)
                    log.info(f"Tado presence successfully changed to '{state}' (HTTP {response.status})")
                    input_text.tado_api_status = "ok"
                else:
                    # log any other status code and response body
                    text = await response.text()
                    log.warning(
                        f"Failed to change Tado presence. HTTP {response.status}: {text}"
                    )
                    input_text.tado_api_status = f"error {response.status}"
    except Exception as e:
        log.error(f"Exception while changing Tado presence: {e}")

@service
def change_presence_to_home():
    change_presence("HOME")

@service
def change_presence_to_away():
    change_presence("AWAY")
    


                    
                    