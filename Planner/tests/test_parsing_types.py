from __future__ import annotations

import sys
import unittest
from pathlib import Path


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.aas_to_pddl_conversion.parsing import parameter_type_from_reference


class ParsingTypeInferenceTests(unittest.TestCase):
    def test_model_reference_location_element_maps_to_location_parameter(self):
        reference = {
            "type": "ModelReference",
            "keys": [
                {
                    "type": "AssetAdministrationShell",
                    "value": "https://smartproductionlab.aau.dk/aas/omronCameraSystemAAS",
                },
                {
                    "type": "Submodel",
                    "value": "Parameters",
                },
                {
                    "type": "SubmodelElementCollection",
                    "value": "Location",
                },
            ],
        }

        self.assertEqual(parameter_type_from_reference(reference), "LocationParameter")


if __name__ == "__main__":
    unittest.main()
