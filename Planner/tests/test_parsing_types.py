from __future__ import annotations

import sys
import unittest
from pathlib import Path


Planner_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Planner_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Planner.step1_aas_input.models import _ParsedSource
from Planner.step1_aas_input.parsing import parameter_type_from_reference, parse_problem


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

    def test_problem_object_explicit_parameter_type_takes_precedence(self):
        parsed = _ParsedSource(aas_id="https://example.org/aas/orderAAS", aas_name="orderAAS")
        problem = {
            "value": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "Objects",
                    "value": [
                        {
                            "modelType": "SubmodelElementCollection",
                            "idShort": "order_123",
                            "value": [
                                {
                                    "modelType": "Property",
                                    "idShort": "parameterType",
                                    "value": "Order",
                                },
                                {
                                    "modelType": "ReferenceElement",
                                    "idShort": "modelRef",
                                    "value": {
                                        "type": "ModelReference",
                                        "keys": [
                                            {
                                                "type": "AssetAdministrationShell",
                                                "value": "self",
                                            }
                                        ],
                                    },
                                },
                            ],
                        }
                    ],
                }
            ]
        }

        parse_problem(problem, parsed)

        self.assertEqual(len(parsed.objects), 1)
        self.assertEqual(parsed.objects[0]["name"], "order_123")
        self.assertEqual(parsed.objects[0]["declared_type"], "Order")
        self.assertEqual(parsed.objects[0]["reference"], "self")

    def test_problem_object_without_parameter_type_uses_reference_inference(self):
        parsed = _ParsedSource(aas_id="https://example.org/aas/test", aas_name="test")
        problem = {
            "value": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "Objects",
                    "value": [
                        {
                            "idShort": "transport_1",
                            "value": {
                                "type": "ModelReference",
                                "keys": [
                                    {
                                        "type": "AssetAdministrationShell",
                                        "value": "https://example.org/aas/planarShuttle1AAS",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ]
        }

        parse_problem(problem, parsed)

        self.assertEqual(len(parsed.objects), 1)
        self.assertEqual(parsed.objects[0]["declared_type"], "planarShuttle1AAS")

    def test_problem_object_order_self_reference_infers_order_type(self):
        parsed = _ParsedSource(aas_id="https://example.org/aas/MIM8AAS", aas_name="MIM8AAS")
        problem = {
            "value": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "Objects",
                    "value": [
                        {
                            "modelType": "SubmodelElementCollection",
                            "idShort": "order_abc123",
                            "value": [
                                {
                                    "modelType": "ReferenceElement",
                                    "idShort": "modelRef",
                                    "value": {
                                        "type": "ModelReference",
                                        "keys": [
                                            {
                                                "type": "AssetAdministrationShell",
                                                "value": "self",
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        parse_problem(problem, parsed)

        self.assertEqual(len(parsed.objects), 1)
        self.assertEqual(parsed.objects[0]["declared_type"], "Order")

    def test_problem_object_order_resolved_self_reference_infers_order_type(self):
        # AAS servers commonly resolve the literal "self" string to the
        # owning AAS id before the planner reads the submodel. The parser
        # must still treat such references as self-references for type
        # inference purposes.
        aas_id = "https://smartproductionlab.aau.dk/aas/MIM8AAS"
        parsed = _ParsedSource(aas_id=aas_id, aas_name="MIM8AAS")
        problem = {
            "value": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "Objects",
                    "value": [
                        {
                            "modelType": "ReferenceElement",
                            "displayName": [
                                {"language": "en", "text": "order_a9a71724"}
                            ],
                            "value": {
                                "type": "ModelReference",
                                "keys": [
                                    {
                                        "type": "AssetAdministrationShell",
                                        "value": aas_id,
                                    }
                                ],
                            },
                        }
                    ],
                }
            ]
        }

        parse_problem(problem, parsed)

        self.assertEqual(len(parsed.objects), 1)
        self.assertEqual(parsed.objects[0]["declared_type"], "Order")


if __name__ == "__main__":
    unittest.main()
