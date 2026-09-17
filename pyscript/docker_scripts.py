state.persist('pyscript.docker_status')

def get_entity_ids(param):
    entity_ids = {}
    for entity_id in state.names():
        if entity_id.startswith("sensor.docker") and entity_id.endswith(param):
            container_name = entity_id.replace("sensor.docker_", "").replace(f"_{param}", "")
            entity_ids[container_name] = entity_id
    return entity_ids


def _update_docker_status():
    attrs = {}
    up_count = 0
    container_count = 0
    
    log.info("Updating docker status")

    for container_name, entity_id in get_entity_ids("status").items():
        container_state = state.get(entity_id)
        attrs[container_name] = container_state
        if "Up" in container_state:
            up_count += 1
        container_count += 1

    docker_state = "ok" if container_count and up_count == container_count else "error"
    state.set("pyscript.docker_status", docker_state, attrs)


_docker_triggers = {}

def _register_docker_triggers(param, func):
    """
    Register triggers for a function.
    
    i.e when called with "status" and _update_docker_status: 
    
    _update_docker_status will run when sensor.docker_bazarr_status changes
    state but also when sensor.docker_radarr_status changes state and so on.
    """
    
    
    current_ids = set(get_entity_ids(param).values())

    # add triggers for any brand-new sensors
    for entity_id in current_ids:
        if entity_id in _docker_triggers:
            continue

        @state_trigger(entity_id)
        def _trig(value=None, entity_id=entity_id, func=func):
            func()

        _docker_triggers[entity_id] = _trig

    # drop (and thereby destroy) triggers for sensors that vanished
    for entity_id in list(_docker_triggers):
        if entity_id not in current_ids:
            del _docker_triggers[entity_id]



# This runs when a NEW docker entry is added to HASS AND on startup
@service
@event_trigger("entity_registry_updated")
@time_trigger("startup")
def update_docker_status(**kwargs):
    _register_docker_triggers("status", _update_docker_status)
    _update_docker_status()

