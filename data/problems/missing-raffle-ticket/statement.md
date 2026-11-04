# Missing Raffle Ticket

A raffle printed tickets numbered `1` to `n`. After the draw, exactly one ticket is missing from the box. The remaining tickets are in no particular order.

Write a function `missing_ticket(tickets, n)` that returns the number of the missing ticket.

## Example 1

Input: `tickets = [3, 1, 5, 2], n = 5`
Output: `4`
Explanation: Tickets 1 to 5 were printed and 4 is the one not in the box.

## Example 2

Input: `tickets = [], n = 1`
Output: `1`
Explanation: Only ticket 1 was printed, and it's missing.

## Constraints

- 1 <= n <= 10^6
- len(tickets) == n - 1
- tickets are distinct numbers from 1 to n
