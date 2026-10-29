# Next Taller Building

A city planner is studying a street of buildings from west to east. For each building, they want to know how far east you'd have to walk to reach the first building that is **strictly taller** than it.

Write a function `next_taller_distance(heights)` that returns a list where each entry is the number of buildings between a building and the next strictly taller one to its east (1 means the very next building). If no taller building comes later, the entry is `0`.

## Example 1

Input: `heights = [3, 1, 4, 2, 5]`
Output: `[2, 1, 2, 1, 0]`
Explanation: The building of height 3 first sees a taller one (4) two buildings later. Nothing is taller than 5.

## Example 2

Input: `heights = [2, 2, 3]`
Output: `[2, 1, 0]`
Explanation: A building of the same height doesn't count as taller.

## Constraints

- 0 <= len(heights) <= 10^5
- 1 <= heights[i] <= 10^9
