# Loudest Moment

A sound meter at a concert records one loudness reading per second. The venue wants a highlight track: for every window of `k` consecutive seconds, the loudest reading in that window.

Write a function `window_peaks(readings, k)` that returns the loudest reading of each window, in order. If there are fewer than `k` readings, return an empty list.

## Example 1

Input: `readings = [1, 3, 2, 5, 4, 1], k = 3`
Output: `[3, 5, 5, 5]`
Explanation: The four windows of three readings peak at 3, 5, 5 and 5.

## Example 2

Input: `readings = [4, 2], k = 3`
Output: `[]`
Explanation: There aren't enough readings for a single window.

## Constraints

- 0 <= len(readings) <= 10^5
- 1 <= k <= 10^5
- 0 <= readings[i] <= 10^9
