# Rooms Needed

An office schedules meetings as `[start, end]` times. Two meetings can share a room only if they don't overlap. A meeting that ends at time `t` frees its room for a meeting that starts at `t`.

Write a function `min_rooms(meetings)` that returns the smallest number of rooms needed to hold every meeting.

## Example 1

Input: `meetings = [[9, 10], [9, 12], [11, 13]]`
Output: `2`
Explanation: 9-10 and 9-12 overlap, so two rooms. 11-13 can reuse the room freed at 10.

## Example 2

Input: `meetings = [[1, 2], [2, 3]]`
Output: `1`
Explanation: A meeting ending at 2 frees its room for one starting at 2.

## Constraints

- 0 <= len(meetings) <= 10^4
- 0 <= start < end <= 10^6
