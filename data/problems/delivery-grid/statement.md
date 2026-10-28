# Delivery Grid

A delivery robot starts in the top-left square of a warehouse floor plan and must reach the bottom-right square. Each square is either open (`.`) or blocked by shelving (`#`). The robot moves one square at a time: up, down, left or right.

Write a function `shortest_route(grid)` that returns the fewest moves needed to reach the bottom-right square, or `-1` if it can't be reached.

## Example 1

Input: `grid = ["..#", ".#.", "..."]`
Output: `4`
Explanation: Down, down, right, right reaches the bottom-right corner in 4 steps.

## Example 2

Input: `grid = [".#", "#."]`
Output: `-1`
Explanation: The robot is walled in at the start.

## Constraints

- 1 <= len(grid) <= 200
- 1 <= len(grid[i]) <= 200
- every row has the same length
- grid[i][j] is '.' (open) or '#' (blocked)
