"""Asset Interfaces Description Submodel Builder for AAS generation."""

from typing import Dict, List, Optional
from basyx.aas import model


class AssetInterfacesBuilder:
    """
    Builder class for creating AssetInterfacesDescription submodel.

    This submodel describes the communication interfaces of an asset,
    primarily MQTT-based interfaces following W3C Thing Description patterns.
    """

    def __init__(self, base_url: str, semantic_factory, element_factory):
        """
        Initialize the AssetInterfacesDescription submodel builder.

        Args:
            base_url: Base URL for AAS identifiers
            semantic_factory: SemanticIdFactory instance for semantic IDs
            element_factory: AASElementFactory instance for element creation
        """
        self.base_url = base_url
        self.semantic_factory = semantic_factory
        self.element_factory = element_factory

    def build(self, system_id: str, config: Dict) -> model.Submodel:
        """
        Create the AssetInterfacesDescription submodel.

        Args:
            system_id: Unique identifier for the system
            config: Configuration dictionary

        Returns:
            AssetInterfacesDescription submodel
        """
        interface_config = config.get('AssetInterfacesDescription', {}) or {}
        mqtt_config = interface_config.get('InterfaceMQTT', {}) or {}

        # Create MQTT interface collection
        interface_elements = []

        # Title (lowercase to match W3C Thing Description)
        title = mqtt_config.get('Title', system_id)
        interface_elements.append(
            self.element_factory.create_property(
                id_short="title",
                value=title,
                value_type=model.datatypes.String
            )
        )

        # Add EndpointMetadata collection with MQTT topics
        endpoint_metadata = self._create_mqtt_endpoint_metadata(mqtt_config)
        if endpoint_metadata:
            interface_elements.append(endpoint_metadata)

        # Create InteractionMetadata collection with actions and properties nested
        interaction_metadata = mqtt_config.get('InteractionMetadata', {})
        interaction_elements = []

        actions = interaction_metadata.get('actions', [])
        if actions:
            actions_collection = self._create_actions_from_interaction_metadata(
                actions)
            if actions_collection:
                interaction_elements.append(actions_collection)

        properties = interaction_metadata.get('properties', [])
        if properties:
            properties_collection = self._create_properties_from_interaction_metadata(
                properties)
            if properties_collection:
                interaction_elements.append(properties_collection)

        # Wrap in InteractionMetadata collection if we have content
        if interaction_elements:
            interaction_metadata_collection = self.element_factory.create_collection(
                id_short="InteractionMetadata",
                elements=interaction_elements,
                semantic_id=self.semantic_factory.INTERACTION_METADATA,
                supplemental_semantic_ids=[
                    self.semantic_factory.WOT_INTERACTION_AFFORDANCE
                ]
            )
            interface_elements.append(interaction_metadata_collection)

        interface_mqtt = self.element_factory.create_collection(
            id_short="InterfaceMQTT",
            elements=interface_elements,
            semantic_id=self.semantic_factory.INTERFACE,
            supplemental_semantic_ids=[
                self.semantic_factory.MQTT_PROTOCOL,
                self.semantic_factory.WOT_THING_DESCRIPTION
            ]
        )

        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/AssetInterfacesDescription",
            id_short="AssetInterfacesDescription",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=self.semantic_factory.ASSET_INTERFACES_DESCRIPTION,
            administration=model.AdministrativeInformation(
                version="1", revision="0"),
            submodel_element=[interface_mqtt]
        )

        return submodel

    def _create_mqtt_endpoint_metadata(self, mqtt_config: Dict) -> Optional[model.SubmodelElementCollection]:
        """
        Create the EndpointMetadata collection for MQTT topics.

        Args:
            mqtt_config: MQTT configuration dictionary

        Returns:
            EndpointMetadata SubmodelElementCollection or None
        """
        endpoint_config = mqtt_config.get('EndpointMetadata', {})
        if not endpoint_config:
            return None

        endpoint_elements = []

        # Base endpoint
        if 'base' in endpoint_config:
            endpoint_elements.append(
                self.element_factory.create_property(
                    id_short="base",
                    value=endpoint_config['base'],
                    value_type=model.datatypes.String
                )
            )

        # Content type
        if 'contentType' in endpoint_config:
            endpoint_elements.append(
                self.element_factory.create_property(
                    id_short="contentType",
                    value=endpoint_config['contentType'],
                    value_type=model.datatypes.String
                )
            )

        if not endpoint_elements:
            return None

        return self.element_factory.create_collection(
            id_short="EndpointMetadata",
            elements=endpoint_elements
        )

    def _create_actions_from_interaction_metadata(self, actions: Dict) -> Optional[model.SubmodelElementCollection]:
        """
        Create Actions collection from interaction metadata.

        Args:
            actions: Dictionary of action name -> action config

        Returns:
            Actions SubmodelElementCollection or None
        """
        if not actions:
            return None

        action_elements = []

        # Actions is a dict with action names as keys
        for action_name, action_config in actions.items():

            action_props = []

            # Key/Title
            if 'key' in action_config:
                action_props.append(
                    self.element_factory.create_property(
                        id_short="Key",
                        value=action_config['key'],
                        value_type=model.datatypes.String
                    )
                )

            if 'title' in action_config:
                action_props.append(
                    self.element_factory.create_property(
                        id_short="Title",
                        value=action_config['title'],
                        value_type=model.datatypes.String
                    )
                )

            # Synchronous flag
            if 'synchronous' in action_config:
                sync_value = str(
                    action_config['synchronous']).lower() == 'true'
                action_props.append(
                    self.element_factory.create_property(
                        id_short="Synchronous",
                        value=sync_value,
                        value_type=model.datatypes.Boolean
                    )
                )

            # Input/Output schemas
            if 'input' in action_config:
                action_props.append(
                    self.element_factory.create_file(
                        id_short="input",
                        value=action_config['input'],
                        content_type="application/schema+json"
                    )
                )

            if 'output' in action_config:
                action_props.append(
                    self.element_factory.create_file(
                        id_short="output",
                        value=action_config['output'],
                        content_type="application/schema+json"
                    )
                )

            # Forms
            if 'forms' in action_config:
                forms_config = action_config['forms']
                form_elements = []

                for key, value in forms_config.items():
                    if key == 'response' and isinstance(value, dict):
                        # Response is a nested structure
                        response_elements = []
                        for resp_key, resp_value in value.items():
                            response_elements.append(
                                self.element_factory.create_property(
                                    id_short=resp_key,
                                    value=str(resp_value),
                                    value_type=model.datatypes.String
                                )
                            )
                        form_elements.append(
                            self.element_factory.create_collection(
                                id_short="response",
                                elements=response_elements
                            )
                        )
                    else:
                        form_elements.append(
                            self.element_factory.create_property(
                                id_short=key,
                                value=str(value),
                                value_type=model.datatypes.String
                            )
                        )

                if form_elements:
                    action_props.append(
                        self.element_factory.create_collection(
                            id_short="Forms",
                            elements=form_elements
                        )
                    )

            action_element = self.element_factory.create_collection(
                id_short=action_name,
                elements=action_props
            )
            action_elements.append(action_element)

        if not action_elements:
            return None

        return self.element_factory.create_collection(
            id_short="actions",
            elements=action_elements,
            semantic_id=self.semantic_factory.WOT_ACTION_AFFORDANCE
        )

    def _create_properties_from_interaction_metadata(self, properties: Dict) -> Optional[model.SubmodelElementCollection]:
        """
        Create Properties collection from interaction metadata.

        Args:
            properties: Dictionary of property name -> property config

        Returns:
            Properties SubmodelElementCollection or None
        """
        if not properties:
            return None

        property_elements = []

        # Properties is a dict with property names as keys
        for prop_name, prop_config in properties.items():

            prop_elements = []

            # Key/Title
            if 'key' in prop_config:
                prop_elements.append(
                    self.element_factory.create_property(
                        id_short="Key",
                        value=prop_config['key'],
                        value_type=model.datatypes.String
                    )
                )

            if 'title' in prop_config:
                prop_elements.append(
                    self.element_factory.create_property(
                        id_short="Title",
                        value=prop_config['title'],
                        value_type=model.datatypes.String
                    )
                )

            # Output schema
            if 'output' in prop_config:
                prop_elements.append(
                    self.element_factory.create_file(
                        id_short="output",
                        value=prop_config['output'],
                        content_type="application/schema+json"
                    )
                )

            # Forms
            if 'forms' in prop_config:
                forms_config = prop_config['forms']
                form_elements = []

                for key, value in forms_config.items():
                    form_elements.append(
                        self.element_factory.create_property(
                            id_short=key,
                            value=str(value),
                            value_type=model.datatypes.String
                        )
                    )

                if form_elements:
                    prop_elements.append(
                        self.element_factory.create_collection(
                            id_short="Forms",
                            elements=form_elements
                        )
                    )

            property_element = self.element_factory.create_collection(
                id_short=prop_name,
                elements=prop_elements
            )
            property_elements.append(property_element)

        if not property_elements:
            return None

        return self.element_factory.create_collection(
            id_short="properties",
            elements=property_elements,
            semantic_id=self.semantic_factory.WOT_PROPERTY_AFFORDANCE
        )
