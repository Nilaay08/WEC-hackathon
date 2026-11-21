from settings import (BATTERY_FAILURE, BATTERY_SIZE, CLOUDY, GENERATOR_FAILURE, GRID_FAILURE,
                      LECTURE_HALL, SOLAR_LIMIT)

TINY = 0.000001   

def check_answer(message, answer, battery_before):

    problems = []
    event = message.get("random_event", "none")
    buildings = message.get("loads", [])
    rows = answer["buildings"]

    if len(rows) != len(buildings):
        return ["wrong number of buildings in the answer"]

    total_solar = sum(r["solar"] for r in rows)
    total_battery = sum(r["battery"] for r in rows)
    total_grid = sum(r["grid"] for r in rows)

    for i, (b, r) in enumerate(zip(buildings, rows)):
        got = r["solar"] + r["battery"] + r["grid"]
        if min(r["solar"], r["battery"], r["grid"]) < 0:
            problems.append(f"building {i}: negative energy")
        if b.get("type") == LECTURE_HALL and r["solar"] > TINY:
            problems.append(f"building {i}: lecture hall got solar")
        if got > b.get("load", 0) + TINY:
            problems.append(f"building {i}: got more than it needs")
        if got < b.get("load", 0) - TINY and event != GRID_FAILURE:
            problems.append(f"building {i}: did not get enough energy")

    if total_solar > (0 if event == CLOUDY else SOLAR_LIMIT) + TINY:
        problems.append("used more solar than available")
    if total_battery > (0 if event == BATTERY_FAILURE else battery_before) + TINY:
        problems.append("used more battery than is stored")
    if event == GRID_FAILURE and total_grid > TINY:
        problems.append("used the grid while it was down")
    if answer["generator"] > TINY and event in (GENERATOR_FAILURE, BATTERY_FAILURE):
        problems.append("used the generator while it (or the battery) was broken")
    if battery_before - total_battery + answer["generator"] > BATTERY_SIZE + TINY:
        problems.append("battery would be filled past 100")
    return problems
