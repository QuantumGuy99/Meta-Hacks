# Trending Tags

A social app logs every hashtag used in the last hour. The trending panel shows the `k` most-used tags. Tags with the same count are shown in alphabetical order, and tags are case-sensitive, so `#Run` and `#run` are different.

Write a function `top_tags(tags, k)` that returns the trending tags in order. If there are fewer than `k` different tags, return all of them.

## Example 1

Input: `tags = ["#run", "#eat", "#run", "#code", "#eat", "#run"], k = 2`
Output: `["#run", "#eat"]`
Explanation: #run appears 3 times and #eat twice.

## Example 2

Input: `tags = ["#b", "#a", "#c"], k = 2`
Output: `["#a", "#b"]`
Explanation: All tie at 1, so the alphabetically first ones win.

## Constraints

- 0 <= len(tags) <= 10^5
- 1 <= k <= 10^4
- if k is more than the number of different tags, return them all
