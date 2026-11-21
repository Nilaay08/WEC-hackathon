"""
WEC 2026 - Campus Microgrid Controller
======================================

WHAT THIS PROGRAM DOES
  Once per simulated hour (24 times) the server sends us:
    - the random event (which source is broken this hour, if any)
    - a 75%-accurate weather forecast for the NEXT hour
    - every building's load
    - the grid price this hour ("grid_cost", $0.50 - $2.00 per unit) 
  We reply with where each building's energy comes from (solar / battery / grid)
  and how much the generator produces. Goal: lowest total cost, every building served.

HOW TO RUN IT
  Competition (server already running on localhost:8800):   python3 main.py
  Practice: 500 random days, compared with simpler strategies: python3 main.py practice
  Socket self-test against a fake local server:              python3 main.py selftest

THE STRATEGY (the key idea is that battery energy always costs exactly $1)
  The battery can only be charged by the generator, at $1/unit, so every unit stored costs $1.
  1. SOLAR first. It is free. Up to 200 units, not for lecture halls, and it can't be stored.
  2. BATTERY instead of grid when the grid costs more than $1. We save (price - $1) per unit,
     and the generator refills the battery in the same hour, so it is full again next hour.
  3. BATTERY = INSURANCE. When the grid is cheap we keep the battery full. If the grid fails,
     the stored energy is the only thing that can power the lecture halls.
  4. GRID covers the rest.
  5. END OF DAY. Stored energy left at hour 24 is wasted money. Near the end we stop
     buying more than we can use, and we spend the leftover where it is actually needed.
     The forecast tells us whether next hour's solar will cover the other buildings.
  6. GRID FAILURE. When there isn't enough energy for everyone, we power as many
     buildings FULLY as possible (we try every combination, which is at most 2^10 = 1024),
     and then share whatever is left.
  Every answer is checked against all the rules before it is sent. If a check fails,
  a simple answer that is always valid is sent instead, so the program never crashes.
"""

import codecs
import itertools
import json
import random
import socket
import sys
import threading

# ===================================================================
# SETTINGS - numbers from the problem statement
# ===================================================================
HOST, PORT = "localhost", 8800
SOLAR_LIMIT = 200        # solar units available per hour (0 when cloudy)
BATTERY_SIZE = 100       # battery capacity
GENERATOR_COST = 1.00    # $ per generator unit
HOURS_IN_DAY = 24
LAST_CHARGE_HOUR = 21    # last normal hour to recharge (energy is usable from the next hour)
NIGHT_START = 20         # from here on we expect night-time loads (the PDF: loads drop at night)
EARLY_MORNING = 6        # hours 0-5 show us what night-time loads look like
NO_SOLAR = "lecture_hall"
TINY = 1e-6

# ===================================================================
# MEMORY - the server never tells us the battery level, so we track it
# ===================================================================
state = {"battery": 0, "hour": 0, "total_cost": 0.0, "total_short": 0,
         "night_need": None}   # biggest battery need we saw in the early morning


def grid_price(message):
    """The PDF calls it "grid_cost". We also accept "grid_price" just in case."""
    return float(message.get("grid_cost", message.get("grid_price", 0)))


def read_hour(message):
    """Use the server's hour if it sends one, otherwise our own counter (wraps every 24 hours)."""
    hour = message.get("hour")
    return int(hour) % HOURS_IN_DAY if isinstance(hour, (int, float)) else state["hour"] % HOURS_IN_DAY


def battery_need(loads, types, solar_available):
    """How much of this hour's demand can't come from solar: lecture halls plus what's above 200."""
    lecture = sum(l for l, t in zip(loads, types) if t == NO_SOLAR)
    others = sum(l for l, t in zip(loads, types) if t != NO_SOLAR)
    return lecture + max(0, others - solar_available)


# ===================================================================
# STEP 1: HOW MUCH BATTERY TO USE AND HOW MUCH TO GENERATE
# ===================================================================
def estimate_future_use(message, loads, types, hour):
    """Guess how much battery energy the rest of the day could use.
    Next hour: like now, and the forecast tells us whether solar will help.
    Hours after that: like now, except that from NIGHT_START on we expect loads like the
    early morning, because the night at the end of the day looks like the night at the start."""
    if hour < EARLY_MORNING and message.get("random_event") != "cloudy_weather":
        need = battery_need(loads, types, SOLAR_LIMIT)
        state["night_need"] = max(need, state["night_need"] or 0)
    sunny_need = battery_need(loads, types, SOLAR_LIMIT)
    total = 0
    for future in range(hour + 1, HOURS_IN_DAY):
        if future == hour + 1 and message.get("forecast") == "cloudy":
            need = battery_need(loads, types, 0)
        else:
            need = sunny_need
        if future >= NIGHT_START and state["night_need"] is not None:
            need = min(need, state["night_need"])
        total += need
    return total


