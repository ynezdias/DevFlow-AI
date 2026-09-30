# AI reviewer evaluation

## Baseline: 2026-09-30

The frozen benchmark contains 35 synthetic Python changes: 20 buggy examples
(two each for division by zero, None validation, boundaries, resource leaks,
shell execution, SQL injection, credentials, path traversal, exception handling,
and authorization), 10 clean alternatives, and five changes with pre-existing
bugs outside the added lines. Each case includes before/after source, a unified
diff, and expected locations and categories. These are assistant-authored labels,
not independently adjudicated production examples. Review the contracts in
labels.json before interpreting the scores.

Labels are withheld from the model. The runner records a SHA-256 fingerprint of
the dataset and preserves per-case findings, timing, failures, and counts in
[results.json](../evaluation/results.json).

## Methodology

A runs the application's Ruff/Bandit analyzer (Ruff 0.16.8, Bandit 1.9.4 on Python
3.12.14 for this run). B runs Gemini using the real diff and full source context.
C combines A and B, deduplicating by path, line, and normalized category.
Matching is strict and one-to-one: path, new-file line, and category must match.
An extra duplicate counts as a false positive. Precision = TP/(TP+FP), recall =
TP/(TP+FN), and F1 = 2TP/(2TP+FP+FN). Undefined metrics are null. Failed calls are
excluded, with completed-case counts shown explicitly; failures are never
interpreted as clean reviews.

The additional full-file baseline supplies all source lines as additions instead
of the real diff. This compares full-file versus diff-grounded review; it changes
the model input as well as eligible lines and is not a pure post-filter ablation.

Live calls use the configured model, at most 2,048 output tokens and zero retries
in this benchmark. The first provider failure stops further live requests while
static evaluation continues. Unit tests mock provider responses and block live
GitHub/Gemini HTTP requests.

## Actual results

| Experiment | Completed cases | TP | FP | FN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A: Ruff + Bandit | 35/35 | 6 | 16 | 14 | 27.27% | 30.00% | 28.57% |
| B: Gemini | 0/35 | — | — | — | — | — | — |
| C: combined | 0/35 | — | — | — | — | — | — |
| Full-file AI baseline | 0/35 | — | — | — | — | — | — |

The configured Gemini model was `gemini-3.8-flash`. The first request returned
`ai_http_503` after 1.578 seconds. That is a failed-request duration, not successful
LLM latency. No token usage was returned. Average successful latency, input/output
tokens, and cost per review are unmeasured, not zero. No prompt revision or
post-result label tuning was performed. Day 13's live comparisons remain blocked
until a configured provider/model successfully responds.

## Interpretation and limitations

The static baseline is weak on these correctness-heavy snippets. It also exposes
limitations of this scoring protocol: the fixed Ruff mapping labels SIM115 as
correctness while expected resource-leak labels use resource; strict line matching
counts an exception-handler finding on the except line as different from an
expected finding on its pass line. Import-order and conservative subprocess
warnings contribute false positives against the narrowly labeled issue set.
These numbers measure agreement with this exact protocol, not universal analyzer
accuracy. Raw results are retained rather than relabeled to improve the score.
A future independently reviewed taxonomy/location policy should be versioned
and compared with this baseline.

No conclusion about AI usefulness or grounding effectiveness is supported yet.
After provider recovery, rerun the same frozen dataset to a new result file,
record provider usage and dated pricing, then compare successful A/B/C runs.

See [evaluation instructions](../evaluation/README.md) for reproducible commands.
