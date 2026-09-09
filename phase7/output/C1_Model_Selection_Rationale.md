# C1 — Model Selection Rationale

## Selected Model

**Model:** `claude-haiku-4-5-20251001`

## Reason for Selection

Claude Haiku 4.5 is used as the primary model for this
lab because the task is structured evidence-to-explanation
generation rather than unrestricted reasoning.

The model receives a curated evidence object and produces:

- Severity
- Evidence
- Interpretation
- Next Checks

The integration therefore prioritizes:

1. Low latency
2. Lower API cost
3. Sufficient reasoning for structured operational explanation
4. Reliable instruction following

A larger Claude model could provide deeper reasoning, but
would generally increase cost and latency. For this C1 task,
the evidence is already structured by the ML pipeline, so a
smaller model is appropriate for the first implementation.

## Cost Consideration

The API response records input and output token counts in:

`c1_network_insights.json`

Actual cost should be calculated using the current Anthropic
pricing applicable to the selected model at the time of
submission.

## Latency Consideration

Each API call records:

`latency_seconds`

This allows the learner to compare response speed across
model choices.

## Reasoning Depth

The task does not require long-form autonomous reasoning.
Claude's role is to transform structured ML evidence into an
operations-friendly explanation while maintaining the
observation/inference boundary.

## Evidence Grounding

The prompt explicitly requires:

- No invented numbers
- No unsupported measurements
- No congestion claims
- Clear separation between evidence and interpretation
- Explicit insufficiency when important evidence is missing

## Validation

The implementation tests:

- Five different grids
- Four required response sections
- Unsupported numbers
- Unsupported congestion assertions
- Missing anomaly score / insufficient evidence behavior
