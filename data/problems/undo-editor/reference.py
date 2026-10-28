def final_text(commands: list[str]) -> str:
    pieces = []
    for command in commands:
        if command == "undo":
            if pieces:
                pieces.pop()
        else:
            pieces.append(command[len("type "):])
    return "".join(pieces)
