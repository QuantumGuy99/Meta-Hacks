# Library Returns

A library's return slot logs each book's id as it comes back, in order. Staff want to catch books that come back more than once in the same day, since that usually means a scanning error.

Write a function `first_repeat(ids)` that returns the id of the **first book to come back a second time**: the one whose second return happens earliest in the log. If no book comes back twice, return `-1`.

## Example 1

Input: `ids = [4, 7, 2, 7, 4]`
Output: `7`
Explanation: 7 shows up a second time at position 3, before 4 shows up again at position 4.

## Example 2

Input: `ids = [1, 2, 3]`
Output: `-1`
Explanation: No book was returned twice.

## Constraints

- 0 <= len(ids) <= 10^5
- 1 <= ids[i] <= 10^9
