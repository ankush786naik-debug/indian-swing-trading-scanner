
import csv
import json
import os


OUTPUT_DIR = "data"


def ensure_output_directory():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def export_json(data, filename):

    ensure_output_directory()

    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False,
            default=str
        )

    return filepath


def export_csv(data, filename):

    ensure_output_directory()

    if isinstance(data, dict):
        data = [data]

    if not data:
    return None

    if not all(isinstance(row, dict) for row in data):
        raise ValueError("CSV export requires dictionary rows.")

    filepath = os.path.join(OUTPUT_DIR, filename)

    columns = list(dict.fromkeys(
        key
        for row in data
        for key in row.keys()
    ))

    with open(
        filepath,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=columns,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(data)

    return filepath
