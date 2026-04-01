from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.bt_synthesis.artifacts import generate_bt_filename, save_bt_xml


class BTArtifactsTests(unittest.TestCase):
    def test_generate_bt_filename_prefers_aas_id_tail(self):
        filename = generate_bt_filename(
            {
                "id": "https://example/aas/Product_A-1/",
                "idShort": "ignored",
            }
        )
        self.assertEqual(filename, "production_Product_A-1.xml")

    def test_generate_bt_filename_falls_back_to_id_short(self):
        filename = generate_bt_filename({"idShort": "My Product@42"})
        self.assertEqual(filename, "production_MyProduct42.xml")

    def test_save_bt_xml_persists_content(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "nested" / "bt.xml"
            save_bt_xml("<root BTCPP_format=\"4\" />", str(output))
            self.assertTrue(output.exists())
            self.assertIn("BTCPP_format", output.read_text())


if __name__ == "__main__":
    unittest.main()
