from pathlib import Path
import pandas as pd
from np2_usageprocessor import UsageProcessor
# ============================================================
# NP3 CONFIGURATION
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = (
    BASE_DIR
    / "output"
    / "network_alerts.csv"
)
GRID_COLUMN = "grid_id"
TIMESTAMP_COLUMN = "timestamp"
ACTIVITY_COLUMN = "total_activity"
# ============================================================
# RULE THRESHOLDS
# ============================================================
# Current activity >= 1.50 × baseline
HIGH_ACTIVITY_MULTIPLIER = 1.50
# Current activity >= 1.50 × previous hour
SPIKE_MULTIPLIER = 1.50
# Current activity <= 0.70 × baseline
DROP_MULTIPLIER = 0.70
# ============================================================
# ACTIVITY FLOOR
# ============================================================
# Use the 10th percentile of daily grid activity
# as the data-driven activity floor.
FLOOR_PERCENTILE = 0.10
# ============================================================
# WITHIN-DAY LEAVE-ONE-OUT BASELINE
# ============================================================
def calculate_baseline(group):
    """
    Calculate the leave-one-out median baseline
    for one grid on one day.
    The current hour is excluded from its own
    baseline calculation.
    """
    values = group[ACTIVITY_COLUMN].to_numpy()
    baselines = []
    for i in range(len(values)):
        # Exclude the current hour
        other_values = [
            values[j]
            for j in range(len(values))
            if j != i
        ]
        if other_values:
            baseline = float(
                pd.Series(other_values).median()
            )
        else:
            baseline = float("nan")
        baselines.append(baseline)
    result = group.copy()
    result["baseline_activity"] = baselines
    return result
def add_baselines(df):
    """
    Add the within-day leave-one-out median baseline.
    Baseline is calculated separately for every
    grid_id and calendar day.
    """
    df = df.copy()
    # Create calendar date
    df["date"] = (
        df[TIMESTAMP_COLUMN].dt.date
    )
    # Sort for deterministic processing
    df = (
        df.sort_values(
            [GRID_COLUMN, TIMESTAMP_COLUMN]
        )
        .reset_index(drop=True)
    )
    # Calculate leave-one-out baseline
    df = (
        df.groupby(
            [GRID_COLUMN, "date"],
            group_keys=False
        )
        .apply(calculate_baseline)
        .reset_index(drop=True)
    )
    return df
# ============================================================
# ACTIVITY FLOOR
# ============================================================
def calculate_activity_floor(df):
    """
    Calculate a data-driven activity floor.
    The floor is the 10th percentile of daily
    total activity across grid/day combinations.
    """
    daily_totals = (
        df.groupby(
            [GRID_COLUMN, "date"]
        )[ACTIVITY_COLUMN]
        .sum()
        .reset_index(
            name="daily_total_activity"
        )
    )
    floor = (
        daily_totals[
            "daily_total_activity"
        ]
        .quantile(FLOOR_PERCENTILE)
    )
    return float(floor), daily_totals
def apply_activity_floor(
    df,
    daily_totals,
    floor
):
    """
    Mark grid/day combinations that meet
    the activity floor.
    """
    df = df.merge(
        daily_totals,
        on=[
            GRID_COLUMN,
            "date"
        ],
        how="left"
    )
    df["above_activity_floor"] = (
        df["daily_total_activity"] >= floor
    )
    return df

# ============================================================
# PREVIOUS-HOUR ACTIVITY
# ============================================================

def add_previous_hour(df):
    """
    Add the immediately preceding hourly
    activity for each grid.
    """
    df = (
        df.sort_values(
            [
                GRID_COLUMN,
                TIMESTAMP_COLUMN
            ]
        )
        .copy()
    )
    df["previous_activity"] = (
        df.groupby(
            GRID_COLUMN
        )[ACTIVITY_COLUMN]
        .shift(1)
    )
    return df

