from backup_plan import backup_answer
from decision import decide
from memory import state
from rule_checker import check_answer
from settings import GENERATOR_COST

def run_one_hour(message):
    battery_before = state["battery"]
    try:
        answer = decide(message)
        problems = check_answer(message, answer, battery_before)
    except Exception as error:                     
        problems = [f"error: {error}"]
    if problems:
        print(f"  hour {state['hour']}: PROBLEM {problems} -> using backup answer")
        answer = backup_answer(message)

    
    used = sum(r["battery"] for r in answer["buildings"])
    state["battery"] = battery_before - used + answer["generator"]

    
    grid = sum(r["grid"] for r in answer["buildings"])
    cost = grid * float(message.get("grid_price", 0)) + answer["generator"] * GENERATOR_COST
    state["total_cost"] += cost

    demand = sum(float(b.get("load", 0)) for b in message.get("loads", []))
    solar = sum(r["solar"] for r in answer["buildings"])
    short = demand - solar - used - grid
    status = "OK   " if not problems else "FIXED"
    print(f"  hour {state['hour']:>2} {status} {message.get('random_event', 'none'):<18}"
          f"price ${float(message.get('grid_price', 0)):.2f}  solar {solar:5.0f}  battery {used:5.0f}  "
          f"grid {grid:5.0f}  generator {answer['generator']:5.0f}  short {short:4.0f}  "
          f"battery now {state['battery']:5.1f}  cost ${cost:7.2f}")

    state["hour"] += 1
    
    return {"buildings": [{k: round(v, 6) for k, v in r.items()} for r in answer["buildings"]],
            "generator": round(answer["generator"], 6)}