def plan_battery(message, loads, types, hour):
    event = message.get("random_event", "none")
    price = grid_price(message)
    grid_ok = event != "grid_failure"
    battery_ok = event != "battery_failure"
    generator_ok = event != "generator_failure"
    solar_now = 0 if event == "cloudy_weather" else SOLAR_LIMIT
    stored = state["battery"]

    if not battery_ok:
        return 0, 0                     # broken battery: can't take energy out or put it in

    need_now = battery_need(loads, types, solar_now)
    future_use = estimate_future_use(message, loads, types, hour)
    hours_after = HOURS_IN_DAY - 1 - hour       # hours still to come after this one

    refill_allowed = generator_ok and (hour <= LAST_CHARGE_HOUR or
                                       (not grid_ok and hours_after > 0))  # outage: keep insurance

    # ---- How much to take out of the battery this hour
    if not grid_ok:
        use = stored                                    # emergency: everything we have
    elif price > GENERATOR_COST and (refill_allowed or hour > LAST_CHARGE_HOUR):
        use = stored                                    # cheaper than grid (or end of day)
    else:
        use = max(0, stored - future_use)               # only the part the day can't use anyway
    if hours_after == 0:
        use = stored                                    # last hour: leftover energy is wasted
    use = min(use, need_now)                            # can't use more than we need

    # ---- How much the generator makes (usable from next hour)
    generate = 0
    if refill_allowed:
        target = min(BATTERY_SIZE, future_use)          # keep it full, but not more than the day can use
        generate = max(0, target - (stored - use))
    return use, generate


# ===================================================================
# STEP 2: SHARE THE ENERGY BETWEEN BUILDINGS
# ===================================================================
def fill(rows, needs, order, source, amount, allowed=lambda i: True):
    """Give `amount` units of `source` to the buildings in `order` until it runs out."""
    for i in order:
        if amount <= 0:
            break
        if allowed(i):
            give = min(needs[i], amount)
            rows[i][source] += give
            needs[i] -= give
            amount -= give
    return amount


def best_buildings_to_power(loads, types, solar, battery):
    """Grid failure: pick the biggest set of buildings we can power FULLY with solar + battery.
    At most 10 buildings, so 1024 combinations: we just try all of them."""
    n = len(loads)
    best, best_key = (), (-1, -1)
    for size in range(n, 0, -1):
        if size < best_key[0]:
            break
        for group in itertools.combinations(range(n), size):
            lecture = sum(loads[i] for i in group if types[i] == NO_SOLAR)
            others = sum(loads[i] for i in group if types[i] != NO_SOLAR)
            if lecture + max(0, others - solar) <= battery:
                key = (size, lecture + others)
                if key > best_key:
                    best, best_key = group, key
    return list(best)


def allocate(loads, types, solar, battery, grid_ok):
    n = len(loads)
    rows = [{"solar": 0, "battery": 0, "grid": 0} for _ in range(n)]
    needs = list(loads)
    can_solar = lambda i: types[i] != NO_SOLAR

    if grid_ok:
        # Solar to buildings that can take it, battery to lecture halls first, grid for the rest.
        fill(rows, needs, range(n), "solar", solar, can_solar)
        lecture_first = sorted(range(n), key=lambda i: types[i] != NO_SOLAR)
        fill(rows, needs, lecture_first, "battery", battery)
        for i in range(n):
            rows[i]["grid"], needs[i] = needs[i], 0
        return rows

    # Grid is down: fully power the best group first, then share what's left with the rest.
    chosen = best_buildings_to_power(loads, types, solar, battery)
    rest = [i for i in range(n) if i not in chosen]
    solar = fill(rows, needs, chosen, "solar", solar, can_solar)
    battery = fill(rows, needs, chosen, "battery", battery)
    solar = fill(rows, needs, rest, "solar", solar, can_solar)
    rest_lecture_first = sorted(rest, key=lambda i: types[i] != NO_SOLAR)
    fill(rows, needs, rest_lecture_first, "battery", battery)
    return rows


def decide(message):
    buildings = message.get("loads", [])
    loads = [int(round(float(b.get("load", 0)))) for b in buildings]
    types = [b.get("type", "") for b in buildings]
    event = message.get("random_event", "none")
    hour = read_hour(message)

    use, generate = plan_battery(message, loads, types, hour)
    solar = 0 if event == "cloudy_weather" else SOLAR_LIMIT
    rows = allocate(loads, types, solar, use, event != "grid_failure")
    return {"buildings": rows, "generator": generate}


