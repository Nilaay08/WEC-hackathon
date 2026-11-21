import random

from hourly_routine import run_one_hour
from memory import state
from settings import HOURS_IN_DAY

def make_practice_day():
    random.seed(7)
    events = (["none"] * 6 + ["cloudy_weather"] * 2 + ["none"] * 2 + ["grid_failure"] * 3
              + ["none"] * 2 + ["generator_failure"] + ["battery_failure"] + ["none"] * 7)
    day = []
    for hour in range(HOURS_IN_DAY):
        busy = 8 <= hour < 20
        price = 0.65 if hour < 7 else 0.95 if hour < 17 else 1.45 if hour < 22 else 0.80
        day.append({
            "random_event": events[hour],
            "forecast": "cloudy" if hour + 1 < HOURS_IN_DAY and events[hour + 1] == "cloudy_weather" else "not cloudy",
            "grid_price": round(price + random.uniform(-0.1, 0.1), 2),
            "loads": [
                {"type": "library", "load": random.randint(40, 60) if busy else 15},
                {"type": "laboratory", "load": random.randint(60, 80) if busy else 30},
                {"type": "lecture_hall", "load": random.randint(50, 70) if busy else 5},
                {"type": "student_centre", "load": random.randint(40, 60) if busy else 10},
                {"type": "student_residence", "load": 30 if busy else 80},
            ],
        })
    return day

def run_practice():
    print("Practice day (no server). Every hour is checked against all the rules.\n")
    for message in make_practice_day():
        run_one_hour(message)
    print(f"\nDay finished. Total cost: ${state['total_cost']:.2f}")
