"""Digital Nameplate Submodel Builder for AAS generation."""

from typing import Dict
from basyx.aas import model


class DigitalNameplateSubmodelBuilder:
    """Builder class for creating DigitalNameplate submodel."""

    def __init__(self, base_url: str, semantic_factory, element_factory):
        self.base_url = base_url
        self.semantic_factory = semantic_factory
        self.element_factory = element_factory

    def build(self, system_id: str, config: Dict) -> model.Submodel:
        """Create the DigitalNameplate submodel.

        Accepts either:
        - explicit `DigitalNameplate` section, or
        - top-level metadata fallbacks (serialNumber, manufacturerName, etc.).
        """
        nameplate_config = config.get(
            'DigitalNameplate', {}) or config.get('Nameplate', {}) or {}
        elements = []

        uri_of_product = nameplate_config.get(
            'URIOfTheProduct',
            f"{self.base_url}/assets/{system_id}"
        )
        elements.append(
            self.element_factory.create_property(
                id_short="URIOfTheProduct",
                value=uri_of_product,
                value_type=model.datatypes.String
            )
        )

        manufacturer_name = nameplate_config.get(
            'ManufacturerName', config.get('manufacturerName', 'Unknown Manufacturer'))
        elements.append(
            self.element_factory.create_multi_language_property(
                id_short="ManufacturerName",
                text=manufacturer_name
            )
        )

        optional_string_fields = {
            'ManufacturerProductDesignation': nameplate_config.get('ManufacturerProductDesignation', config.get('manufacturerProductDesignation', config.get('idShort', system_id))),
            'ManufacturerProductFamily': nameplate_config.get('ManufacturerProductFamily', config.get('manufacturerProductFamily')),
            'ManufacturerArticleNumber': nameplate_config.get('ManufacturerArticleNumber', config.get('manufacturerArticleNumber')),
            'SerialNumber': nameplate_config.get('SerialNumber', config.get('serialNumber')),
            'YearOfConstruction': nameplate_config.get('YearOfConstruction', config.get('yearOfConstruction')),
            'DateOfManufacture': nameplate_config.get('DateOfManufacture', config.get('dateOfManufacture')),
            'HardwareVersion': nameplate_config.get('HardwareVersion', config.get('hardwareVersion')),
            'SoftwareVersion': nameplate_config.get('SoftwareVersion', config.get('softwareVersion')),
            'CountryOfOrigin': nameplate_config.get('CountryOfOrigin', config.get('countryOfOrigin')),
        }

        for field_name, field_value in optional_string_fields.items():
            if field_value in (None, ""):
                continue
            elements.append(
                self.element_factory.create_property(
                    id_short=field_name,
                    value=str(field_value),
                    value_type=model.datatypes.String
                )
            )

        return model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/Nameplate",
            id_short="DigitalNameplate",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=self.semantic_factory.DIGITAL_NAMEPLATE_SUBMODEL,
            administration=model.AdministrativeInformation(
                version="1", revision="0"),
            submodel_element=elements
        )
