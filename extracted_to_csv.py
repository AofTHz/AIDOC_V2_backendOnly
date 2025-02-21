import json
import csv

# Input JSON file and Output CSV file
input_json = "extracted_training_data.json"
output_csv = "exported_data.csv"

# Load JSON data
with open(input_json, "r", encoding="utf-8") as f:
    extracted_data = json.load(f)

# Prepare data for CSV export
with open(output_csv, "w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)

    for item in extracted_data:
        # Get extracted text (fallback to empty string if missing)
        extracted_text = item.get("extracted_text", "").strip()

        # Get the label (edited_label > predicted_label > folder)
        label = (item.get("edited_label", "").strip() or
                 item.get("predicted_label", "").strip() or
                 item.get("folder", ""))

        # Get accuracy (edited_accuracy > accuracy)
        accuracy = item.get("edited_accuracy") or item.get("accuracy", [])

        # Ensure accuracy is a valid list
        if isinstance(accuracy, list) and len(accuracy) == 3:
            accuracy_str = f"[{accuracy[0]},{accuracy[1]},{accuracy[2]}]"
        else:
            accuracy_str = "[0,0,0]"  # Default fallback

        # Write row to CSV (no header, 2 columns)
        writer.writerow([extracted_text, f"{label}, {accuracy_str}"])

print(f"CSV export complete! Data saved to {output_csv}")
