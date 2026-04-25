import asyncio

@service
def close_entre_window():
    task.unique("close_entre_window")
    counter=0
    while binary_sensor.hue_secure_contact_sensor_entre_velux_opening == "on":
        log.info(f"Closing Entre velux window, attempt {counter}")
        button.press(entity_id="button.xiao_smart_ir_mate_c07738_close_window")
        asyncio.sleep(1)
        counter+=1
        
        # Never give up. Closing is important (like when it rains)
