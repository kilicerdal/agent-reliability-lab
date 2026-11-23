# Blind cause-label evaluation

Both prompts and the grader are fixed before the run. The new fixture file has 25 cases, five per output label. Run each case twice per arm for 100 investigations. Both arms receive the same permitted tool evidence. The model receives no fixture IDs, expected labels, or grading criteria. The project author created and labeled these synthetic cases. The model is blinded to the answer key. Independent human review is outside this experiment.

The primary metric is the existing strict pass. Compare the same case and repetition across prompts, report discordant pairs, and report results for all five expected labels. Also report SQL-to-dependency mislabels, correct `unknown` abstentions, and grounded recoveries among runs exposed to a tool failure. Group repeated runs by incident when discussing the strength of the evidence.

The candidate clears this local promotion gate only if it adds at least three strict passes out of 50, improves SQL diagnoses, and matches or exceeds every other cause category. A successful gate would support a separate decision about changing the default.

Frozen fixture SHA-256: `d7b528dcd66f9d75d50f708a2035ba7fa5bd2d486ecffe04a040288fb00a5cb3`.
