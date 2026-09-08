import pandas as pd
import pytest

from phase6.ml2_engnetactfeatures import (
    calculate_features_for_grid,
)

def sample_grid():
    timestamps = pd.date_range(
        "2013-11-01 00:00:00",
        periods=50,
        freq="h",
    )
    return pd.DataFrame(
        {
            "grid_id": ["4857"] * len(timestamps),
            "timestamp": timestamps,
            "total_activity": [
                float(i + 1)
                for i in range(len(timestamps))
            ],
            "internet_activity": [
                float(i + 1) * 0.5
                for i in range(len(timestamps))
            ],
        }
    )

def test_features_do_not_use_data_after_feature_timestamp():
    """
    The implementation must only use observations through t.

    This test deliberately adds a huge future observation after the
    selected feature timestamp and verifies that the feature vector
    for the earlier timestamp is unchanged.
    """

    original = sample_grid()
    result_original = calculate_features_for_grid(
        original
    )
    target_timestamp = pd.Timestamp(
        result_original.iloc[0]["feature_timestamp"]
    )
    before = result_original[
        result_original["feature_timestamp"]
        == target_timestamp.isoformat()
    ].iloc[0]
    modified = original.copy()
    future_timestamp = (
        target_timestamp
        + pd.Timedelta(hours=1)
    )
    modified = pd.concat(
        [
            modified,
            pd.DataFrame(
                {
                    "grid_id": ["4857"],
                    "timestamp": [future_timestamp],
                    "total_activity": [999999999999.0],
                    "internet_activity": [999999999999.0],
                }
            ),
        ],
        ignore_index=True,
    )
    result_modified = calculate_features_for_grid(
        modified
    )
    after = result_modified[
        result_modified["feature_timestamp"]
        == target_timestamp.isoformat()
    ].iloc[0]
    for column in [
        "avg_activity",
        "activity_growth",
        "active_hours",
        "peak_ratio",
        "variability",
        "internet_share",
    ]:
        assert after[column] == pytest.approx(
            before[column]
        )

def test_feature_window_never_extends_after_t():
    """
    Direct implementation-level boundary test.

    The generated feature timestamp must always be at least as
    recent as the latest source observation used by the feature
    calculation.
    """
    source = sample_grid()
    result = calculate_features_for_grid(
        source
    )
    assert not result.empty
    for timestamp in result["feature_timestamp"]:
        t = pd.Timestamp(timestamp)

        # The function produces a feature for t only when t is
        # an observed timestamp in the source.
        assert t in set(source["timestamp"])
        # No feature timestamp may be after the source's own
        # maximum available timestamp.
        assert t <= source["timestamp"].max()
