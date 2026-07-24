# Experiment Evidence Contract

This contract applies to experiment issues #71, #73, #74, #75, and #77.

`status: ready` only means the experiment code and declared inputs are complete. It does not mean the experiment has enough evidence to support a research claim.

Research support is recorded separately under `evidence.status`:

- `ready`: all evidence artifacts required by that experiment are present.
- `insufficient_evidence`: at least one required artifact is missing, and `evidence.missing` must list the missing items explicitly.

The shared evidence item keys are:

- `human_labels`: independent human labels or adjudicated ground truth.
- `real_llm_calls`: real frozen-model LLM call logs, not mock backend output.
- `factor_catalog_100`: a fixed 100-factor catalog or 100-candidate directory.
- `real_jydb_data`: real JYDB raw tables and PIT panel, not synthetic fallback data.

Research conclusions are calculated separately in `research_conclusion`. A ready contract with `research_conclusion.status: not_computed` is acceptable and should not be described as a successful empirical finding.
