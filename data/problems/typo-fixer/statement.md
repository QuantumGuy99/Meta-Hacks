# Typo Fixer

A spell checker suggests fixes by measuring how different two words are. One edit is inserting a letter, deleting a letter, or replacing one letter with another.

Write a function `min_edits(a, b)` that returns the fewest edits needed to turn word `a` into word `b`.

## Example 1

Input: `a = "flaw", b = "lawn"`
Output: `2`
Explanation: Delete the "f" and add an "n" at the end.

## Example 2

Input: `a = "plant", b = "planet"`
Output: `1`
Explanation: Insert an "e".

## Constraints

- 0 <= len(a), len(b) <= 1000
- a and b contain lowercase letters
