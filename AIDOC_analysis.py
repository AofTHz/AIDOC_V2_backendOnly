import asyncio
import glob
import json
import os
import pathlib
import shutil
import uuid

import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, accuracy_score
from sqlmodel import Session

from AIDOC_database import get_folder, get_session_internal
from AIDOC_files_reciver import return_result
from backend.AIDOC_geminiAPI import generate_response

async def predict_folder_async(pdf_path, session: Session):
    folder_list = get_folder(session)
    pdf_file = pathlib.Path(pdf_path)
    task_id = str(uuid.uuid4())

    # Create the temp folder for this task
    temp_folder = pathlib.Path("database") / "temp" / task_id
    temp_folder.mkdir(parents=True, exist_ok=True)

    # 1) Copy the original PDF file into that folder
    target_pdf = temp_folder / pdf_file.name
    shutil.copy(pdf_file, target_pdf)

    # 2) Read the file in binary (so we can pass bytes to return_result)
    with open(target_pdf, "rb") as f:
        pdf_bytes = f.read()

    # 3) Pass the bytes to return_result
    result, accuracy = return_result(pdf_bytes, task_id, folder_list, target_pdf.name)
    return result
async def collect_ground_truth_and_predictions_async(session: Session):
    base_folder = "TestSet"
    folder_labels = ["MobileApp", "WebApp", "HardwareIOT"]
    y_true = []
    y_pred = []
    misclassified_files = []

    pdf_paths = []

    for folder in folder_labels:
        folder_path = os.path.join(base_folder, folder)
        pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
        for pdf_path in pdf_files:
            y_true.append(folder)
            pdf_paths.append(pdf_path)

    predictions = await asyncio.gather(*[asyncio.create_task(predict_folder_async(pdf_path, session)) for pdf_path in pdf_paths])

    for pdf_path, true_label, predicted_label in zip(pdf_paths, y_true, predictions):
        y_pred.append(predicted_label)

        if true_label != predicted_label:  # If misclassified
            misclassified_files.append(os.path.basename(pdf_path))  # Just store file names

    # Save filenames of misclassified PDFs for later re-processing
    with open("misclassified_files.json", "w", encoding="utf-8") as f:
        json.dump(misclassified_files, f, indent=4, ensure_ascii=False)

    return y_true, y_pred, misclassified_files

async def main():
    # Collect labels (actual vs. predicted)
    session = get_session_internal()
    y_true, y_pred, misclassified_data = await collect_ground_truth_and_predictions_async(session)

    # Save misclassified data for review (optional)
    if misclassified_data:
        print(f"Found {len(misclassified_data)} misclassified documents.")
        with open("misclassified_data.json", "w", encoding="utf-8") as f:
            json.dump(misclassified_data, f, indent=4, ensure_ascii=False)
    else:
        print("No misclassified documents found.")

    # Build confusion matrix
    labels = ["MobileApp", "WebApp", "HardwareIOT"]
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    print("Confusion Matrix:\n", cm)

    # Accuracy (optional)
    acc = accuracy_score(y_true, y_pred)
    print("Accuracy:", acc)

    # Visualize the confusion matrix (optional)
    plt.figure(figsize=(6, 4))
    sns.heatmap(cm, annot=True, fmt="d", xticklabels=labels, yticklabels=labels, cmap='Blues')
    plt.ylabel("Actual")
    plt.xlabel("Predicted")
    plt.title("Confusion Matrix")
    plt.show()

if __name__ == "__main__":
    asyncio.run(main())
