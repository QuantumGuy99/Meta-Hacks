def final_text(commands: list[str]) -> str:
    # Keep every full version of the text and step back on undo.
    versions = [""]
    for command in commands:
        if command == "undo":
            if len(versions) > 1:
                versions.pop()
        else:
            versions.append(versions[-1] + command.split(" ", 1)[1])
    return versions[-1]
