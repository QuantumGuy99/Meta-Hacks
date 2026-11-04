# Rising Scores

A player's game scores are listed in the order they were played. A **rise** is a selection of scores, kept in their original order, where each score is strictly higher than the one before. You can skip scores, but you can't reorder them.

Write a function `longest_rise(scores)` that returns the length of the longest rise.

## Example 1

Input: `scores = [5, 2, 8, 6, 3, 6, 9, 7]`
Output: `4`
Explanation: One longest rise is 2, 3, 6, 9.

## Example 2

Input: `scores = [4, 4, 4]`
Output: `1`
Explanation: Equal scores don't count as rising.

## Constraints

- 0 <= len(scores) <= 10^5
- -10^9 <= scores[i] <= 10^9
