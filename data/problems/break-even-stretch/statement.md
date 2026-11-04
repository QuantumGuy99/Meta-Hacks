# Break-Even Stretch

A small shop records how its cash balance changed each day, as positive or negative numbers. The owner wants the longest run of **consecutive** days where the changes add up to exactly zero, meaning the shop broke even over that stretch.

Write a function `longest_zero_net(changes)` that returns the length of the longest such stretch, or `0` if there isn't one.

## Example 1

Input: `changes = [3, -1, -2, 4, -4, 1]`
Output: `5`
Explanation: The first five days add up to 3 - 1 - 2 + 4 - 4 = 0.

## Example 2

Input: `changes = [1, 2, 3]`
Output: `0`
Explanation: No stretch of days breaks even.

## Constraints

- 0 <= len(changes) <= 10^5
- -10^4 <= changes[i] <= 10^4
