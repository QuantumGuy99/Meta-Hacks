# Room Bookings

A coworking space logs room bookings as `[start, end]` hours. The front desk wants a simpler view: the blocks of time when the room is busy. Bookings that overlap, or that touch (one ends exactly when the next starts), form one busy block.

Write a function `merge_bookings(bookings)` that returns the busy blocks as a list of `[start, end]` pairs sorted by start time.

## Example 1

Input: `bookings = [[9, 11], [10, 12], [14, 15], [15, 16]]`
Output: `[[9, 12], [14, 16]]`
Explanation: 9-11 overlaps 10-12, and 14-15 touches 15-16.

## Example 2

Input: `bookings = [[13, 14], [8, 10]]`
Output: `[[8, 10], [13, 14]]`
Explanation: Bookings can arrive in any order; the result is sorted.

## Constraints

- 0 <= len(bookings) <= 10^4
- 0 <= start < end <= 10^6
