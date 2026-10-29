# Runner-Up Score

A coding contest posts everyone's final score. The organizers want the **runner-up score**: the highest score that is strictly lower than the winning score. Players who tie for first don't create a runner-up.

Write a function `runner_up(scores)` that returns the runner-up score, or `-1` if there isn't one.

## Example 1

Input: `scores = [88, 92, 92, 75]`
Output: `88`
Explanation: The highest score is 92. The next highest different score is 88.

## Example 2

Input: `scores = [50, 50]`
Output: `-1`
Explanation: Everyone tied, so there is no runner-up score.

## Constraints

- 0 <= len(scores) <= 10^5
- 0 <= scores[i] <= 100