# ============================================================
# ALERT RULES
# ============================================================
def generate_alerts(df):
    """
    Apply the three deterministic rules.
    Rules:
        HIGH_ACTIVITY
        ACTIVITY_SPIKE
        ACTIVITY_DROP
    """
    alerts = []
    for _, row in df.iterrows():
        # Ignore low-activity grids
        if not row["above_activity_floor"]:
            continue
        current = row[ACTIVITY_COLUMN]
        baseline = row["baseline_activity"]
        previous = row["previous_activity"]
        # Cannot evaluate without a baseline
        if pd.isna(baseline):
            continue
        grid_id = row[GRID_COLUMN]
        timestamp = row[TIMESTAMP_COLUMN]
        # ----------------------------------------------------
        # HIGH_ACTIVITY
        # ----------------------------------------------------
        if (
            current
            >= baseline * HIGH_ACTIVITY_MULTIPLIER
        ):
            alerts.append({
                "grid_id": grid_id,
                "timestamp": timestamp,
                "alert_type": "HIGH_ACTIVITY",
                "current_activity": current,
                "baseline_activity": baseline,
                "reason": (
                    f"Current activity {current:.2f} "
                    f"is at least "
                    f"{HIGH_ACTIVITY_MULTIPLIER:.2f}x "
                    f"the within-day baseline "
                    f"{baseline:.2f}."
                )
            })
        # ----------------------------------------------------
        # ACTIVITY_SPIKE
        # ----------------------------------------------------
        if (
            pd.notna(previous)
            and previous > 0
            and current
            >= previous * SPIKE_MULTIPLIER
        ):
            alerts.append({
                "grid_id": grid_id,
                "timestamp": timestamp,
                "alert_type": "ACTIVITY_SPIKE",
                "current_activity": current,
                "baseline_activity": baseline,
                "reason": (
                    f"Activity increased from "
                    f"{previous:.2f} to "
                    f"{current:.2f}, at least "
                    f"{SPIKE_MULTIPLIER:.2f}x "
                    f"the previous hour."
                )
            })
        # ----------------------------------------------------
        # ACTIVITY_DROP
        # ----------------------------------------------------
        if (
            current
            <= baseline * DROP_MULTIPLIER
        ):
            alerts.append({
                "grid_id": grid_id,
                "timestamp": timestamp,
                "alert_type": "ACTIVITY_DROP",
                "current_activity": current,
                "baseline_activity": baseline,
                "reason": (
                    f"Current activity {current:.2f} "
                    f"is at or below "
                    f"{DROP_MULTIPLIER:.2f}x "
                    f"the within-day baseline "
                    f"{baseline:.2f}."
                )
            })
    return pd.DataFrame(alerts)

# ============================================================
# OPERATIONAL SUMMARY
# ============================================================

def print_summary(
    df,
    alerts,
    floor
):
    """
    Print the operational summary.
    """
    total_grid_hours = len(df)
    total_alerts = len(alerts)
    print("\n" + "=" * 60)
    print(
        "RULE-BASED NETWORK ACTIVITY ALERT SUMMARY"
    )
    print("=" * 60)
    print(
        f"Input grid/hour rows       : "
        f"{total_grid_hours}"
    )
    print(
        f"Activity floor             : "
        f"{floor:.2f}"
    )
    print(
        f"Alert records generated    : "
        f"{total_alerts}"
    )
    # --------------------------------------------------------
    # Unique alerting grid-hours
    # --------------------------------------------------------
    if alerts.empty:
        unique_alerting_grid_hours = 0
    else:
        unique_alerting_grid_hours = (
            alerts[
                [
                    "grid_id",
                    "timestamp"
                ]
            ]
            .drop_duplicates()
            .shape[0]
        )
    # --------------------------------------------------------
    # Correct alerting proportion
    # --------------------------------------------------------
    if total_grid_hours > 0:
        alert_proportion = (
            unique_alerting_grid_hours
            / total_grid_hours
        )
    else:
        alert_proportion = 0.0
    print(
        f"Unique alerting grid-hours : "
        f"{unique_alerting_grid_hours}"
    )
    print(
        f"Alerting grid-hour rate     : "
        f"{alert_proportion:.2%}"
    )
    # --------------------------------------------------------
    # Alerts by type
    # --------------------------------------------------------
    print("\nAlerts by type:")
    if alerts.empty:
        print("  No alerts generated.")
    else:
        type_counts = (
            alerts["alert_type"]
            .value_counts()
        )
        for alert_type, count in (
            type_counts.items()
        ):
            print(
                f"  {alert_type:<20} "
                f"{count}"
            )
    # --------------------------------------------------------
    # Top 10 grids
    # --------------------------------------------------------
    print(
        "\nTop 10 grids by alert count:"
    )
    if alerts.empty:
        print("  No alerting grids.")
    else:
        top_grids = (
            alerts
            .groupby("grid_id")
            .size()
            .sort_values(
                ascending=False
            )
            .head(10)
        )
        for grid_id, count in (
            top_grids.items()
        ):
            print(
                f"  Grid {grid_id:<10} "
                f"{count}"
            )
    print("=" * 60)