# ===================================================================
# STEP 3: CHECK EVERY RULE BEFORE SENDING
# ===================================================================
def check_answer(message, answer, battery_before):
    """Returns a list of problems. Empty list = valid answer."""
    problems = []
    event = message.get("random_event", "none")
    buildings = message.get("loads", [])
    rows = answer["buildings"]
    if len(rows) != len(buildings):
        return ["wrong number of buildings"]

    for i, (b, r) in enumerate(zip(buildings, rows)):
        got = r["solar"] + r["battery"] + r["grid"]
        load = float(b.get("load", 0))
        if min(r.values()) < 0:
            problems.append(f"building {i}: negative energy")
        if b.get("type") == NO_SOLAR and r["solar"] > TINY:
            problems.append(f"building {i}: lecture hall got solar")
        if got > load + TINY:
            problems.append(f"building {i}: got more than its load")
        if got < load - TINY and event != "grid_failure":
            problems.append(f"building {i}: not enough energy")

    total = lambda src: sum(r[src] for r in rows)
    if total("solar") > (0 if event == "cloudy_weather" else SOLAR_LIMIT) + TINY:
        problems.append("too much solar")
    if total("battery") > (0 if event == "battery_failure" else battery_before) + TINY:
        problems.append("more battery than stored")
    if event == "grid_failure" and total("grid") > TINY:
        problems.append("used the grid while it was down")
    if answer["generator"] < 0:
        problems.append("negative generator")
    if answer["generator"] > TINY and event in ("generator_failure", "battery_failure"):
        problems.append("generator used while it (or the battery) was broken")
    if battery_before - total("battery") + answer["generator"] > BATTERY_SIZE + TINY:
        problems.append("battery would go past 100")
    return problems


def backup_answer(message):
    """Always valid: solar where allowed, grid for the rest, battery only if the grid is down."""
    event = message.get("random_event", "none")
    buildings = message.get("loads", [])
    loads = [int(round(float(b.get("load", 0)))) for b in buildings]
    types = [b.get("type", "") for b in buildings]
    battery = 0 if event == "battery_failure" else state["battery"]
    solar = 0 if event == "cloudy_weather" else SOLAR_LIMIT
    if event == "grid_failure":
        rows = allocate(loads, types, solar, battery, grid_ok=False)
    else:
        rows = allocate(loads, types, solar, 0, grid_ok=True)
    return {"buildings": rows, "generator": 0}


# ===================================================================
# STEP 4: ONE FULL HOUR = decide, check, update memory, log
# ===================================================================
def run_one_hour(message, quiet=False, strategy=None):
    battery_before = state["battery"]
    try:
        answer = (strategy or decide)(message)
        problems = check_answer(message, answer, battery_before)
    except Exception as error:              # never crash: fall back to the safe answer
        problems = [f"error: {error}"]
    if problems:
        answer = backup_answer(message)

    rows = answer["buildings"]
    solar, used, grid = (sum(r[s] for r in rows) for s in ("solar", "battery", "grid"))
    state["battery"] = battery_before - used + answer["generator"]
    cost = grid * grid_price(message) + answer["generator"] * GENERATOR_COST
    demand = sum(float(b.get("load", 0)) for b in message.get("loads", []))
    short = demand - solar - used - grid
    state["total_cost"] += cost
    state["total_short"] += short

    if not quiet:
        flag = "OK   " if not problems else f"FIXED {problems}"
        print(f"  hour {read_hour(message):>2} {flag} {message.get('random_event', 'none'):<18}"
              f"${grid_price(message):.2f}  solar {solar:4.0f}  battery {used:4.0f}  grid {grid:4.0f}"
              f"  gen {answer['generator']:4.0f}  short {short:4.0f}  stored {state['battery']:4.0f}"
              f"  cost ${cost:7.2f}", file=sys.stderr)
    state["hour"] += 1
    return {"buildings": [{k: int(v) for k, v in r.items()} for r in rows],
            "generator": int(answer["generator"])}


# ===================================================================
# STEP 5A: COMPETITION MODE - talk to the real server
# ===================================================================
def read_messages(sock):
    """Turn the byte stream into complete JSON messages, however the server splits them."""
    decoder, text = json.JSONDecoder(), ""
    utf8 = codecs.getincrementaldecoder("utf-8")()
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            return                                  # server closed: the day is over
        text += utf8.decode(chunk)
        while True:
            text = text.lstrip()
            if not text:
                break
            try:
                message, end = decoder.raw_decode(text)
            except json.JSONDecodeError:
                break                               # only half a message so far
            text = text[end:]
            yield message


def run_competition(host=HOST, port=PORT):
    print(f"Connecting to {host}:{port} ...", file=sys.stderr)
    with socket.create_connection((host, port)) as sock:
        for message in read_messages(sock):
            if not isinstance(message, dict) or "loads" not in message:
                print(f"  (server says: {message})", file=sys.stderr)
                continue
            reply = run_one_hour(message)
            sock.sendall((json.dumps(reply) + "\n").encode("utf-8"))
    print(f"Done. Our estimated cost: ${state['total_cost']:.2f}", file=sys.stderr)


