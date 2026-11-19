---
name: count-local-items
description: Use when asked to count distinct nonempty items in a supplied local text list.
---
# Count local items (v2 synthetic fixture)

Use when the request is to count distinct items in a supplied local text list,
including an indirect request for how many different entries it contains.
Unrelated questions do not trigger this workflow. If the input path is absent,
ask for it before running. Read only the user-supplied list; do not search
accounts or create schedules.

Run `python3 <skill-directory>/scripts/count.py <input-path>` using the available
local command tool. The [script](scripts/count.py) counts unique stripped
nonempty lines. [Sample input](assets/items.txt) has count 2. A failed command
or missing tool means report the observed failure and needed input; do not
fabricate a count or label the task complete.

Output the script JSON containing count, input_sha256 and fixture_version=v2.
Verify it by independently reading the supplied list and checking the unique
count and input hash. Follow design → implement → independent review → feedback
→ testing → repeat until acceptance. The existing script is the implementation;
obtain independent review of the result and resolve findings. If an independent
reviewer is unavailable, provide the verified result with review pending and
retain the next step; do not claim completed acceptance.
