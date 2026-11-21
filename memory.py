state = {
    "battery": 0.0,      
    "hour": 0,           
    "total_cost": 0.0,   
}

def reset_memory():

    state["battery"] = 0.0
    state["hour"] = 0
    state["total_cost"] = 0.0
