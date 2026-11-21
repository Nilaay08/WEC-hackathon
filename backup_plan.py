from settings import CLOUDY, GRID_FAILURE, LECTURE_HALL, SOLAR_LIMIT

def backup_answer(message):

    grid_works = message.get("random_event") != GRID_FAILURE
    solar_left = 0 if message.get("random_event") == CLOUDY else SOLAR_LIMIT
    rows = []
    for b in message.get("loads", []):
        load = float(b.get("load", 0))
        solar = 0 if b.get("type") == LECTURE_HALL else min(load, solar_left)
        solar_left -= solar
        rows.append({"solar": solar, "battery": 0, "grid": (load - solar) if grid_works else 0})
    return {"buildings": rows, "generator": 0}
