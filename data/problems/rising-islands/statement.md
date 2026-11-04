# Rising Islands

A map starts as all sea, with `rows` by `cols` cells. Each entry in `adds` raises one cell into land, in order. Land cells that touch up, down, left or right belong to the same island. Corner-touching cells don't connect. Raising a cell that's already land changes nothing.

Write a function `islands_after_each(rows, cols, adds)` that returns, after each addition, how many islands are on the map.

## Example 1

Input: `rows = 3, cols = 3, adds = [[0, 0], [0, 1], [1, 2], [2, 1], [1, 1]]`
Output: `[1, 1, 2, 3, 1]`
Explanation: The last cell connects all three islands into one.

## Example 2

Input: `rows = 1, cols = 3, adds = [[0, 0], [0, 0]]`
Output: `[1, 1]`
Explanation: Raising the same cell again changes nothing.

## Constraints

- 1 <= rows, cols <= 10^4
- 0 <= len(adds) <= 10^5
- adds[i] = [row, col] inside the grid
