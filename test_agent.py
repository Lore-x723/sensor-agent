import tempfile
import unittest
from pathlib import Path

from agent import detect_anomalies, load_readings, make_checklist


class AgentTests(unittest.TestCase):
    def test_sample_finds_two_anomalies(self):
        rows = load_readings(Path(__file__).with_name("sample_data.csv"))
        anomalies = detect_anomalies(rows, 60, 4.5)
        self.assertEqual(2, len(anomalies))
        self.assertEqual({"motor-02"}, {item["device"] for item in anomalies})
        self.assertEqual(2, len(make_checklist(anomalies)))

    def test_invalid_value_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("timestamp,device,temperature_c,vibration_mm_s\n2026-10-19T09:00:00,motor,NaN,2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_readings(path)


if __name__ == "__main__":
    unittest.main()
