# Seesaw Split

Weights sit in a row along a plank. You want to put a pivot under one of the weights so that the total weight to its left equals the total weight to its right. The weight sitting on the pivot doesn't count toward either side. Weights can be negative, like a balloon pulling up.

Write a function `balance_point(weights)` that returns the leftmost position where the plank balances, or `-1` if there isn't one. With an empty left or right side, that side's total is 0.

## Example 1

Input: `weights = [2, 7, 1, 3, 6]`
Output: `2`
Explanation: Put the pivot under position 2: 2 + 7 = 9 on the left and 3 + 6 = 9 on the right.

## Example 2

Input: `weights = [1, 2, 3]`
Output: `-1`
Explanation: No position balances the two sides.

## Constraints

- 0 <= len(weights) <= 10^5
- -10^4 <= weights[i] <= 10^4
