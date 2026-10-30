# canned
<!-- Used by engine/interviewer.py `fallback_text` when there's no usable analyzer draft and no rubric hint
(PLAN §9.5, §9.6). One entry per line, a dash then `key: text`. Keys are InterventionTrigger values, plus
`concept` for the last ladder level. ENG-6 phrases messages with the model and keeps these as its fallback.
Never put code, a fix or anything from a hidden test in a line. -->

- asked: Good question. What do you think? Tell me what you'd assume, and we'll go from there.
- hint_requested: You're close. Which part are you least sure about right now?
- time_warning: Time check: about {minutes} minutes left.
- paste: I noticed a pasted block. I'll focus my feedback on the parts you wrote.
- coded_before_plan: Before you go further, what's your approach?
- run_failed: One of the visible tests is still failing. What does your code do with that input?
- bug_suspected: Take another look around line {line}. What happens there?
- plan_mismatch: Your code seems to be going a different way from the plan you described. Has the plan changed?
- silent: Talk me through what you're doing.
- idle: Where are you at?
- reply: Okay, go on.
- probe: Walk me through why this part of your code works.
- concept: Let's step back from the code. In plain words, what idea does this part of the problem need?
