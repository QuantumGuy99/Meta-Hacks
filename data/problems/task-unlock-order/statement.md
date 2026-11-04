# Task Unlock Order

A build system has `n` tasks numbered `0` to `n - 1`. Each dependency `[before, after]` means task `before` must finish before task `after` can start. When several tasks are ready at the same time, the build system always starts the smallest-numbered one.

Write a function `build_order(n, deps)` that returns the order the tasks run in. If the dependencies make it impossible to finish every task, return an empty list.

## Example 1

Input: `n = 4, deps = [[0, 1], [0, 2], [1, 3], [2, 3]]`
Output: `[0, 1, 2, 3]`
Explanation: 0 unlocks 1 and 2; both unlock 3. Among valid orders this one is smallest.

## Example 2

Input: `n = 2, deps = [[0, 1], [1, 0]]`
Output: `[]`
Explanation: Each task waits on the other, so no order works.

## Constraints

- 1 <= n <= 10^4
- 0 <= len(deps) <= 5 * 10^4
- deps[i] = [before, after] with before != after
