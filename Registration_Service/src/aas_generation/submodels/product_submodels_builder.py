"""Product AAS Submodel Builders.

Builders for ProductInformation and BatchInformation submodels,
which are specific to Product AAS configurations.
"""

from typing import Dict, Any
from basyx.aas import model

from ..semantic_ids import SemanticIdCatalog


class ProductInformationSubmodelBuilder:
    """
    Builder for the ProductInformation submodel.

    Config format:
        ProductInformation:
            ProductName: 'Human Growth Hormone (Somatropin)'
            ProductFamily: 'Growth Hormones'
            ProductCode: 'HGH-001'
            Description: 'Recombinant human growth hormone for injection'
    """

    SEMANTIC_ID = f"{SemanticIdCatalog.CSSX_BASE}ProductInformationSubmodel"

    def __init__(self, base_url: str):
        self.base_url = base_url

    def build(self, system_id: str, config: Dict) -> model.Submodel:
        pi_config = config.get('ProductInformation', {}) or {}
        if not pi_config:
            return None

        elements = []
        for key, value in pi_config.items():
            if key == 'semanticId':
                continue
            elements.append(
                model.Property(
                    id_short=key,
                    value_type=model.datatypes.String,
                    value=str(value)
                )
            )

        semantic_id_value = pi_config.get('semanticId', self.SEMANTIC_ID)

        return model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/ProductInformation",
            id_short="ProductInformation",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=model.ExternalReference(
                (model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE, value=semantic_id_value),)
            ),
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=elements
        )


class BatchInformationSubmodelBuilder:
    """
    Builder for the BatchInformation submodel.

    Config format:
        BatchInformation:
            OrderNumber: 'UUID'
            OrderTimestamp: '2026-01-20T10:00:00.000Z'
            Quantity: 40000
            Unit: 'units'
            Packaging: 'Prefilled Syringe (2.5mL)'
            Status: 'planned'
    """

    SEMANTIC_ID = f"{SemanticIdCatalog.CSSX_BASE}BatchInformationSubmodel"

    def __init__(self, base_url: str):
        self.base_url = base_url

    def build(self, system_id: str, config: Dict) -> model.Submodel:
        bi_config = config.get('BatchInformation', {}) or {}
        if not bi_config:
            return None

        elements = []
        for key, value in bi_config.items():
            if key == 'semanticId':
                continue
            if isinstance(value, int):
                elements.append(
                    model.Property(
                        id_short=key,
                        value_type=model.datatypes.Int,
                        value=value
                    )
                )
            elif isinstance(value, float):
                elements.append(
                    model.Property(
                        id_short=key,
                        value_type=model.datatypes.Float,
                        value=value
                    )
                )
            else:
                elements.append(
                    model.Property(
                        id_short=key,
                        value_type=model.datatypes.String,
                        value=str(value)
                    )
                )

        semantic_id_value = bi_config.get('semanticId', self.SEMANTIC_ID)

        return model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/BatchInformation",
            id_short="BatchInformation",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=model.ExternalReference(
                (model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE, value=semantic_id_value),)
            ),
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=elements
        )
