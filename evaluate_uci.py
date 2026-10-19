"""Reproducible evaluation against UCI hydraulic condition-monitoring data.

Run: python evaluate_uci.py path/to/TS1-VS1-profile-directory
The source data is not redistributed here.
"""

import json
import statistics
import sys
import zipfile
import csv
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import detect_anomalies  # noqa: E402


def read_matrix(archive, suffix):
    matches = [name for name in archive.namelist() if name.lower().endswith(suffix.lower())]
    if len(matches) != 1:
        raise ValueError(f"Expected one {suffix}; found {matches}")
    with archive.open(matches[0]) as stream:
        for raw in stream:
            yield [float(value) for value in raw.decode("utf-8").split()]


def read_local_matrix(directory, name):
    with (directory / name).open("r", encoding="utf-8") as stream:
        for line in stream:
            yield [float(value) for value in line.split()]


def scores(predicted, actual):
    tp = sum(p and a for p, a in zip(predicted, actual))
    fp = sum(p and not a for p, a in zip(predicted, actual))
    fn = sum(not p and a for p, a in zip(predicted, actual))
    tn = sum(not p and not a for p, a in zip(predicted, actual))
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "specificity": tn / (tn + fp) if tn + fp else None,
    }


def main():
    archive_path = Path(sys.argv[1])
    if archive_path.is_dir():
        temperatures = list(read_local_matrix(archive_path, "TS1.txt"))
        vibrations = list(read_local_matrix(archive_path, "VS1.txt"))
        profile = list(read_local_matrix(archive_path, "profile.txt"))
    else:
        with zipfile.ZipFile(archive_path) as archive:
            temperatures = list(read_matrix(archive, "TS1.txt"))
            vibrations = list(read_matrix(archive, "VS1.txt"))
            profile = list(read_matrix(archive, "profile.txt"))
    if not (len(temperatures) == len(vibrations) == len(profile) == 2205):
        raise ValueError("Unexpected number of cycles")
    if any(len(t) != 60 or len(v) != 60 for t, v in zip(temperatures, vibrations)):
        raise ValueError("Unexpected sample count for 1 Hz sensor")

    labels = [not (p[0] == 100 and p[1] == 100 and p[2] == 0 and p[3] == 130) for p in profile]
    cooler_labels = [p[0] != 100 for p in profile]
    results = {
        "source": "UCI dataset 447 Condition monitoring of hydraulic systems",
        "cycles": len(profile),
        "nonoptimal_cycles_any_component": sum(labels),
        "nonoptimal_cycles_cooler": sum(cooler_labels),
        "aggregation": {},
    }
    for name, aggregate in (("mean", statistics.mean), ("max", max)):
        readings = [
            {"timestamp": f"cycle-{index:04d}", "device": "hydraulic-rig",
             "temperature_c": aggregate(t), "vibration_mm_s": aggregate(v)}
            for index, (t, v) in enumerate(zip(temperatures, vibrations), 1)
        ]
        flagged = detect_anomalies(readings, 60.0, 4.5)
        flagged_ids = {int(row["timestamp"].split("-")[1]) - 1 for row in flagged}
        predicted = [index in flagged_ids for index in range(len(readings))]
        results["aggregation"][name] = {
            "min_temp": min(row["temperature_c"] for row in readings),
            "max_temp": max(row["temperature_c"] for row in readings),
            "min_vibration": min(row["vibration_mm_s"] for row in readings),
            "max_vibration": max(row["vibration_mm_s"] for row in readings),
            "flagged": len(flagged),
            "scores_any_component_nonoptimal": scores(predicted, labels),
            "scores_cooler_nonoptimal": scores(predicted, cooler_labels),
        }
        if name == "mean":
            adapted_path = archive_path.parent / "uci_cycle_means.csv" if archive_path.is_file() else archive_path / "uci_cycle_means.csv"
            with adapted_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(("timestamp", "device", "temperature_c", "vibration_mm_s"))
                base = datetime(2000, 1, 1)
                for index, row in enumerate(readings):
                    writer.writerow(((base + timedelta(minutes=index)).isoformat(), row["device"], row["temperature_c"], row["vibration_mm_s"]))
            # Exploratory sensitivity only; these cutoffs are chosen after seeing data.
            sensitivity = {}
            for threshold_temp, threshold_vib in ((55.0, 4.5), (60.0, 1.0), (55.0, 1.0)):
                current = detect_anomalies(readings, threshold_temp, threshold_vib)
                ids = {int(row["timestamp"].split("-")[1]) - 1 for row in current}
                predictions = [i in ids for i in range(len(readings))]
                sensitivity[f"temp_{threshold_temp:g}_vibration_{threshold_vib:g}"] = {
                    "flagged": len(current),
                    "scores_cooler_nonoptimal": scores(predictions, cooler_labels),
                }
            results["exploratory_sensitivity_mean"] = sensitivity
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