# ===================================================================
# STEP 5B: PRACTICE MODE - random days in the PDF's format
# ===================================================================
TYPES = ["library", "laboratory", "lecture_hall", "student_centre", "student_residence"]


def make_day(seed, event_chance=0.15):
    """A random day: 7-10 buildings, loads 5-70 peaking in the day, prices $0.50-$2.00,
    random events that can last a few hours, and a forecast that is right 75% of the time."""
    rng = random.Random(seed)
    campus = TYPES + [rng.choice(TYPES) for _ in range(rng.randint(2, 5))]
    events, hour = [], 0
    while hour < HOURS_IN_DAY:
        if rng.random() < event_chance:
            kind = rng.choice(["cloudy_weather", "grid_failure", "battery_failure", "generator_failure"])
            events += [kind] * rng.randint(1, 3)
        else:
            events.append("none")
        hour = len(events)
    events = events[:HOURS_IN_DAY]
    day = []
    for h in range(HOURS_IN_DAY):
        busy = max(0.0, 1 - abs(h - 13) / 7)                    # peaks at 1 pm
        price = min(2.0, max(0.5, 0.6 + 1.1 * busy + rng.uniform(-0.25, 0.25)))
        next_cloudy = h + 1 < HOURS_IN_DAY and events[h + 1] == "cloudy_weather"
        forecast_right = rng.random() < 0.75
        day.append({
            "random_event": events[h],
            "forecast": "cloudy" if next_cloudy == forecast_right else "not cloudy",
            "loads": [{"type": t, "load": min(70, max(5, int(5 + 60 * busy + rng.randint(-8, 8))))}
                      for t in campus],
            "grid_cost": round(price, 2),
        })
    return day


def grid_only(message):
    """Comparison strategy: solar, then grid. The battery is never charged."""
    return backup_answer(message)


def simulate(day, strategy):
    """Run one day with a given strategy. Returns (cost, energy short)."""
    saved = dict(state)
    state.update(battery=0, hour=0, total_cost=0.0, total_short=0, night_need=None)
    for message in day:
        run_one_hour(message, quiet=True, strategy=strategy)
    result = state["total_cost"], state["total_short"]
    state.update(saved)
    return result


def run_practice(days=500):
    print("One example day (every hour is checked against every rule):\n", file=sys.stderr)
    for message in make_day(seed=1):
        run_one_hour(message)
    print(f"\nExample day cost: ${state['total_cost']:.2f}, energy short: {state['total_short']:.0f}\n",
          file=sys.stderr)

    ours = [simulate(make_day(s), decide) for s in range(days)]
    base = [simulate(make_day(s), grid_only) for s in range(days)]
    avg = lambda xs, k: sum(x[k] for x in xs) / len(xs)
    print(f"Average over {days} random days:", file=sys.stderr)
    print(f"  grid only (no battery):  cost ${avg(base, 0):8.2f}   energy short {avg(base, 1):6.1f}", file=sys.stderr)
    print(f"  our controller:          cost ${avg(ours, 0):8.2f}   energy short {avg(ours, 1):6.1f}", file=sys.stderr)


# ===================================================================
# STEP 5C: SELF-TEST - a fake server on this computer, to test the socket code
# ===================================================================
def run_selftest():
    day = make_day(seed=99)
    server = socket.socket()
    server.bind(("localhost", 0))
    server.listen(1)
    port = server.getsockname()[1]
    replies = []

    def fake_server():
        conn, _ = server.accept()
        with conn:
            for message in day:
                raw = json.dumps(message, indent=2).encode()
                for k in range(0, len(raw), 37):          # send in awkward pieces on purpose
                    conn.sendall(raw[k:k + 37])
                reply, buf = None, b""
                while reply is None:
                    buf += conn.recv(65536)
                    try:
                        reply = json.loads(buf)
                    except ValueError:
                        pass
                replies.append(reply)
            conn.sendall(b'{"final_score": 123}')
        server.close()

    thread = threading.Thread(target=fake_server)
    thread.start()
    run_competition("localhost", port)
    thread.join()
    ok = len(replies) == HOURS_IN_DAY and all(
        set(r) == {"buildings", "generator"} and len(r["buildings"]) == len(m["loads"])
        for r, m in zip(replies, day))
    print(f"\nSELF-TEST {'PASSED' if ok else 'FAILED'}: {len(replies)}/24 replies in the right format",
          file=sys.stderr)


# ===================================================================
# START HERE
# ===================================================================
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "practice":
        run_practice()
    elif mode == "selftest":
        run_selftest()
    else:
        run_competition()
