# Mixed passages

Compare a score over a complete document with the highest score found by a fixed window search when one controlled passage is inserted into human writing. Measure false positives once per document after searching every registered window. The experiment uses a fresh public key and its own domain, thresholds and evidence files.

## Material

Reuse the 192 public-domain passages in `fixtures/corpus.json`, with its existing split of eight calibration authors and eight evaluation authors. This corpus was already examined for Declawd v1 and v2. It supplies known human material, rather than a fresh blind sample. Group each author's twelve passages in their recorded order into three disjoint groups of four. Join each group with paragraph breaks and keep its first 768 ASCII word tokens. The resulting corpus contains 48 backgrounds, with 24 in each split. Record the four source identifiers, author and exact text for each background. Retain the original source attribution and public-domain notice.

Test prefixes of 128, 384 and 768 tokens from every background. These lengths overlap within a background. Documents share authors, so report counts by author as well as pooled counts. Do not attach population confidence intervals to these small, dependent samples.

Use the reviewed `fixtures/template-v2.json` as a controlled language template. Freeze its exact bytes, then generate one passage with the new key by taking the first green candidate in each slot, or the first candidate if none is green. The neutral control takes every first candidate. Keep prefixes of 64, 128 and 256 tokens, even if a prefix ends within a sentence. Each prefix is inserted as a separate paragraph at the start, middle and end of each human background. The middle is token index `floor(background_tokens / 2)`. The measured document therefore contains both human writing and a controlled passage. The template and its neutral output are authored experimental material, rather than additional human controls.

## Scoring

Use ASCII word runs matching `[A-Za-z]+(?:'[A-Za-z]+)?`, folded to lower case. For adjacent tokens `previous` and `current`, hash `domain || key || length(previous) || previous || length(current) || current` with SHA-256. Lengths are unsigned four-byte big-endian UTF-8 lengths. The domain is `declawd/mixed-passage-v1/green`. The pair is green when the first eight digest bytes, interpreted as an unsigned big-endian integer, are divisible by four. Count each distinct adjacent pair once within the scored span. Exclude the transition from outside a window into its first token.

With `N` distinct pairs and `G` green pairs, the score is `(4G - N) / sqrt(3N)`. Require at least 32 distinct pairs. This is a separate experimental floor. It changes no v1/v2 contract and makes no claim about production detector reliability. The score is a descriptive statistic here, without a normal-distribution p-value claim.

Search windows of 64, 128 and 256 tokens at a stride of 16 tokens. Include the final possible start for each width, even if it is off the stride. Skip widths longer than the document. Recompute pair uniqueness within each window. Choose the highest eligible score, breaking exact ties by the earliest start and then the shortest width. Record every window's start, end, distinct-pair count and green count. A document receives one window-search verdict from that maximum.

## Thresholds

Calibrate on the 24 human backgrounds in the calibration split alone. Score each of the three background lengths. Choose separate thresholds for the whole document and the maximum over all windows. For each method, take the smallest threshold on the inclusive grid `0.00, 0.05, ..., 19.95` that keeps the observed false-positive fraction at or below 2 per cent separately at all three lengths. With 24 documents per group, this requires zero calibration crossings. Stop and retain an error if any calibration document has no eligible score, or if no threshold meets the rule.

Use strict greater-than comparisons, calculated with integers before any display rounding. Commit the calibration report and its thresholds before evaluating the human evaluation split or either inserted-passage condition. The generated marked passage plays no part in threshold selection. Also report the diagnostic count from applying the whole-document threshold to a window maximum. This uncorrected search shows the consequence of reusing a threshold after adding a search.

## Sequence

Commit the plan, configuration, derived corpus, implementation, tests and a registration containing their SHA-256 hashes before drawing a key. Record one 32-byte key from `secrets.token_bytes`, the registration hash and its Git commit in `seed.json`. Create that file exclusively and refuse a second draw. Commit and push the seed before scoring. Recording this sequence documents the draw, without proving that no earlier private draw occurred.

Run calibration once and commit its output before evaluation. Then evaluate all human documents, all 648 marked insertions and all 648 neutral insertions in the evaluation split. Retain every result, including misses, false positives and unavailable scores. A run directory is created exclusively. Reproduction recomputes the frozen outputs and compares them without choosing another key or threshold. Any change to a registered input requires another experiment identifier and registration.

## Outcomes

Report one false-positive count per human evaluation document at each background length. For insertions, report detection counts by background length, inserted length and position, with paired whole-document and window results. Retain each case's exact text hash, raw score counts, winning window and full search trace. For the winning window, record intersection over union with the known insertion span and the fraction of inserted tokens covered. Count a localised detection when the adjusted window threshold is crossed and intersection over union is at least 0.5.

The primary comparison is the two separately calibrated methods. The uncorrected window result is a diagnostic, and the neutral insertion is an additional control for the controlled template. No threshold, key, window, length, position or wording is selected using evaluation results. Summaries count the registered cases, without treating overlapping lengths, repeated inserted text or shared authors as independent observations.

## Boundaries

This experiment measures the new Declawd word-pair scheme on a fixed corpus and one controlled template. It supplies no detector or result for Claude, ChatGPT, Gemini, TextSeal or any vendor's production watermark. A detected pattern supplies no authorship finding. A missed pattern supplies no evidence that writing was human.

The localisation question is informed by [WaterSeeker, version 6](https://arxiv.org/abs/2409.05112v6). Its implementation is independently written here, with no code copied from the repository whose licence was absent in the scout capture. [TextSeal's pinned README](https://github.com/facebookresearch/textseal/blob/79c3f8001c0022ebeb8dd73f1fc86f4bc3ddc354/README.md) provides a separate research reference for localised detection. This run uses neither package nor a language model.
