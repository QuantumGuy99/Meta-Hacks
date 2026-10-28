# Genre Sampler

A radio host wants to open the show with a short "sampler": a stretch of **consecutive** songs from tonight's playlist that includes at least one song from every genre on a required list. Shorter is better, since listeners get bored.

Write a function `shortest_sampler(songs, required)` that returns the length of the shortest stretch of consecutive songs that includes every genre in `required` at least once.

- If no stretch works, return `-1`.
- If `required` is empty, return `0`.
- A genre listed more than once in `required` still only needs to appear once.

## Example 1

Input: `songs = ["pop", "rock", "jazz", "pop", "rap", "jazz", "rock"], required = ["rock", "rap"]`
Output: `3`
Explanation: The last three songs (rap, jazz, rock) include both required genres. No shorter stretch does.

## Example 2

Input: `songs = ["pop", "pop"], required = ["rap"]`
Output: `-1`
Explanation: No song is rap, so no stretch works.

## Constraints

- 0 <= len(songs) <= 10^5
- 0 <= len(required) <= 50
- every genre is 1 to 20 lowercase letters
