"""AssetInterfacesBuilderV2 — overrides v1 to attach the missing semanticId on
EndpointMetadata.

All other elements get their semanticIds from v1 + the SemanticIdFactoryV2
overrides automatically.
"""
from __future__ import annotations

from typing import Dict, Optional

from basyx.aas import model

from generation.AAS_generation.submodels.asset_interfaces_builder import (
    AssetInterfacesBuilder,
)


class AssetInterfacesBuilderV2(AssetInterfacesBuilder):
    def _create_mqtt_endpoint_metadata(
        self, mqtt_config: Dict
    ) -> Optional[model.SubmodelElementCollection]:
        endpoint_config = mqtt_config.get("EndpointMetadata", {})
        if not endpoint_config:
            return None

        endpoint_elements = []
        if "base" in endpoint_config:
            endpoint_elements.append(
                self.element_factory.create_property(
                    id_short="base",
                    value=endpoint_config["base"],
                    value_type=model.datatypes.String,
                )
            )
        if "contentType" in endpoint_config:
            endpoint_elements.append(
                self.element_factory.create_property(
                    id_short="contentType",
                    value=endpoint_config["contentType"],
                    value_type=model.datatypes.String,
                )
            )

        if not endpoint_elements:
            return None

        return self.element_factory.create_collection(
            id_short="EndpointMetadata",
            elements=endpoint_elements,
            semantic_id=self.semantic_factory.AID_ENDPOINT_METADATA,
        )
