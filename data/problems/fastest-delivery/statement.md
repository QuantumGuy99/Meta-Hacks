# Fastest Delivery

A courier network has `n` stops numbered `0` to `n - 1`. Each road is one-way and written as `[from, to, minutes]`. There can be several roads between the same two stops.

Write a function `fastest_delivery(n, roads)` that returns the fewest total minutes needed to get from stop `0` to stop `n - 1`, or `-1` if it can't be done.

## Example 1

Input: `n = 4, roads = [[0, 1, 4], [0, 2, 1], [2, 1, 2], [1, 3, 1]]`
Output: `4`
Explanation: 0 → 2 → 1 → 3 takes 1 + 2 + 1 = 4 minutes, faster than 0 → 1 → 3 at 5.

## Example 2

Input: `n = 3, roads = [[0, 1, 5]]`
Output: `-1`
Explanation: No road leads to stop 2.

## Constraints

- 1 <= n <= 10^4
- 0 <= len(roads) <= 5 * 10^4
- roads[i] = [from, to, minutes], 0 <= from, to < n
- 0 <= minutes <= 10^4
- roads are one-way
