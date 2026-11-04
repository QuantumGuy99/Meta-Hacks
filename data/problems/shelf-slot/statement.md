# Shelf Slot

A library shelf holds books sorted by id, smallest first, with no repeated ids. When a new book arrives, the librarian needs to know where it goes.

Write a function `shelf_slot(ids, new_id)` that returns the position of `new_id` if it's already on the shelf, or otherwise the position where it should be inserted to keep the shelf sorted.

## Example 1

Input: `ids = [101, 205, 310, 422], new_id = 310`
Output: `2`
Explanation: 310 is already on the shelf at position 2.

## Example 2

Input: `ids = [101, 205, 310, 422], new_id = 250`
Output: `2`
Explanation: 250 goes between 205 and 310, at position 2.

## Constraints

- 0 <= len(ids) <= 10^6
- ids is sorted from smallest to largest with no repeats
- 1 <= ids[i], new_id <= 10^9
