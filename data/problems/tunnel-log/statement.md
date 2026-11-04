# Tunnel Log

A sensor at a one-lane tunnel logs every event as a character: `E` when someone enters and `X` when someone exits. A log is valid if nobody ever exits while the tunnel is empty, and the tunnel is empty again when the log ends.

Write a function `tunnel_ok(log)` that returns `True` if the log is valid and `False` otherwise.

## Example 1

Input: `log = "EEXEXX"`
Output: `True`
Explanation: The count inside goes 1, 2, 1, 2, 1, 0, never below zero, and ends at zero.

## Example 2

Input: `log = "EXXE"`
Output: `False`
Explanation: After the third event, more people have left than entered.

## Constraints

- 0 <= len(log) <= 10^5
- log contains only the characters E and X
