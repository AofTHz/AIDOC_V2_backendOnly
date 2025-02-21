import asyncio
import json
import os
import glob
import pathlib
import shutil
import uuid
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, accuracy_score
from sqlmodel import Session

from AIDOC_files_reciver import return_result_with_text
from AIDOC_database import get_folder, get_session_internal

def load_tuned_model(path="database/tuning_results.json"):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("tuned_model")
    return None

async def predict_with_model(pdf_path, session: Session, tuned_model=None):
    folder_list = get_folder(session)
    task_id = str(uuid.uuid4())
    temp_folder = pathlib.Path("database") / "temp" / task_id
    temp_folder.mkdir(parents=True, exist_ok=True)
    pdf_file = pathlib.Path(pdf_path)
    target_pdf = temp_folder / pdf_file.name
    shutil.copy(pdf_file, target_pdf)
    with open(target_pdf, "rb") as f:
        pdf_bytes = f.read()

    # Call return_result_with_text with all required parameters:
    label, accuracy, full_text = return_result_with_text(
        pdf_bytes,
        task_id,
        folder_list,
        target_pdf.name
        # If your function later supports tuned_model, you could pass it here
    )
    return label

async def evaluate_model(session: Session, tuned_model=None):
    base_folder = "TestSet"
    folder_labels = ["MobileApp", "HardwareIOT", "WebApp"]
    y_true, y_pred = [], []
    pdf_paths = []
    for folder in folder_labels:
        folder_path = os.path.join(base_folder, folder)
        pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
        for pdf_path in pdf_files:
            y_true.append(folder)
            pdf_paths.append(pdf_path)
    tasks = []
    for pdf_path in pdf_paths:
        tasks.append(asyncio.create_task(predict_with_model(pdf_path, session, tuned_model)))
    y_pred = await asyncio.gather(*tasks)
    return y_true, y_pred

async def main():
    tuned_model = load_tuned_model()
    if tuned_model:
        print(f"Loaded tuned model: {tuned_model}")
    else:
        print("No tuned model found; fallback only.")
    session = get_session_internal()
    y_true, y_pred = await evaluate_model(session, tuned_model)
    labels = ["MobileApp", "HardwareIOT", "WebApp"]
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    print("\nConfusion Matrix:\n", cm)
    acc = accuracy_score(y_true, y_pred)
    print("Accuracy:", acc)
    plt.figure(figsize=(6, 4))
    sns.heatmap(cm, annot=True, fmt="d", xticklabels=labels, yticklabels=labels, cmap="Blues")
    plt.ylabel("Actual")
    plt.xlabel("Predicted")
    plt.title("Confusion Matrix")
    plt.show()

if __name__ == "__main__":
    asyncio.run(main())