# ============================================================
# MAIN
# ============================================================

def main():
    print(
        "Starting alert using UsageProcessor..."
    )
    # --------------------------------------------------------
    # Create the NP2 processor
    # --------------------------------------------------------
    input_file = (
        BASE_DIR.parent
        / "dataset"
        / "sms-call-internet-mi-2013-11-01.csv"
    )
    processor = UsageProcessor(
        input_file
    )
    # --------------------------------------------------------
    # Run only the NP2 processing required by NP3
    # NP3 receives grid/hour analytics directly
    # from UsageProcessor instead of reading the
    # intermediate CSV.
    # --------------------------------------------------------
    print(
        "Running data preparation..."
    )
    processor.load_data()
    processor.clean_data()
    processor.derive_time_features()
    processor.aggregate_to_grid_time()
    processor.derive_activity_features()
    # --------------------------------------------------------
    # Get grid/hour DataFrame directly from NP2
    # --------------------------------------------------------
    df = (
        processor.grid_time_df.copy()
    )
    print(
        f"Received {len(df)} grid/hour rows "
        "from UsageProcessor."
    )
    # --------------------------------------------------------
    # Validate required NP3 columns
    # --------------------------------------------------------
    required_columns = {
        GRID_COLUMN,
        TIMESTAMP_COLUMN,
        ACTIVITY_COLUMN
    }
    missing = (
        required_columns
        - set(df.columns)
    )
    if missing:
        raise ValueError(
            "UsageProcessor did not provide "
            f"required alert columns: "
            f"{sorted(missing)}"
        )
    # --------------------------------------------------------
    # Add date
    # --------------------------------------------------------
    df["date"] = (
        df[TIMESTAMP_COLUMN].dt.date
    )
    # --------------------------------------------------------
    # Within-day baseline
    # --------------------------------------------------------
    print(
        "Calculating within-day baselines..."
    )
    df = add_baselines(df)
    # --------------------------------------------------------
    # Activity floor
    # --------------------------------------------------------
    floor, daily_totals = (
        calculate_activity_floor(df)
    )
    print(
        f"Calculated activity floor: "
        f"{floor:.2f}"
    )
    df = apply_activity_floor(
        df,
        daily_totals,
        floor
    )
    # --------------------------------------------------------
    # Previous hour
    # --------------------------------------------------------
    df = add_previous_hour(df)
    # --------------------------------------------------------
    # Generate alerts
    # --------------------------------------------------------
    print(
        "Applying alert rules..."
    )
    alerts = generate_alerts(df)
    # --------------------------------------------------------
    # Save alerts
    # --------------------------------------------------------
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )
    alerts.to_csv(
        OUTPUT_FILE,
        index=False
    )
    # --------------------------------------------------------
    # Print operational summary
    # --------------------------------------------------------
    print_summary(
        df,
        alerts,
        floor
    )
    print(
        f"\nAlert file written to: "
        f"{OUTPUT_FILE}"
    )
# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    main()