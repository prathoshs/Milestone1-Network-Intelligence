from pathlib import Path
import logging
import pandas as pd
# LOGGING CONFIGURATION
# LOG_DIR = Path("logs")
# LOG_DIR.mkdir(parents=True, exist_ok=True)
# LOG_FILE = LOG_DIR / "usage_processor.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    # handlers=[
    #     logging.FileHandler(LOG_FILE, mode="a"),
    #     logging.StreamHandler()
    # ]
)
logger = logging.getLogger(__name__)

# USAGE PROCESSOR

class UsageProcessor:
    # Raw → Canonical mapping
    COLUMN_MAPPING = {
        "datetime": "timestamp",
        "CellID": "grid_id",
        "countrycode": "country_code",
        "smsin": "sms_in",
        "smsout": "sms_out",
        "callin": "call_in",
        "callout": "call_out",
        "internet": "internet_activity"
    }
    # Required canonical columns
    REQUIRED_COLUMNS = [
        "timestamp",
        "grid_id",
        "country_code",
        "sms_in",
        "sms_out",
        "call_in",
        "call_out",
        "internet_activity"
    ]
    # Activity columns

    ACTIVITY_COLUMNS = [
        "sms_in",
        "sms_out",
        "call_in",
        "call_out",
        "internet_activity"
    ]

    # Constructor
    def __init__(self, file_path=None, dataframe=None):
        if file_path is None and dataframe is None:
            raise ValueError(
                "Provide either file_path or dataframe."
            )
        if file_path is not None and dataframe is not None:
            raise ValueError(
                "Provide only one of file_path or dataframe."
            )
        self.file_path = Path(file_path) if file_path else None
        self.df = (
            dataframe.copy()
            if dataframe is not None
            else None
        )
        self.grid_time_df = None
        self.daily_summary = None
        self.grid_summary = None
        
        self.input_rows = 0
        self.rejected_rows = 0
        self.nulls_handled = 0
        self.output_rows = 0
        
    # 1. LOAD DATA
    def load_data(self):
        if self.df is not None:
            logger.info(
                "Using provided DataFrame | rows=%d",
                len(self.df)
            )
            return self.df
        if not self.file_path.exists():
            raise FileNotFoundError(
                f"Input file not found: {self.file_path}"
            )
        self.df = pd.read_csv(self.file_path)
        logger.info(
            "Data loaded | file=%s | rows=%d | columns=%d",
            self.file_path,
            len(self.df),
            len(self.df.columns)
        )
        return self.df
    
    # 2. CLEAN DATA
    def clean_data(self):
        if self.df is None:
            self.load_data()
        # Convert raw column names to canonical names
        self.df = self.df.rename(
            columns=self.COLUMN_MAPPING
        )
        # Validate required columns
        missing_columns = [
            column
            for column in self.REQUIRED_COLUMNS
            if column not in self.df.columns
        ]
        if missing_columns:
            raise ValueError(
                "Missing required columns: "
                + ", ".join(missing_columns)
            )
        input_rows = len(self.df)
        # Convert timestamp
        self.df["timestamp"] = pd.to_datetime(
            self.df["timestamp"],
            errors="coerce"
        )
        # Missing timestamp / grid ID
        invalid_rows = (
            self.df["timestamp"].isna()
            | self.df["grid_id"].isna()
        )
        dropped_rows = int(invalid_rows.sum())
        if dropped_rows:
            self.df = self.df.loc[
                ~invalid_rows
            ].copy()
        # Activity null handling
        # Curated layer:
        # activity null → 0

        null_count = int(
            self.df[self.ACTIVITY_COLUMNS]
            .isna()
            .sum()
            .sum()
        )
        if null_count > 0:
            self.df.loc[
                :,
                self.ACTIVITY_COLUMNS
            ] = self.df[
                self.ACTIVITY_COLUMNS
            ].fillna(0)
            logger.info(
                "Activity nulls handled | count=%d | policy=null_to_zero",
                null_count
            )
        # Negative activity validation
        negative_rows = int(
            (
                self.df[self.ACTIVITY_COLUMNS] < 0
            )
            .any(axis=1)
            .sum()
        )
        if negative_rows > 0:
            raise ValueError(
                f"Negative activity values detected "
                f"in {negative_rows} rows."
            )
        # Exact duplicate check
        duplicate_rows = int(
            self.df.duplicated().sum()
        )
        if duplicate_rows > 0:
            logger.warning(
                "Exact duplicate rows detected | count=%d",
                duplicate_rows
            )
        # Log cleaning result
        logger.info(
            "Cleaning completed | input_rows=%d | "
            "dropped_rows=%d | output_rows=%d",
            input_rows,
            dropped_rows,
            len(self.df)
        )
        if self.df["timestamp"].isna().any():
            raise ValueError(
                "Cleaned data still contains invalid timestamps."
            )

        if self.df["grid_id"].isna().any():
            raise ValueError(
                "Cleaned data still contains missing grid_id."
            )
        return self.df
    
    # 3. DERIVE TIME FEATURES
    def derive_time_features(self):
        if self.df is None:
            self.clean_data()
        self.df["date"] = (
            self.df["timestamp"].dt.date
        )
        self.df["hour"] = (
            self.df["timestamp"].dt.hour
        )
        self.df["day_of_week"] = (
            self.df["timestamp"].dt.dayofweek
        )
        if self.df["date"].isna().any():
            raise ValueError(
                "Date derivation produced missing values."
            )

        if not self.df["hour"].between(0, 23).all():
            raise ValueError(
                "Invalid hour values detected."
            )
        logger.info(
            "Time features created | "
            "date, hour, day_of_week"
        )
        return self.df
   
    # 4. AGGREGATE TO GRID/HOUR
    def aggregate_to_grid_time(self):
        if self.df is None:
            self.derive_time_features()
            
        self.df["hour_timestamp"] = (
            self.df["timestamp"].dt.floor("h")
        )

        # Raw grain:
        # timestamp + grid_id + country_code
        # Analytics grain:
        # timestamp + grid_id
        self.grid_time_df = (self.df.groupby(["hour_timestamp", "grid_id"],
                as_index=False,
                sort=True
            )[self.ACTIVITY_COLUMNS]
            .sum()
        )
        self.grid_time_df = (
            self.grid_time_df.rename(
                columns={
                    "hour_timestamp": "timestamp"
                }
            )
        )
        # ----------------------------------------------------
        # Add date/hour to canonical hourly table
        # ----------------------------------------------------
        self.grid_time_df["date"] = (
            self.grid_time_df["timestamp"].dt.date
        )
        self.grid_time_df["hour"] = (
            self.grid_time_df["timestamp"].dt.hour
        )

        # Validate one record per grid/hour
        duplicate_grid_hours = int(
            self.grid_time_df.duplicated(
                subset=["timestamp", "grid_id"]
            ).sum()
        )
        if duplicate_grid_hours > 0:
            raise ValueError(
                "Grid/hour aggregation failed. "
                f"Found {duplicate_grid_hours} duplicates."
            )
            
        if len(self.grid_time_df) > len(self.df):

            raise ValueError(
                "Grid/hour aggregation produced more "
                "rows than the cleaned input."
            )
            
        if "country_code" in self.grid_time_df.columns:

            raise ValueError(
                "country_code must not appear in "
                "grid/hour analytics output."
            )
        self.output_rows = len(
            self.grid_time_df
        )
        logger.info(
            "Grid/hour aggregation completed | rows=%d",
            len(self.grid_time_df)
        )
        return self.grid_time_df
    
    # 5. DERIVE ACTIVITY FEATURES
    def derive_activity_features(self):
        if self.grid_time_df is None:
            self.aggregate_to_grid_time()
        self.grid_time_df["total_sms"] = (
            self.grid_time_df["sms_in"]
            + self.grid_time_df["sms_out"]
        )
        self.grid_time_df["total_calls"] = (
            self.grid_time_df["call_in"]
            + self.grid_time_df["call_out"]
        )
        self.grid_time_df["total_activity"] = (
            self.grid_time_df["total_sms"]
            + self.grid_time_df["total_calls"]
            + self.grid_time_df["internet_activity"]
        )
        logger.info(
            "Activity features created | "
            "total_sms, total_calls, total_activity"
        )
        return self.grid_time_df
    
    # 6. COMPUTE KPIs
    def compute_kpis(self):
        if self.grid_time_df is None:
            self.derive_activity_features()
        # Create reusable date column
        self.grid_time_df["date"] = (
            self.grid_time_df["timestamp"].dt.date
        )
        # DAILY SUMMARY
        self.daily_summary = (
            self.grid_time_df
            .groupby("date", as_index=False)
            .agg(
                total_sms_activity=(
                    "total_sms",
                    "sum"
                ),
                total_call_activity=(
                    "total_calls",
                    "sum"
                ),
                total_internet_activity=(
                    "internet_activity",
                    "sum"
                ),
                total_activity=(
                    "total_activity",
                    "sum"
                ),
                unique_grids=(
                    "grid_id",
                    "nunique"
                )
            )
        )
        # ----------------------------------------------------
        # GRID SUMMARY
        # ----------------------------------------------------
        self.grid_summary = (
            self.grid_time_df
            .groupby(
                "grid_id",
                as_index=False
            )
            .agg(
                total_sms_activity=(
                    "total_sms",
                    "sum"
                ),
                total_call_activity=(
                    "total_calls",
                    "sum"
                ),
                total_internet_activity=(
                    "internet_activity",
                    "sum"
                ),
                total_activity=(
                    "total_activity",
                    "sum"
                )
            )
            .sort_values(
                "total_activity",
                ascending=False
            )
            .reset_index(drop=True)
        )
        logger.info(
            "KPI computation completed | "
            "daily_rows=%d | grid_rows=%d",
            len(self.daily_summary),
            len(self.grid_summary)
        )
        return (
            self.daily_summary,
            self.grid_summary
        )
    # ========================================================
    # 7. EXPORT SUMMARY
    # ========================================================
    def export_summary(
        self,
        output_dir="output"
    ):
        if (
            self.daily_summary is None
            or self.grid_summary is None
        ):
            self.compute_kpis()
        output_path = Path(output_dir)
        output_path.mkdir(
            parents=True,
            exist_ok=True
        )
        # ----------------------------------------------------
        # 1. DAILY SUMMARY
        # ----------------------------------------------------
        daily_file = (
            output_path / "daily_summary.csv"
        )
        self.daily_summary.to_csv(
            daily_file,
            index=False
        )
        # ----------------------------------------------------
        # 2. GRID SUMMARY
        # ----------------------------------------------------
        grid_file = (
            output_path / "grid_summary.csv"
        )
        self.grid_summary.to_csv(
            grid_file,
            index=False
        )
        # ----------------------------------------------------
        # 3. GRID/HOUR SUMMARY
        #    NP3 INPUT
        # ----------------------------------------------------
        grid_hour_file = (
            output_path / "grid_hour_summary.csv"
        )
        grid_hour_columns = [
            "grid_id",
            "timestamp",
            "sms_in",
            "sms_out",
            "call_in",
            "call_out",
            "internet_activity",
            "total_sms",
            "total_calls",
            "total_activity"
        ]
        grid_hour_output = (
            self.grid_time_df[
                grid_hour_columns
            ]
            .sort_values(
                ["grid_id", "timestamp"]
            )
            .reset_index(drop=True)
        )
        # ----------------------------------------------------
        # Validate grid/hour grain
        # ----------------------------------------------------
        duplicate_count = int(
            grid_hour_output
            .duplicated(
                subset=[
                    "grid_id",
                    "timestamp"
                ]
            )
            .sum()
        )
        if duplicate_count > 0:
            raise ValueError(
                "grid_hour_summary contains "
                f"{duplicate_count} duplicate "
                "grid_id/timestamp records."
            )
        # ----------------------------------------------------
        # Write grid/hour output
        # ----------------------------------------------------
        grid_hour_output.to_csv(
            grid_hour_file,
            index=False
        )
        # ----------------------------------------------------
        # Logging
        # ----------------------------------------------------
        logger.info(
            "Daily summary exported | path=%s",
            daily_file
        )
        logger.info(
            "Grid summary exported | path=%s",
            grid_file
        )
        logger.info(
            "Grid/hour summary exported | "
            "path=%s | rows=%d",
            grid_hour_file,
            len(grid_hour_output)
        )
        return (
            daily_file,
            grid_file,
            grid_hour_file
        )
    # ========================================================
    # COMPLETE PIPELINE
    # ========================================================
    def run(self, output_dir="output"):
        self.load_data()
        self.clean_data()
        self.derive_time_features()
        self.aggregate_to_grid_time()
        self.derive_activity_features()
        self.compute_kpis()
        files = self.export_summary(output_dir)
        logger.info(
            "UsageProcessor pipeline completed successfully."
        )
        return {
            "cleaned_data": self.df,
            "grid_time_data": self.grid_time_df,
            "daily_summary": self.daily_summary,
            "grid_summary": self.grid_summary,
            "output_files": files
        }

cleaner = UsageProcessor("D:/Milestone1proj/dataset/sms-call-internet-mi-2013-11-01.csv")
cleaner.run()