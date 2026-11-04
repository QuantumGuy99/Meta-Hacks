# Mirror Badge Codes

Conference badges carry a code made of letters, digits and dashes. Badges whose code reads the same forwards and backwards get a small prize. Dashes are just separators and don't count, and upper and lower case letters count as the same.

Write a function `is_mirror_code(code)` that returns `True` if the code reads the same in both directions under those rules, and `False` otherwise.

## Example 1

Input: `code = "Ab-1-bA"`
Output: `True`
Explanation: Without dashes and ignoring case it reads "ab1ba" both ways.

## Example 2

Input: `code = "AB-12"`
Output: `False`
Explanation: "ab12" backwards is "21ba".

## Constraints

- 0 <= len(code) <= 10^5
- code contains only letters, digits and dashes
