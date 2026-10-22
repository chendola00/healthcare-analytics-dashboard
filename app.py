import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
import numpy as np

st.set_page_config(
    page_title="Healthcare Analytics Dashboard",
    page_icon="🏥",
    layout="wide"
)

DATA_PATH = Path(__file__).resolve().parent / "data/processed/diabetes_cleaned.csv"


@st.cache_data
def load_data():
    return pd.read_csv(DATA_PATH, dtype={"payer_code": "string"})

def wilson_ci(successes, total, z=1.96):
    """Return Wilson 95% confidence limits as percentages."""
    if total <= 0:
        return np.nan, np.nan
    p = successes / total
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    margin = z * np.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominator
    return (center - margin) * 100, (center + margin) * 100


def summarize_readmissions(data, group_column):
    """Summarize encounter-level readmissions with Wilson confidence limits."""
    summary = (
        data.groupby(group_column, observed=True)
        .agg(
            total_encounters=("readmitted_30d", "size"),
            readmissions=("readmitted_30d", "sum"),
            readmission_rate=("readmitted_30d", "mean"),
        )
        .reset_index()
    )
    summary["readmission_rate"] *= 100
    if summary.empty:
        summary["ci_lower"] = pd.Series(dtype=float)
        summary["ci_upper"] = pd.Series(dtype=float)
    else:
        summary[["ci_lower", "ci_upper"]] = summary.apply(
            lambda row: pd.Series(wilson_ci(row["readmissions"], row["total_encounters"])),
            axis=1,
        )
    return summary


def confidence_error_arrays(summary):
    """Plotly uses positive and negative distances from the point estimate."""
    return (
        (summary["ci_upper"] - summary["readmission_rate"]).clip(lower=0),
        (summary["readmission_rate"] - summary["ci_lower"]).clip(lower=0),
    )


df = load_data()

# Basic dataset validation
required_columns = [
    "patient_nbr",
    "age",
    "gender",
    "diabetesMed",
    "time_in_hospital",
    "readmitted_30d"
]

missing_columns = [
    col for col in required_columns
    if col not in df.columns
]

if missing_columns:
    st.error(f"Missing required columns: {missing_columns}")
    st.stop()

if not df["readmitted_30d"].isin([0, 1]).all():
    st.error("Invalid values found in readmitted_30d.")
    st.stop()

st.title("🏥 Healthcare Analytics Dashboard")
st.caption("Exploratory Analysis of Hospital Readmissions in Diabetes Patients")

st.sidebar.header("Filters")
age_options = sorted(df["age"].dropna().unique().tolist())
selected_ages = st.sidebar.multiselect("Age Group", options=age_options, default=age_options)

gender_options = sorted(df["gender"].dropna().unique().tolist())
selected_genders = st.sidebar.multiselect("Gender", options=gender_options, default=gender_options)

medication_options = sorted(df["diabetesMed"].dropna().unique().tolist())
selected_medications = st.sidebar.multiselect(
    "Diabetes Medication", options=medication_options, default=medication_options
)

filtered_df = df[
    df["age"].isin(selected_ages)
    & df["gender"].isin(selected_genders)
    & df["diabetesMed"].isin(selected_medications)
].copy()

total_encounters = len(filtered_df)
unique_patients = filtered_df["patient_nbr"].nunique()
readmissions = int(filtered_df["readmitted_30d"].sum())
readmission_rate = readmissions / total_encounters * 100 if total_encounters else 0

st.divider()
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Encounters", f"{total_encounters:,}")
col2.metric("Unique Patients", f"{unique_patients:,}")
col3.metric("30-Day Readmissions", f"{readmissions:,}")
col4.metric("Readmission Rate", f"{readmission_rate:.2f}%")
st.divider()

st.subheader("30-Day Readmission Rate by Age Group")
if filtered_df.empty:
    st.warning("No data matches the selected filters.")
else:
    age_summary = summarize_readmissions(filtered_df, "age")
    age_summary["age"] = pd.Categorical(
        age_summary["age"], categories=age_options, ordered=True
    )
    age_summary = age_summary.sort_values("age")
    age_plus, age_minus = confidence_error_arrays(age_summary)
    fig_age = px.bar(
        age_summary,
        x="age", y="readmission_rate",
        error_y=age_plus, error_y_minus=age_minus,
        labels={"age": "Age Group", "readmission_rate": "30-Day Readmission Rate (%)"},
        hover_data={
            "total_encounters": True,
            "readmissions": True,
            "readmission_rate": ":.2f",
            "ci_lower": ":.2f",
            "ci_upper": ":.2f",
        },
        title="Readmission Rate Across Age Groups (95% CI)",
    )
    fig_age.update_layout(xaxis_title="Age Group", yaxis_title="Readmission Rate (%)")
    st.plotly_chart(fig_age, use_container_width=True)
    with st.expander("View Age Group Summary"):
        st.dataframe(age_summary, hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("Additional Readmission Analysis")

    los_summary = summarize_readmissions(filtered_df, "time_in_hospital")
    los_plus, los_minus = confidence_error_arrays(los_summary)
    fig_los = px.line(
        los_summary,
        x="time_in_hospital", y="readmission_rate", markers=True,
        error_y=los_plus, error_y_minus=los_minus,
        title="Readmission Rate by Length of Stay (95% CI)",
        labels={
            "time_in_hospital": "Length of Stay (Days)",
            "readmission_rate": "30-Day Readmission Rate (%)",
        },
        hover_data={
            "total_encounters": True, "readmissions": True,
            "ci_lower": ":.2f", "ci_upper": ":.2f",
        },
    )
    fig_los.update_xaxes(dtick=1)
    st.plotly_chart(fig_los, use_container_width=True)

    gender_summary = summarize_readmissions(
        filtered_df[filtered_df["gender"].isin(["Female", "Male"])], "gender"
    )
    medication_summary = summarize_readmissions(filtered_df, "diabetesMed")

    col_left, col_right = st.columns(2)
    with col_left:
        if gender_summary.empty:
            st.info("No Female or Male encounters match the selected filters.")
        else:
            gender_plus, gender_minus = confidence_error_arrays(gender_summary)
            fig_gender = px.bar(
                gender_summary,
                x="gender", y="readmission_rate", color="gender",
                error_y=gender_plus, error_y_minus=gender_minus,
                title="Readmission Rate by Gender (95% CI)",
                labels={"gender": "Gender", "readmission_rate": "Readmission Rate (%)"},
                text_auto=".2f",
                hover_data={
                    "total_encounters": True, "readmissions": True,
                    "ci_lower": ":.2f", "ci_upper": ":.2f",
                },
            )
            fig_gender.update_layout(showlegend=False)
            st.plotly_chart(fig_gender, use_container_width=True)

    with col_right:
        medication_plus, medication_minus = confidence_error_arrays(medication_summary)
        fig_med = px.bar(
            medication_summary,
            x="diabetesMed", y="readmission_rate", color="diabetesMed",
            error_y=medication_plus, error_y_minus=medication_minus,
            title="Readmission Rate by Diabetes Medication (95% CI)",
            labels={
                "diabetesMed": "Diabetes Medication Recorded",
                "readmission_rate": "Readmission Rate (%)",
            },
            text_auto=".2f",
            hover_data={
                "total_encounters": True, "readmissions": True,
                "ci_lower": ":.2f", "ci_upper": ":.2f",
            },
        )
        fig_med.update_layout(showlegend=False)
        st.plotly_chart(fig_med, use_container_width=True)

    st.caption(
        "95% confidence intervals use the Wilson score method at the encounter level. "
        "Repeated encounters from the same patient may not be independent."
    )
