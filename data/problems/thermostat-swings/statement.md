# Thermostat Swings

A smart thermostat logs the room temperature at regular intervals. The building manager wants to know how often the temperature jumps around, because big jumps usually mean a window was left open or the heating misbehaved.

A **swing** happens when two readings next to each other differ by **more than** `k` degrees. It doesn't matter whether the temperature went up or down.

Write a function `count_big_swings(temps, k)` that returns the number of swings in the log.

## Example 1

Input: `temps = [70, 75, 74, 80, 79], k = 3`
Output: `2`
Explanation: The changes between neighboring readings are 5, 1, 6 and 1. Only 5 and 6 are bigger than 3.

## Example 2

Input: `temps = [50, 40, 50], k = 5`
Output: `2`
Explanation: A drop of 10 and a rise of 10 both count as swings.

## Constraints

- 0 <= len(temps) <= 10^5
- -100 <= temps[i] <= 150
- 0 <= k <= 250
