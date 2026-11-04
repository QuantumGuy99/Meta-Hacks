def tunnel_ok(log: str) -> bool:
    inside = 0
    for event in log:
        if event == "E":
            inside += 1
        else:
            inside -= 1
            if inside < 0:
                return False
    return inside == 0
