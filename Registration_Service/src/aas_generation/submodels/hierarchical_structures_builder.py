"""Hierarchical Structures Submodel Builder for AAS generation."""

from typing import Dict, List
from basyx.aas import model


class HierarchicalStructuresSubmodelBuilder:
    """
    Builder class for creating HierarchicalStructures submodel.
    
    The HierarchicalStructures submodel represents relationships between
    assets in a hierarchy (OneUp or OneDown archetype).
    """
    
    def __init__(self, base_url: str, semantic_factory, element_factory):
        """
        Initialize the HierarchicalStructures submodel builder.
        
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
        Create the HierarchicalStructures submodel.
        
        Simplified config format:
            HierarchicalStructures:
                Archetype: 'OneUp'  # or 'OneDown'
                IsPartOf:  # or HasPart for OneDown
                    - systemName:
                        globalAssetId: 'required-unique-id'
                        systemId: 'optional-config-key'  # defaults to systemName + 'AAS'
        
        Auto-derives:
            - aasId from systemName
            - submodelId from systemId (defaults to systemName + 'AAS')
        
        Args:
            system_id: Unique identifier for the system
            config: Configuration dictionary containing HierarchicalStructures section
            
        Returns:
            HierarchicalStructures submodel instance
        """
        hs_config = config.get('HierarchicalStructures', {}) or {}
        archetype = hs_config.get('Archetype', 'OneUp')
        global_asset_id = config.get('globalAssetId', f"{self.base_url}/assets/{system_id}")
        
        # Create ArcheType property
        archetype_property = self._create_archetype_property(archetype)
        
        # Create EntryNode with relationships
        entry_node = self._create_entry_node(system_id, global_asset_id, hs_config, archetype)
        
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/HierarchicalStructures",
            id_short="HierarchicalStructures",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=self.semantic_factory.HIERARCHICAL_STRUCTURES,
            administration=model.AdministrativeInformation(version="1", revision="1"),
            submodel_element=[archetype_property, entry_node]
        )
        
        return submodel
    
    def _create_archetype_property(self, archetype: str) -> model.Property:
        """Create the ArcheType property."""
        return self.element_factory.create_property(
            id_short="ArcheType",
            value=archetype,
            value_type=model.datatypes.String,
            semantic_id=self.semantic_factory.HIERARCHICAL_ARCHETYPE
        )
    
    def _create_entry_node(self, system_id: str, global_asset_id: str,
                          hs_config: Dict, archetype: str) -> model.Entity:
        """Create the EntryNode entity with Node children and relationships."""
        node_entities = []
        entry_node_statements = []
        
        # Handle both IsPartOf and HasPart
        is_part_of = hs_config.get('IsPartOf', [])
        has_part = hs_config.get('HasPart', [])
        
        # Determine which statements to process based on archetype
        statements_to_process = []
        relationship_prefix = ""
        
        if archetype == 'OneUp':
            statements_to_process = is_part_of
            relationship_prefix = "IsPartOf"
        elif archetype == 'OneDown':
            statements_to_process = has_part
            relationship_prefix = "HasPart"
        
        # Process each entity in the hierarchy
        for entity_item in statements_to_process:
            # Support both string format (just system name) and dict format (with details)
            if isinstance(entity_item, str):
                entity_name = entity_item
                entity_config = {}
            elif isinstance(entity_item, dict):
                entity_name = list(entity_item.keys())[0]
                entity_config = entity_item[entity_name] or {}
            else:
                continue
            
            # Auto-derive missing IDs
            entity_system_id = entity_config.get('systemId', f"{entity_name}AAS")
            entity_submodel_id = entity_config.get(
                'submodelId',
                f"{self.base_url}/submodels/instances/{entity_system_id}/HierarchicalStructures"
            )
            entity_global_asset_id = entity_config.get('globalAssetId', '')
            
            # Create Node entity with SameAs reference
            node_entity = self._create_node_entity(
                entity_name, entity_global_asset_id, entity_submodel_id
            )
            node_entities.append(node_entity)
            
            # Create relationship element
            relationship = self._create_relationship(
                system_id, entity_name, relationship_prefix
            )
            entry_node_statements.append(relationship)
        
        # Add all Node entities to EntryNode statements
        entry_node_statements.extend(node_entities)
        
        entry_node = model.Entity(
            id_short="EntryNode",
            entity_type=model.EntityType.SELF_MANAGED_ENTITY,
            global_asset_id=global_asset_id,
            semantic_id=self.semantic_factory.ENTRY_NODE,
            statement=entry_node_statements if entry_node_statements else []
        )
        
        return entry_node
    
    def _create_node_entity(self, entity_name: str, global_asset_id: str,
                           submodel_id: str) -> model.Entity:
        """Create a Node entity with optional SameAs reference."""
        node_statements = []
        
        # Create SameAs reference if submodel ID is provided
        if submodel_id:
            same_as = self.element_factory.create_reference_element(
                id_short="SameAs",
                reference=model.ModelReference(
                    (
                        model.Key(
                            type_=model.KeyTypes.SUBMODEL,
                            value=submodel_id
                        ),
                        model.Key(
                            type_=model.KeyTypes.ENTITY,
                            value="EntryNode"
                        )
                    ),
                    model.Entity
                ),
                semantic_id=self.semantic_factory.HIERARCHICAL_SAME_AS,
                supplemental_semantic_ids=[
                    self.semantic_factory.ENTRY_NODE
                ]
            )
            node_statements.append(same_as)
        
        # SELF_MANAGED requires globalAssetId, CO_MANAGED doesn't
        is_self_managed = bool(global_asset_id)
        
        return self.element_factory.create_entity(
            id_short=entity_name,
            entity_type=model.EntityType.SELF_MANAGED_ENTITY if is_self_managed else model.EntityType.CO_MANAGED_ENTITY,
            global_asset_id=global_asset_id if global_asset_id else None,
            statements=node_statements if node_statements else None,
            semantic_id=self.semantic_factory.HIERARCHICAL_NODE
        )
    
    def _create_relationship(self, system_id: str, entity_name: str,
                            relationship_prefix: str) -> model.RelationshipElement:
        """Create a relationship element between EntryNode and a child Node."""
        return self.element_factory.create_relationship(
            id_short=f"{relationship_prefix}_{entity_name}",
            first=model.ModelReference(
                (
                    model.Key(
                        type_=model.KeyTypes.SUBMODEL,
                        value=f"{self.base_url}/submodels/instances/{system_id}/HierarchicalStructures"
                    ),
                    model.Key(
                        type_=model.KeyTypes.ENTITY,
                        value="EntryNode"
                    )
                ),
                model.Entity
            ),
            second=model.ModelReference(
                (
                    model.Key(
                        type_=model.KeyTypes.SUBMODEL,
                        value=f"{self.base_url}/submodels/instances/{system_id}/HierarchicalStructures"
                    ),
                    model.Key(
                        type_=model.KeyTypes.ENTITY,
                        value="EntryNode"
                    ),
                    model.Key(
                        type_=model.KeyTypes.ENTITY,
                        value=entity_name
                    )
                ),
                model.Entity
            ),
            semantic_id=self.semantic_factory.HIERARCHICAL_RELATIONSHIP
        )
