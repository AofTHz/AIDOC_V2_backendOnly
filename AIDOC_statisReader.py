import pandas as pd
import json
import matplotlib.pyplot as plt


def parse_accuracy(acc_text):
    """Convert '[20, 5, 75]' into a Python list [20, 5, 75]."""
    try:
        return json.loads(acc_text.replace("'", '"'))
    except (json.JSONDecodeError, TypeError):
        return []


def get_first_guess_index(scores):
    """Return the index of the highest value in a list."""
    if not scores or len(scores) < 3:
        return None
    sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return sorted_indices[0]


def get_second_guess_index(scores):
    """Return the index of the second-highest value in a list."""
    if not scores or len(scores) < 3:
        return None
    sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return sorted_indices[1]


def get_third_guess_index(scores):
    """Return the index of the third-highest value in a list."""
    if not scores or len(scores) < 3:
        return None
    sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return sorted_indices[2]


def has_keywords(details_text):
    """Return 1 if the file contains at least one keyword, otherwise 0."""
    try:
        kw_dict = json.loads(details_text.replace("'", '"'))
        return 1 if kw_dict else 0
    except (json.JSONDecodeError, TypeError):
        return 0


def main():
    # 1) Read CSV without column names (ensuring correct column count)
    df = pd.read_csv("database/statistics.csv", header=None, usecols=[0, 1, 2, 3, 4])
    df = df[df[0] != "TOTAL"].copy()

    # Parse accuracy array from column 4
    df["AccuracyArray"] = df[4].apply(parse_accuracy)

    # Compute sorted scores for each file (if exactly 3 values exist, otherwise default to zeros)
    df["SortedScores"] = df["AccuracyArray"].apply(
        lambda s: sorted(s, reverse=True) if (s and len(s) == 3) else [0, 0, 0])
    df["FirstGuessValue"] = df["SortedScores"].apply(lambda s: s[0])
    df["SecondGuessValue"] = df["SortedScores"].apply(lambda s: s[1])
    df["ThirdGuessValue"] = df["SortedScores"].apply(lambda s: s[2])

    # Also compute guess indices per file for folder mapping
    df["FirstGuessIndex"] = df["AccuracyArray"].apply(get_first_guess_index)
    df["SecondGuessIndex"] = df["AccuracyArray"].apply(get_second_guess_index)
    df["ThirdGuessIndex"] = df["AccuracyArray"].apply(get_third_guess_index)

    # Folder labels for mapping indices [0, 1, 2]
    folder_labels = ["MobileApp", "HardwareIOT", "WebApp"]

    # -------------------
    # Calculate Distribution by Folder (File Count)
    # -------------------
    first_guess_counts = df["FirstGuessIndex"].value_counts().sort_index()
    second_guess_counts = df["SecondGuessIndex"].value_counts().sort_index()
    third_guess_counts = df["ThirdGuessIndex"].value_counts().sort_index()

    first_guess_data = [first_guess_counts.get(i, 0) for i in range(len(folder_labels))]
    second_guess_data = [second_guess_counts.get(i, 0) for i in range(len(folder_labels))]
    third_guess_data = [third_guess_counts.get(i, 0) for i in range(len(folder_labels))]

    # -------------------
    # Calculate Overall Confidence Percentages using the score values
    # -------------------
    total_first_value = df["FirstGuessValue"].sum()
    total_second_value = df["SecondGuessValue"].sum()
    total_third_value = df["ThirdGuessValue"].sum()
    overall_total = total_first_value + total_second_value + total_third_value

    first_percentage = (total_first_value / overall_total * 100) if overall_total else 0
    second_percentage = (total_second_value / overall_total * 100) if overall_total else 0
    third_percentage = (total_third_value / overall_total * 100) if overall_total else 0

    # -------------------
    # Combined Guess Distribution Chart with Overall Percentages
    # -------------------
    fig, axs = plt.subplots(1, 3, figsize=(18, 6))
    guess_types = ["First Guess", "Second Guess", "Third Guess"]
    guess_data_list = [first_guess_data, second_guess_data, third_guess_data]
    overall_percentages = [first_percentage, second_percentage, third_percentage]

    for ax, guess_type, data, percentage in zip(axs, guess_types, guess_data_list, overall_percentages):
        ax.pie(data, labels=folder_labels, autopct="%1.1f%%", startangle=140)
        ax.set_title(f"{guess_type}\nOverall Confidence: {percentage:.1f}%")

    plt.suptitle("Combined Guess Distributions (by Folder & Confidence)")
    plt.savefig("guess_distribution_combined.png", dpi=150)
    plt.close()

    # -------------------
    # Count files that contained at least one keyword
    # -------------------
    df["HasKeywords"] = df[3].apply(has_keywords)
    num_files_with_keywords = df["HasKeywords"].sum()

    # -------------------
    # Save updated statistics with a 'TOTAL' row for keywords
    # -------------------
    summary_row = pd.DataFrame([["TOTAL_KEYWORD_FOUND", "", num_files_with_keywords, "", ""]])
    df_updated = pd.concat([df, summary_row], ignore_index=True)
    df_updated.to_csv("database/statistics_updated.csv", index=False, header=False, encoding="utf-8-sig")

    # Print summary information to the console
    print("=== Statistics Updated ===")
    print(" - Combined guess distribution image saved as 'guess_distribution_combined.png'")
    print(f" - Overall Confidence Percentages:")
    print(f"    First Guess: {first_percentage:.1f}%")
    print(f"    Second Guess: {second_percentage:.1f}%")
    print(f"    Third Guess: {third_percentage:.1f}%")
    print(" - database/statistics_updated.csv updated")
    print(f" - {num_files_with_keywords} files contained keywords")


if __name__ == "__main__":
    main()
