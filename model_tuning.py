import logging
import os
import glob
import uuid
import pathlib
import json
import shutil
import sys
import google.generativeai as generativeai
import google.genai as genai
from AIDOC_files_reciver import return_result_with_text
import os

os.environ["GOOGLE_API_KEY"] = "AIzaSyCvBQuefC2a9kOsOSd4zDqYmttZIi2O0Y4"


# Configure your Gemini API
generativeai.configure(api_key="AIzaSyCvBQuefC2a9kOsOSd4zDqYmttZIi2O0Y4")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_training_data_editable(base_folder="TestSet", output_file="extracted_training_data.json"):
    """
    Goes through PDFs in TestSet and extracts text via return_result_with_text.
    Saves a JSON file with fields that you can manually edit (e.g., to adjust labels and accuracy).
    """
    folder_labels = ["MobileApp", "HardwareIOT", "WebApp"]
    extracted_data = []

    for label in folder_labels:
        pdf_dir = os.path.join(base_folder, label)
        if not os.path.isdir(pdf_dir):
            continue

        pdf_files = glob.glob(os.path.join(pdf_dir, "*.pdf"))
        for pdf_path in pdf_files:
            print(f"Extracting text from {pdf_path} (folder={label})")
            task_id = str(uuid.uuid4())
            temp_folder = pathlib.Path("database") / "temp" / task_id
            temp_folder.mkdir(parents=True, exist_ok=True)
            target_pdf = temp_folder / pathlib.Path(pdf_path).name
            shutil.copy(pdf_path, target_pdf)
            with open(target_pdf, "rb") as f:
                pdf_bytes = f.read()
            try:
                # Call return_result_with_text to get predicted label, accuracy, and extracted text.
                predicted_label, accuracy, extracted_text = return_result_with_text(
                    pdf_bytes,
                    task_id,
                    folder_labels,  # using our list as a placeholder for folder_list
                    target_pdf.name
                )
            except Exception as e:
                print(f"Error extracting text from {pdf_path}: {e}")
                predicted_label = ""
                accuracy = ""
                extracted_text = ""
            # Build a record with original info and empty fields for manual editing.
            extracted_data.append({
                "pdf_path": pdf_path,
                "filename": target_pdf.name,
                "folder": label,
                "predicted_label": predicted_label,
                "edited_label": "",        # leave empty for manual editing if needed
                "accuracy": accuracy,
                "edited_accuracy": "",     # leave empty to allow manual adjustments
                "extracted_text": extracted_text,
            })
            shutil.rmtree(temp_folder, ignore_errors=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(extracted_data, f, indent=4, ensure_ascii=False)
    print(f"Extraction complete. Data saved to {output_file}")
    return output_file

def build_training_data_from_extracted_file(input_file="extracted_training_data.json"):
    with open(input_file, "r", encoding="utf-8") as f:
        extracted_data = json.load(f)

    training_pairs = []
    for index, item in enumerate(extracted_data):
        text_input = item.get("extracted_text", "")

        # Get the raw label from edited_label, predicted_label, or folder
        raw_label = (item.get("edited_label", "").strip() or
                     item.get("predicted_label", "").strip() or
                     item.get("folder", ""))

        # Retrieve accuracy values, preferring edited_accuracy if available
        accuracy_val = item.get("edited_accuracy") or item.get("accuracy", [])

        # Ensure accuracy is a list of exactly three numbers before formatting
        if isinstance(accuracy_val, list) and len(accuracy_val) == 3:
            accuracy_str = f"[{accuracy_val[0]},{accuracy_val[1]},{accuracy_val[2]}]"
        else:
            accuracy_str = ""  # If accuracy is missing or malformed, exclude it

        # Construct final output format
        output_label = f"{raw_label},{accuracy_str}" if accuracy_str else raw_label

        if text_input and text_input.strip():
            training_pairs.append((text_input, output_label))

        # Logging transformation details
        logger.info(f"Processed {index + 1}/{len(extracted_data)}: {output_label}")

    logger.info(f"Total training examples generated: {len(training_pairs)}")

    return training_pairs

def tune_model_with_pdf_data(training_data, tuned_model_name):
    """
    Fine-tunes the model using genai.create_tuned_model with training data provided as a list of dicts.
    Logs a preview of the training examples that the AI model is receiving.
    """
    # Prepare training data as a list of dictionaries
    training_examples = [
        {"text_input": input_text, "output": label_text}
        for input_text, label_text in training_data
    ]

    # Log a preview of the training data that will be used for tuning
    preview_count = min(20, len(training_examples))
    logger.info(f"Previewing the first {preview_count} training examples for model tuning:")
    for example in training_examples[:preview_count]:
        logger.info(f"Example output: {example['output']}")

    logger.info("Starting model tuning on extracted PDF text data...")

    # Use genai.create_tuned_model with dict-based training data
    operation = generativeai.create_tuned_model(
        source_model='models/gemini-1.5-flash-001-tuning',
        training_data=training_examples,
        id=tuned_model_name,
        display_name=tuned_model_name,
        epoch_count=5,
        batch_size=2,
        learning_rate=0.00001
    )
    # Wait for tuning to complete
    tuned_model = operation.result()  # tuned_model.model contains the model ID

    # Generate sample content with the tuned model
    client = genai.Client()
    response = client.models.generate_content(
        model=f"tunedModels/{tuned_model_name}",
        contents='55'
    )

    logger.info("Tuning job completed. Generated content sample:")
    logger.info(response.text)

    _save_tuned_model_info(tuned_model.model, {
        "epoch_count": 5,
        "batch_size": 2,
        "learning_rate": 0.00001,
        "display_name": tuned_model_name
    }, training_data)
    logger.info(f"[OK] Tuning complete. Model name: {tuned_model.model}\n")

def _save_tuned_model_info(tuned_model_name, config, training_data, path="database/tuning_results.json"):
    tuning_data = {
        "tuned_model": tuned_model_name,
        "epoch_count": config["epoch_count"],
        "batch_size": config["batch_size"],
        "learning_rate": config["learning_rate"],
        "num_training_examples": len(training_data),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tuning_data, f, indent=4)
    print(f"Tuned model info saved to {path}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "extract":
        extract_training_data_editable()
    elif len(sys.argv) > 1 and sys.argv[1] == "train":
        training_data = build_training_data_from_extracted_file()
        if not training_data:
            print(
                "No training data found in the extracted file. Please run extraction first and edit the file if needed.")
        else:
            tune_model_with_pdf_data(training_data, tuned_model_name="pdf-tuned-model4")
            print("\nAll done!")
    elif len(sys.argv) > 1 and sys.argv[1] == "test":
        client = genai.Client()
        response = client.models.generate_content(
            model=f"tunedModels/pdf-tuned-model4",
            contents='55'
        )
        print(response.text)
    elif len(sys.argv) > 1 and sys.argv[1] == "delete":
        client = genai.Client()
        generativeai.delete_tuned_model(f'tunedModels/pdf-tuned-model4')
    else:
        print("Usage: python model_tuning.py [extract|train]")