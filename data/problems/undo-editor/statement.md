# Undo Editor

A tiny note-taking app supports two commands. `"type X"` appends the text `X` to the end of the note. `"undo"` removes the text added by the most recent `type` command that hasn't already been undone. An `undo` with nothing left to undo does nothing.

Write a function `final_text(commands)` that returns the note after running all the commands in order, starting from an empty note.

## Example 1

Input: `commands = ["type a", "type bc", "undo", "type d"]`
Output: `"ad"`
Explanation: The undo removes "bc", the most recent typing.

## Example 2

Input: `commands = ["type x", "undo", "undo"]`
Output: `""`
Explanation: The second undo has nothing left to undo, so it does nothing.

## Constraints

- 0 <= len(commands) <= 10^5
- each command is "undo" or "type " followed by at least one character
- typed text may contain spaces
