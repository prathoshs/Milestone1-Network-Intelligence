# C3 Context Engineering Checklist

    ## Long-Context Incident Investigation

    ### Evidence Selection
    - [x] Use trusted network/API evidence rather than raw CSV data.
    - [x] Collect current grid activity metrics.
    - [x] Collect grid-level features.
    - [x] Collect location information.
    - [x] Collect recent historical evidence.
    - [x] Collect prior alerts.
    - [x] Collect current ML risk output.
    - [x] Collect current anomaly output.
    - [x] Collect pipeline quality/status information.

    ### Context Curation
    - [x] Summarize historical timeline before sending it to Claude.
    - [x] Summarize alert history instead of sending all alert rows.
    - [x] Avoid dumping raw historical rows into the curated context.
    - [x] Keep current metrics separate from historical evidence.
    - [x] Keep model outputs separate from observed activity measures.
    - [x] Keep pipeline status visible as material evidence.
    - [x] Preserve failed or unavailable evidence instead of inventing values.

    ### Evidence Interpretation
    - [x] Separate CURRENT EVIDENCE from HISTORICAL EVIDENCE.
    - [x] Explicitly identify UNCERTAINTY.
    - [x] Distinguish observations from model outputs.
    - [x] Do not treat model risk as proof of congestion.
    - [x] Do not treat anomaly score as proof of congestion.
    - [x] Do not convert activity measures into counts or MB.
    - [x] Do not claim capacity problems or service failure without evidence.
    - [x] Explicitly account for stale analytics.
    - [x] Explicitly account for rejected rows and data-quality limitations.

    ### Context Efficiency
    - [x] Compare dump-everything context with curated context.
    - [x] Record the failure of the oversized context as a negative control.
    - [x] Use summarized evidence to stay within the model context window.
    - [x] Remove irrelevant raw rows from the active context.

    ### Reliability / Sensitivity
    - [x] Run the investigation with the original pipeline status.
    - [x] Run the investigation with pipeline health forced to unhealthy.
    - [x] Compare the UNCERTAINTY sections.
    - [x] Verify that degraded pipeline health changes the confidence assessment.

    ### Safety and Traceability
    - [x] Do not invent missing evidence.
    - [x] Report unavailable evidence explicitly.
    - [x] Preserve model version information.
    - [x] Preserve timestamps for current evidence.
    - [x] Treat AS_OF as the effective reporting timestamp.
    - [x] Treat grid_id as a geographic grid cell.
    