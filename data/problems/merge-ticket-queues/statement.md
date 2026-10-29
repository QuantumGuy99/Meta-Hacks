# Merge Ticket Queues

A theme park runs two entry lanes. Each lane hands out numbered tickets, and each lane's list of numbers is already sorted from smallest to largest. At closing, the park wants one combined list in order.

Write a function `merge_queues(a, b)` that returns all the ticket numbers from both lists in one sorted list. Keep repeated numbers.

## Example 1

Input: `a = [1, 4, 9], b = [2, 3, 10]`
Output: `[1, 2, 3, 4, 9, 10]`
Explanation: Both queues are merged in ticket order.

## Example 2

Input: `a = [], b = [5]`
Output: `[5]`
Explanation: One queue can be empty.

## Constraints

- 0 <= len(a), len(b) <= 10^5
- a and b are each sorted from smallest to largest
- -10^9 <= a[i], b[i] <= 10^9
