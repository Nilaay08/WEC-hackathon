from backup_plan import backup_answer
from decision import decide
from memory import reset_memory, state
from practice_day import make_practice_day
from rule_checker import check_answer

BUILDINGS = [
    {"type": "library", "load": 20},
    {"type": "lecture_hall", "load": 30},
    {"type": "student_residence", "load": 50},
]

def hour(event="none", price=1.2, forecast="not cloudy", loads=BUILDINGS):
    return {"random_event": event, "grid_price": price, "forecast": forecast, "loads": loads}

def setup(battery=0, at_hour=5):
    reset_memory()
    state["battery"] = battery
    state["hour"] = at_hour

def test_solar_goes_first_but_never_to_the_lecture_hall():
    setup()
    answer = decide(hour(price=0.7))
    assert [b["solar"] for b in answer["buildings"]] == [20, 0, 50]

def test_expensive_grid_uses_the_battery_lecture_hall_first():
    setup(battery=100)
    answer = decide(hour(price=1.2))
    assert answer["buildings"][1]["battery"] == 30
    assert sum(b["grid"] for b in answer["buildings"]) == 0

def test_cheap_grid_saves_the_battery():
    setup(battery=100)
    answer = decide(hour(price=0.7))
    assert sum(b["battery"] for b in answer["buildings"]) == 0

def test_grid_failure_uses_the_battery_and_no_grid():
    setup(battery=40)
    message = hour(event="grid_failure", price=0.7)
    answer = decide(message)
    assert sum(b["grid"] for b in answer["buildings"]) == 0
    assert answer["buildings"][1]["battery"] == 30
    assert check_answer(message, answer, 40) == []

def test_generator_never_overfills_and_respects_failures():
    setup(battery=95)
    assert decide(hour(price=0.7))["generator"] <= 5
    setup(battery=0)
    assert decide(hour(event="generator_failure", price=0.7))["generator"] == 0
    setup(battery=0)
    assert decide(hour(event="battery_failure", price=0.7))["generator"] == 0

def test_no_refill_in_the_last_three_hours():
    setup(battery=0, at_hour=21)
    assert decide(hour(price=0.7))["generator"] == 0

def test_rule_checker_catches_bad_answers():
    message = hour()
    bad = {"buildings": [{"solar": 0, "battery": 0, "grid": 20},
                         {"solar": 30, "battery": 0, "grid": 0},      
                         {"solar": 50, "battery": 0, "grid": 0}], "generator": 0}
    assert check_answer(message, bad, 0) != []

def test_backup_answer_is_always_valid():
    for event in ["none", "cloudy_weather", "grid_failure", "battery_failure", "generator_failure"]:
        message = hour(event=event)
        assert check_answer(message, backup_answer(message), 0) == []

def test_whole_practice_day_is_valid_every_hour():
    reset_memory()
    for message in make_practice_day():
        before = state["battery"]
        answer = decide(message)
        assert check_answer(message, answer, before) == [], message
        state["battery"] = before - sum(b["battery"] for b in answer["buildings"]) + answer["generator"]
        state["hour"] += 1

if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS  {test.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
