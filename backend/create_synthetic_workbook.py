import os
from pathlib import Path
import pandas as pd

def create_synthetic_workbook():
    target_path = Path("sample_data") / "Business_Reporting_Dashboard_Synthetic_Test_Workbook.xlsx"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(target_path, engine="openpyxl") as writer:
        # Sheet 1: Paynter 2026
        df_rejections = pd.DataFrame(
            {
                "Month": [
                    "Jan-26", "Jan-26", "Feb-26", "Mar-26", "Apr-26",
                    "May-26", "Jun-26", "Jul-26", "Aug-26",
                ],
                "Model": [
                    "157 TY", "367 TY", "157 TY", "457 TY", "Milwaukee",
                    "157 TY", "367 TY", "457 TY", "157 TY",
                ],
                "Defect": [
                    "Scratch", "Dent", "Scratch", "Burr", "Dimension",
                    "Dent", "Scratch", "Scratch", "Dent",
                ],
                "Count": [100, 57, 101, 93, 48, 60, 86, 132, 277],
                "PPM": [2700.0, 1529.0, 2718.0, 2514.0, 1307.0, 1618.0, 2318.0, 3565.0, 7458.0],
            }
        )
        df_rejections.to_excel(writer, sheet_name="Paynter 2026", index=False)

        # Sheet 2: Action Tracker
        df_actions = pd.DataFrame(
            {
                "Action_Item": ["Rework fixture 4", "Check calibration", "Tool replacement", "Sensor update"],
                "Champion": ["John D.", "Sarah M.", "John D.", "Alex K."],
                "Due_Date": ["2026-02-15", "2026-12-01", "2026-01-10", "2026-03-30"],
                "Closure_Date": ["2026-02-14", None, None, None],
                "Action_Status": ["closed", "open", "overdue", "open"],
            }
        )
        df_actions.to_excel(writer, sheet_name="Action Tracker", index=False)

        # Sheet 3: Targets
        df_targets = pd.DataFrame(
            {
                "Month": ["Jan-26", "Feb-26", "Mar-26", "Apr-26", "May-26", "Jun-26", "Jul-26", "Aug-26"],
                "Target_PPM": [3000, 3000, 2800, 2800, 2500, 2500, 2200, 2000],
                "Target_Production": [40000, 42000, 41000, 39000, 43000, 44000, 45000, 46000],
            }
        )
        df_targets.to_excel(writer, sheet_name="Targets", index=False)

    print(f"Created {target_path} successfully ({target_path.stat().st_size} bytes)")

    # Also copy to workspace root so it matches both paths
    root_path = Path("Business_Reporting_Dashboard_Synthetic_Test_Workbook.xlsx")
    import shutil
    shutil.copyfile(target_path, root_path)
    print(f"Copied to {root_path} successfully")

if __name__ == "__main__":
    create_synthetic_workbook()
