import pandas as pd
import sqlite3
import json
import os
from datetime import datetime, timedelta

def generate_comparison_report(ids):
    """
    Generates a comparison report for a list of record IDs.
    """
    # 1) First, get the standard aggregated metrics
    from tools.database import ActigraphDB
    db = ActigraphDB()
    df_summary = db.get_aggregated_metrics_for_ids(
        record_ids=ids,
        include_tables=["sleep_analysis", "activity_analysis", "light_analysis"],
        include_analysis_types=None,
        agg="mean",
    )

    # 2) Next, get sleep_light_exposure details for each ID
    db_path = os.path.join(os.getcwd(), 'Actigraph_record.db')
    conn = sqlite3.connect(db_path)
    query = "SELECT record_id, results FROM sleep_analysis WHERE analysis_type='sleep_light_exposure'"
    df_sleep_light = pd.read_sql_query(query, conn)

    sleep_light_metrics = []
    for _, row in df_sleep_light.iterrows():
        record_id = row['record_id']
        if record_id in ids:
            try:
                data = json.loads(row['results'])
                id_metrics = {"id": record_id}
                for metric, values in data.items():
                    if values:
                        minutes_list = [entry.get("minutes", 0) for entry in values if entry.get("minutes") is not None]
                        if minutes_list:
                            id_metrics[f"{metric}_mean_minutes"] = sum(minutes_list) / len(minutes_list)
                            id_metrics[f"{metric}_total_minutes"] = sum(minutes_list)
                            id_metrics[f"{metric}_count_days"] = len(minutes_list)
                        else:
                            id_metrics[f"{metric}_mean_minutes"] = 0
                            id_metrics[f"{metric}_total_minutes"] = 0
                            id_metrics[f"{metric}_count_days"] = 0
                sleep_light_metrics.append(id_metrics)
            except (json.JSONDecodeError, KeyError):
                pass
    df_sleep_light_summary = pd.DataFrame(sleep_light_metrics)

    # 3) Extract sleep periods and calculate durations
    query_periods = "SELECT record_id, results FROM sleep_analysis WHERE analysis_type='sleep_periods'"
    df_sleep_periods = pd.read_sql_query(query_periods, conn)
    conn.close()

    def calculate_sleep_duration(sleep_period):
        try:
            onset_datetime = datetime.strptime(f"{sleep_period['Sleep_onset_DATE'][:10]} {sleep_period['Sleep_onset_Time']}", "%Y-%m-%d %H:%M:%S")
            offset_datetime = datetime.strptime(f"{sleep_period['Sleep_offset_DATE'][:10]} {sleep_period['Sleep_offset_TIME']}", "%Y-%m-%d %H:%M:%S")
            if offset_datetime < onset_datetime:
                offset_datetime += timedelta(days=1)
            duration = offset_datetime - onset_datetime
            return duration.total_seconds() / 60
        except (KeyError, ValueError):
            return None

    sleep_periods_metrics = []
    for _, row in df_sleep_periods.iterrows():
        record_id = row['record_id']
        if record_id in ids:
            try:
                sleep_periods = json.loads(row['results'])
                durations = [d for d in [calculate_sleep_duration(p) for p in sleep_periods] if d is not None]
                if durations:
                    id_metrics = {
                        "id": record_id,
                        "sleep_duration_mean_minutes": sum(durations) / len(durations),
                        "sleep_duration_mean_hours": (sum(durations) / len(durations)) / 60,
                        "sleep_duration_total_minutes": sum(durations),
                        "sleep_duration_total_hours": sum(durations) / 60,
                        "sleep_periods_count": len(durations),
                        "sleep_duration_min_minutes": min(durations),
                        "sleep_duration_max_minutes": max(durations),
                        "sleep_duration_std_minutes": (sum((d - (sum(durations) / len(durations)))**2 for d in durations) / len(durations))**0.5 if len(durations) > 1 else 0
                    }
                    sleep_periods_metrics.append(id_metrics)
            except (json.JSONDecodeError, KeyError):
                pass
    df_sleep_periods_summary = pd.DataFrame(sleep_periods_metrics)

    # 4) Merge all datasets
    if not df_summary.empty:
        df_combined = df_summary.copy()
    else:
        df_combined = pd.DataFrame({'id': ids}).set_index('id')

    if not df_sleep_light_summary.empty:
        df_combined = df_combined.merge(df_sleep_light_summary.set_index('id'), on="id", how="outer")
    
    if not df_sleep_periods_summary.empty:
        df_combined = df_combined.merge(df_sleep_periods_summary.set_index('id'), on="id", how="outer")
    
    df_combined.reset_index(inplace=True)

    if df_combined.empty:
        return "No data found for the specified IDs.", None

    # 5) Create Tables
    # Table 1
    table_1 = df_combined[['id', 'sleep_analysis.cpd_mid_sleep.cpd_hours_mean','sleep_analysis.sri_sleep.SRI_mean', 'sleep_duration_min_minutes']].copy()
    table_1.rename(columns={'id': 'Period', 'sleep_analysis.cpd_mid_sleep.cpd_hours_mean': 'CPD1', 'sleep_analysis.sri_sleep.SRI_mean': 'SRI', 'sleep_duration_min_minutes': 'Duration'}, inplace=True)
    table_1 = table_1.round({'CPD1': 2, 'SRI': 2, 'Duration': 2})
    table_new = pd.DataFrame({"Name": ["CPD mid sleep", "SRI", "Sleep Duration"], "Period1": [table_1.loc[0, "CPD1"], table_1.loc[0, "SRI"], table_1.loc[0, "Duration"]], "Period2": [table_1.loc[1, "CPD1"], table_1.loc[1, "SRI"], table_1.loc[1, "Duration"]]})
    table_new["Difference"] = table_new["Period2"] - table_new["Period1"]
    table_1 = table_new.copy()

    # Table 2
    table_2 = df_combined[['id', 'metric1_mean_minutes','metric2_mean_minutes', 'metric3_mean_minutes']].copy()
    table_2.rename(columns={'id': 'Period', 'metric1_mean_minutes': '↑ recom. during sleep', 'metric2_mean_minutes': '↑ recom. before sleep', 'metric3_mean_minutes': '↓ recom. after waking'}, inplace=True)
    table_2 = table_2.round({'↑ recom. during sleep': 2, '↑ recom. before sleep': 2, '↓ recom. after waking': 2})
    table_new_2 = pd.DataFrame({"Name": ["↑ recom. during sleep", "↑ recom. before sleep", "↓ recom. after waking"], "Period1": [table_2.loc[0, "↑ recom. during sleep"], table_2.loc[0, "↑ recom. before sleep"], table_2.loc[0, "↓ recom. after waking"]], "Period2": [table_2.loc[1, "↑ recom. during sleep"], table_2.loc[1, "↑ recom. before sleep"], table_2.loc[1, "↓ recom. after waking"]]})
    table_new_2["Difference"] = table_new_2["Period2"] - table_new_2["Period1"]
    table_2 = table_new_2.copy()

    # Table 3
    table_3 = df_combined[['id', 'activity_analysis.activity_is_iv.IS_2day_mean', 'activity_analysis.activity_is_iv.IV_2day_mean']].copy()
    table_3.rename(columns={'id': 'Period', 'activity_analysis.activity_is_iv.IS_2day_mean': 'IS', 'activity_analysis.activity_is_iv.IV_2day_mean': 'IV'}, inplace=True)
    table_3 = table_3.round({'IS': 2, 'IV': 2})
    table_new_3 = pd.DataFrame({"Name": ["IS", "IV"], "Period1": [table_3.loc[0, "IS"], table_3.loc[0, "IV"]], "Period2": [table_3.loc[1, "IS"], table_3.loc[1, "IV"]]})
    table_new_3["Difference"] = table_new_3["Period2"] - table_new_3["Period1"]
    table_3 = table_new_3.copy()

    # Table 4
    table_4 = df_combined[['id', 'activity_analysis.activity_l5_m10_ra.M10_mean_mean', 'activity_analysis.activity_l5_m10_ra.L5_mean_mean', 'activity_analysis.activity_l5_m10_ra.RA_mean']].copy()
    table_4.rename(columns={'id': 'Period', 'activity_analysis.activity_l5_m10_ra.M10_mean_mean': 'M10', 'activity_analysis.activity_l5_m10_ra.L5_mean_mean': 'L5', 'activity_analysis.activity_l5_m10_ra.RA_mean': 'RA'}, inplace=True)
    table_4 = table_4.round({'M10': 2, 'L5': 2, 'RA': 2})
    table_new_4 = pd.DataFrame({"Name": ["M10", "L5", "RA"], "Period1": [table_4.loc[0, "M10"], table_4.loc[0, "L5"], table_4.loc[0, "RA"]], "Period2": [table_4.loc[1, "M10"], table_4.loc[1, "L5"], table_4.loc[1, "RA"]]})
    table_new_4["Difference"] = table_new_4["Period2"] - table_new_4["Period1"]
    table_4 = table_new_4.copy()

    # Table 5
    table_5 = df_combined[['id', 'activity_analysis.activity_cosinor.mesor_mean', 'activity_analysis.cpd_activity_acrophase.cpd_hours_mean']].copy()
    table_5.rename(columns={'id': 'Period', 'activity_analysis.activity_cosinor.mesor_mean': 'Mesor', 'activity_analysis.cpd_activity_acrophase.cpd_hours_mean': 'CPD2'}, inplace=True)
    table_5 = table_5.round({'Mesor': 2, 'CPD2': 2})
    table_new_5 = pd.DataFrame({"Name": ["Mesor", "CPD2"], "Period1": [table_5.loc[0, "Mesor"], table_5.loc[0, "CPD2"]], "Period2": [table_5.loc[1, "Mesor"], table_5.loc[1, "CPD2"]]})
    table_new_5["Difference"] = table_new_5["Period2"] - table_new_5["Period1"]
    table_5 = table_new_5.copy()

    # Table 6
    table_6 = df_combined[['id', 'light_analysis.light_is_iv.IS_2day_mean', 'light_analysis.light_is_iv.IV_2day_mean']].copy()
    table_6.rename(columns={'id': 'Period', 'light_analysis.light_is_iv.IS_2day_mean': 'IS', 'light_analysis.light_is_iv.IV_2day_mean': 'IV'}, inplace=True)
    table_6 = table_6.round({'IS': 2, 'IV': 2})
    table_new_6 = pd.DataFrame({"Name": ["IS", "IV"], "Period1": [table_6.loc[0, "IS"], table_6.loc[0, "IV"]], "Period2": [table_6.loc[1, "IS"], table_6.loc[1, "IV"]]})
    table_new_6["Difference"] = table_new_6["Period2"] - table_new_6["Period1"]
    table_6 = table_new_6.copy()

    # Table 7
    table_7 = df_combined[['id', 'light_analysis.light_l5_m10_ra.M10_mean_mean', 'light_analysis.light_l5_m10_ra.L5_mean_mean', 'light_analysis.light_l5_m10_ra.RA_mean']].copy()
    table_7.rename(columns={'id': 'Period', 'light_analysis.light_l5_m10_ra.M10_mean_mean': 'M10', 'light_analysis.light_l5_m10_ra.L5_mean_mean': 'L5', 'light_analysis.light_l5_m10_ra.RA_mean': 'RA'}, inplace=True)
    table_7 = table_7.round({'M10': 2, 'L5': 2, 'RA': 2})
    table_new_7 = pd.DataFrame({"Name": ["M10", "L5", "RA"], "Period1": [table_7.loc[0, "M10"], table_7.loc[0, "L5"], table_7.loc[0, "RA"]], "Period2": [table_7.loc[1, "M10"], table_7.loc[1, "L5"], table_7.loc[1, "RA"]]})
    table_new_7["Difference"] = table_new_7["Period2"] - table_new_7["Period1"]
    table_7 = table_new_7.copy()

    # Table 8
    table_8 = df_combined[['id', 'light_analysis.light_cosinor.mesor_mean', 'light_analysis.cpd_light_acrophase.cpd_hours_mean']].copy()
    table_8.rename(columns={'id': 'Period', 'light_analysis.light_cosinor.mesor_mean': 'Mesor', 'light_analysis.cpd_light_acrophase.cpd_hours_mean': 'CPD3'}, inplace=True)
    table_8 = table_8.round({'Mesor': 2, 'CPD3': 2})
    table_new_8 = pd.DataFrame({"Name": ["Mesor", "CPD3"], "Period1": [table_8.loc[0, "Mesor"], table_8.loc[0, "CPD3"]], "Period2": [table_8.loc[1, "Mesor"], table_8.loc[1, "CPD3"]]})
    table_new_8["Difference"] = table_new_8["Period2"] - table_new_8["Period1"]
    table_8 = table_new_8.copy()

    # 6) Generate an Enhanced HTML Report
    header = "Report"
    Quick_summary="This report provides a comprehensive analysis of the circadian rhythms and activity patterns of the subjects over the study period."
    report_sections = {
        "Sleep and Circadian Health": {
            "Circadian Rhythms and Sleep Metrics": table_1,
            "Light Exposure Recommendations": table_2,
        },
        "Activity Patterns": {
            "Interdaily Stability (IS) and Intradaily Variability (IV)": table_3,
            "Most Active 10h (M10), Least Active 5h (L5), and Relative Amplitude (RA)": table_4,
            "Cosinor Analysis (Mesor and Acrophase)": table_5,
        },
        "Light Exposure Patterns": {
            "Light Exposure IS and IV": table_6,
            "Light Exposure L5, M10, and RA": table_7,
            "Light Exposure Cosinor Analysis": table_8,
        }
    }

    html_report = f"""
    <html>
    <head>
        <title>Circadian Medicine Report</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; background-color: #f9f9f9; color: #333; }}
            .container {{ max-width: 900px; margin: 40px auto; padding: 20px; background-color: #fff; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.05); }}
            h1 {{ color: #1a237e; text-align: center; border-bottom: 2px solid #3949ab; padding-bottom: 10px; margin-bottom: 10px; }}
            h2 {{ color: #3949ab; border-bottom: 1px solid #c5cae9; padding-bottom: 8px; margin-top: 40px; }}
            h3 {{ color: #5c6bc0; margin-top: 30px; }}
            p.summary {{ text-align: center; font-size: 1.1em; color: #555; margin-bottom: 30px; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
            th, td {{ border: 1px solid #e0e0e0; padding: 12px; text-align: left; }}
            th {{ background-color: #e8eaf6; font-weight: 600; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            .navbar {{ background-color: #3949ab; padding: 10px 0; text-align: center; border-radius: 8px 8px 0 0; }}
            .navbar a {{ color: white; padding: 10px 20px; text-decoration: none; font-weight: 500; }}
            .navbar a:hover {{ background-color: #5c6bc0; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{header}</h1>
            <p class="summary">{Quick_summary}</p>
            <div class="navbar">
                <a href="#section-sleep">Sleep & Circadian Health</a>
                <a href="#section-activity">Activity Patterns</a>
                <a href="#section-light">Light Exposure</a>
            </div>
    """
    for section_id, (section_title, tables) in enumerate(report_sections.items()):
        html_report += f'<h2 id="section-{"sleep" if section_id == 0 else ("activity" if section_id == 1 else "light")}">{section_title}</h2>'
        for title, df in tables.items():
            html_report += f"<h3>{title}</h3>"
            html_report += df.to_html(index=False, border=0)
    html_report += "</div></body></html>"

    return html_report, df_combined
