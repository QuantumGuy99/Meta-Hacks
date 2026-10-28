# Ingredient Groups

A bakery labels each recipe with a code made of lowercase letters, where every letter stands for one scoop of an ingredient. The order of the letters doesn't matter, only how many scoops of each ingredient go in.

Two codes describe the **same mix** if they use exactly the same letters the same number of times. For example, `"abc"` and `"bca"` are the same mix, but `"ab"` and `"abb"` are not.

Write a function `count_ingredient_groups(codes)` that returns how many different mixes appear in the list.

## Example 1

Input: `codes = ["abc", "bca", "aab", "aba", "xyz"]`
Output: `3`
Explanation: `"abc"` and `"bca"` are one mix, `"aab"` and `"aba"` are another, and `"xyz"` is on its own.

## Example 2

Input: `codes = ["ab", "ba", "abb"]`
Output: `2`
Explanation: `"abb"` uses `b` twice, so it is a different mix from `"ab"` and `"ba"`.

## Constraints

- 0 <= len(codes) <= 10^4
- 0 <= len(codes[i]) <= 20
- codes[i] contains only lowercase letters a-z
