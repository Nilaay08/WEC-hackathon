from memory import state
from settings import (BATTERY_FAILURE, BATTERY_SIZE, CLOUDY, GENERATOR_COST, GENERATOR_FAILURE,
                      GRID_FAILURE, HOURS_IN_DAY, LECTURE_HALL, MIN_RESERVE, RESERVE_FACTOR,
                      SOLAR_LIMIT, STOP_REFILL_HOURS)

def decide(message):
    
    event = message.get("random_event", "none")
    price = float(message.get("grid_price", 0))
    cloudy_next_hour = message.get("forecast") == "cloudy"
    buildings = message.get("loads", [])

    
    solar_works = event != CLOUDY
    grid_works = event != GRID_FAILURE
    battery_works = event != BATTERY_FAILURE
    generator_works = event != GENERATOR_FAILURE

    hours_left = HOURS_IN_DAY - state["hour"]
    last_hours = hours_left <= STOP_REFILL_HOURS

    
    answer = []
    still_needs = []
    for b in buildings:
        answer.append({"solar": 0, "battery": 0, "grid": 0})
        still_needs.append(float(b.get("load", 0)))

    
    solar_left = SOLAR_LIMIT if solar_works else 0
    for i, b in enumerate(buildings):
        if b.get("type") == LECTURE_HALL:
            continue
        give = min(still_needs[i], solar_left)
        answer[i]["solar"] = give
        still_needs[i] -= give
        solar_left -= give

    
    can_refill_later = generator_works and battery_works and not last_hours
    if not battery_works:
        use_battery = False                     
    elif not grid_works:
        use_battery = True                      
    elif last_hours:
        use_battery = True                      
    elif price > GENERATOR_COST and can_refill_later:
        use_battery = True                      
    else:
        use_battery = False                     

    battery_used = 0
    if use_battery:
        
        order = sorted(range(len(buildings)),
                       key=lambda i: buildings[i].get("type") != LECTURE_HALL)
        for i in order:
            give = min(still_needs[i], state["battery"] - battery_used)
            answer[i]["battery"] = give
            still_needs[i] -= give
            battery_used += give

    
    if grid_works:
        for i in range(len(buildings)):
            answer[i]["grid"] = still_needs[i]
            still_needs[i] = 0

    
    battery_after = state["battery"] - battery_used
    generator = 0
    if can_refill_later:
        
        lecture_need = sum(float(b.get("load", 0)) for b in buildings if b.get("type") == LECTURE_HALL)
        other_need = sum(float(b.get("load", 0)) for b in buildings if b.get("type") != LECTURE_HALL)
        if cloudy_next_hour:
            outage_need = lecture_need + other_need                       
        else:
            outage_need = lecture_need + max(0, other_need - SOLAR_LIMIT)  
        target = min(BATTERY_SIZE, max(MIN_RESERVE, RESERVE_FACTOR * outage_need))
        generator = max(0, target - battery_after)

    return {"buildings": answer, "generator": generator}
