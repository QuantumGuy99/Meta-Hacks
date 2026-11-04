# Gift Card Pairs

A store sells gift cards of different values. A customer wants to pay for an item costing exactly `price` using two different gift cards from a pile.

Write a function `count_pairs(values, price)` that returns how many different pairs of cards (two different positions in the list) add up to exactly `price`. Cards with equal values still count as different cards.

## Example 1

Input: `values = [1, 5, 3, 3, 7], price = 6`
Output: `2`
Explanation: Cards 1 + 5 and the two cards worth 3 each make 6.

## Example 2

Input: `values = [2, 2, 2], price = 4`
Output: `3`
Explanation: Any two of the three cards work: 3 different pairs.

## Constraints

- 0 <= len(values) <= 10^5
- -10^6 <= values[i], price <= 10^6
