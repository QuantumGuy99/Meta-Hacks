# Battery Budget

A camping battery logs how many units of charge were used in each hour of a trip. The owner wants to know the longest run of **consecutive** hours that a battery with `budget` units could have powered on its own.

Write a function `longest_within_budget(usage, budget)` that returns the length of the longest stretch of consecutive hours whose total usage is **at most** `budget`. If no stretch fits, return `0`.

## Example 1

Input: `usage = [2, 1, 5, 1, 1, 1], budget = 4`
Output: `3`
Explanation: The last three hours use 3 units in total. No longer stretch stays within 4.

## Example 2

Input: `usage = [4, 1, 1, 4], budget = 3`
Output: `2`
Explanation: The two middle hours use 2 units. Any stretch including a 4 is over budget.

## Constraints

- 0 <= len(usage) <= 10^5
- 0 <= usage[i] <= 10^4
- 0 <= budget <= 10^9
