# Printer Speed

An office printer must finish a stack of documents within `h` hours. Each hour, it prints up to `speed` pages of **one** document. If a document has fewer pages left than that, the printer finishes it and sits idle for the rest of the hour.

Write a function `min_print_speed(pages, h)` that returns the slowest whole-number speed, in pages per hour, that finishes every document within `h` hours.

## Example 1

Input: `pages = [3, 6, 7, 11], h = 8`
Output: `4`
Explanation: At 4 pages per hour the documents take 1 + 2 + 2 + 3 = 8 hours. At 3 they'd take 10.

## Example 2

Input: `pages = [30, 11, 23, 4, 20], h = 5`
Output: `30`
Explanation: With one hour per document, the speed must cover the largest one.

## Constraints

- 1 <= len(pages) <= 10^4
- len(pages) <= h <= 10^9
- 1 <= pages[i] <= 10^9
