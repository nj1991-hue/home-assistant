import asyncio

@service
def close_entre_window():
    task.unique("close_entre_window")
    counter=0
    while binary_sensor.hue_secure_contact_sensor_entre_velux_opening == "on":
        log.info(f"Closing Entre velux window, attempt {counter}")

        remote.send_command(
            entity_id="remote.broadlink_universal_remote",
            num_repeats= 12,
            delay_secs= 0.4,
            hold_secs= 0,
            command= "close_window",
            device= "velux_window_remote"
        )
 
        asyncio.sleep(60)
        counter+=1
        
        # Never give up. Closing is important (like when it rains)
        if counter > 10:
            log.warning(    
                "Looks like the entre window isn't closing. "
                f"This is attempt {counter}. "
            )

@service
def open_entre_window():
    task.unique("open_entre_window")
    counter=0
    while binary_sensor.hue_secure_contact_sensor_entre_velux_opening == "off":
        log.info(f"Opening Entre velux window, attempt {counter}")

        remote.send_command(
            entity_id="remote.broadlink_universal_remote",
            num_repeats= 12,
            delay_secs= 0.4,
            hold_secs= 0,
            command= "open_window",
            device= "velux_window_remote"
        )
 
        asyncio.sleep(60)
        counter+=1
        
        if counter > 10:
            log.warning(    
                "Looks like the entre window isn't opening. "
                f"This is attempt {counter}. "
            )

        
