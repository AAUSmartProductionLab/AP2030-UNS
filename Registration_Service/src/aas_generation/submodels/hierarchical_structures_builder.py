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
                IsPartOf:  # or HasPart for OneDown - dict format
                    systemName:
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
        aas_id = config.get('id', f"{self.base_url}/aas/{system_id}")
        entry_node = self._create_entry_node(system_id, global_asset_id, hs_config, archetype, aas_id)
        
        # Create display name as LangStringSet
        display_name_value = hs_config.get('Name', 'HierarchicalStructures')
        if isinstance(display_name_value, str):
            display_name = model.LangStringSet({"en": display_name_value})
        else:
            display_name = display_name_value
        
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/HierarchicalStructures",
            id_short="HierarchicalStructures",
            display_name=display_name,
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
                          hs_config: Dict, archetype: str, aas_id: str) -> model.Entity:
        """Create the EntryNode entity with Node children and relationships.
        
        Supports two config formats:
        1. Dict format (Resource AAS): IsPartOf/HasPart: {entityName: {globalAssetId: ...}}
        2. Nodes/Relationships format (Product AAS): Nodes: [{idShort:, entityType:, ...}], Relationships: [{first:, second:}]
        """
        entry_node_statements = []
        
        # Check for Nodes/Relationships format first (Product AAS style)
        nodes_list = hs_config.get('Nodes', None)
        relationships_list = hs_config.get('Relationships', None)
        entry_node_name = hs_config.get('entryNode', None)
        
        if isinstance(nodes_list, list) and nodes_list:
            entry_node_statements = self._build_from_nodes_relationships(
                system_id, nodes_list, relationships_list or [], entry_node_name, archetype
            )
        else:
            # Legacy dict format (Resource AAS)
            entry_node_statements = self._build_from_dict_format(
                system_id, hs_config, archetype, aas_id
            )
        
        entry_node = model.Entity(
            id_short="EntryNode",
            entity_type=model.EntityType.SELF_MANAGED_ENTITY,
            global_asset_id=global_asset_id,
            semantic_id=self.semantic_factory.ENTRY_NODE,
            statement=entry_node_statements if entry_node_statements else []
        )
        
        return entry_node
    
    def _build_from_nodes_relationships(
        self, system_id: str, nodes_list: list, relationships_list: list,
        entry_node_name: str, archetype: str
    ) -> list:
        """Build statements from Nodes/Relationships list format (Product AAS)."""
        statements = []
        submodel_id = f"{self.base_url}/submodels/instances/{system_id}/HierarchicalStructures"
        
        # Create child Node entities (skip the entry node itself)
        for node_cfg in nodes_list:
            if not isinstance(node_cfg, dict):
                continue
            id_short = node_cfg.get('idShort', '')
            if not id_short or id_short == entry_node_name:
                continue
            
            entity_type_str = node_cfg.get('entityType', 'CoManagedEntity')
            is_self_managed = entity_type_str == 'SelfManagedEntity'
            node_global_asset_id = node_cfg.get('globalAssetId', None)
            
            node_entity = self.element_factory.create_entity(
                id_short=id_short,
                entity_type=model.EntityType.SELF_MANAGED_ENTITY if is_self_managed else model.EntityType.CO_MANAGED_ENTITY,
                global_asset_id=node_global_asset_id if is_self_managed else None,
                semantic_id=self.semantic_factory.HIERARCHICAL_NODE
            )
            statements.append(node_entity)
        
        # Create Relationship elements
        relationship_prefix = "HasPart" if archetype == 'OneDown' else "IsPartOf"
        for rel_cfg in relationships_list:
            if not isinstance(rel_cfg, dict):
                continue
            rel_id_short = rel_cfg.get('idShort', '')
            first_name = rel_cfg.get('first', '')
            second_name = rel_cfg.get('second', '')
            if not first_name or not second_name:
                continue
            
            # First entity reference
            first_keys = [model.Key(model.KeyTypes.SUBMODEL, submodel_id)]
            if first_name == entry_node_name:
                first_keys.append(model.Key(model.KeyTypes.ENTITY, "EntryNode"))
            else:
                first_keys.append(model.Key(model.KeyTypes.ENTITY, "EntryNode"))
                first_keys.append(model.Key(model.KeyTypes.ENTITY, first_name))
            
            # Second entity reference
            second_keys = [model.Key(model.KeyTypes.SUBMODEL, submodel_id)]
            if second_name == entry_node_name:
                second_keys.append(model.Key(model.KeyTypes.ENTITY, "EntryNode"))
            else:
                second_keys.append(model.Key(model.KeyTypes.ENTITY, "EntryNode"))
                second_keys.append(model.Key(model.KeyTypes.ENTITY, second_name))
            
            sem = rel_cfg.get('semanticId')
            sem_ref = self.semantic_factory.HIERARCHICAL_RELATIONSHIP
            if sem:
                sem_ref = model.ExternalReference(
                    (model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE, value=sem),)
                )
            
            rel = self.element_factory.create_relationship(
                id_short=rel_id_short or f"{relationship_prefix}_{second_name}",
                first=model.ModelReference(tuple(first_keys), model.Entity),
                second=model.ModelReference(tuple(second_keys), model.Entity),
                semantic_id=sem_ref
            )
            statements.append(rel)
        
        return statements
    
    def _build_from_dict_format(
        self, system_id: str, hs_config: Dict, archetype: str, aas_id: str
    ) -> list:
        """Build statements from IsPartOf/HasPart dict format (Resource AAS)."""
        node_entities = []
        entry_node_statements = []
        
        # Handle both IsPartOf and HasPart (now as dicts)
        is_part_of = hs_config.get('IsPartOf', {})
        has_part = hs_config.get('HasPart', {})
        
        # Determine which statements to process based on archetype
        statements_to_process = {}
        relationship_prefix = ""
        
        if archetype == 'OneUp':
            statements_to_process = is_part_of if isinstance(is_part_of, dict) else {}
            relationship_prefix = "IsPartOf"
        elif archetype == 'OneDown':
            statements_to_process = has_part if isinstance(has_part, dict) else {}
            relationship_prefix = "HasPart"
        
        # Process each entity in the hierarchy (dict format)
        for entity_name, entity_config in statements_to_process.items():
            if not isinstance(entity_config, dict):
                entity_config = {}
            
            entity_system_id = entity_config.get('systemId', entity_name)
            if not entity_system_id.endswith('AAS'):
                entity_system_id_for_submodel = entity_system_id + 'AAS'
            else:
                entity_system_id_for_submodel = entity_system_id
                
            entity_aas_id = entity_config.get(
                'aasId',
                f"{self.base_url}/aas/{entity_system_id}"
            )
            entity_submodel_id = entity_config.get(
                'submodelId',
                f"{self.base_url}/submodels/instances/{entity_system_id_for_submodel}/HierarchicalStructures"
            )
            entity_global_asset_id = entity_config.get('globalAssetId', '')
            
            node_entity = self._create_node_entity(
                entity_name, entity_global_asset_id, entity_submodel_id, entity_aas_id
            )
            node_entities.append(node_entity)
            
            relationship = self._create_relationship(
                system_id, entity_name, relationship_prefix, aas_id
            )
            entry_node_statements.append(relationship)
        
        entry_node_statements.extend(node_entities)
        return entry_node_statements
    
    def _create_node_entity(self, entity_name: str, global_asset_id: str,
                           submodel_id: str, aas_id: str = None) -> model.Entity:
        """Create a Node entity with optional SameAs reference.
        
        Args:
            entity_name: Name/idShort for the entity
            global_asset_id: Global asset ID for the entity
            submodel_id: Target HierarchicalStructures submodel ID
            aas_id: Unused, kept for API compatibility
        """
        node_statements = []
        
        # Create SameAs reference if submodel ID is provided
        # AASd-125 compliant: First key is AasIdentifiable (SUBMODEL),
        # subsequent keys are FragmentKeys (ENTITY)
        if submodel_id:
            same_as_reference = model.ModelReference(
                (
                    model.Key(model.KeyTypes.SUBMODEL, submodel_id),
                    model.Key(model.KeyTypes.ENTITY, "EntryNode")
                ),
                model.Entity
            )
            same_as = self.element_factory.create_reference_element(
                id_short="SameAs",
                reference=same_as_reference,
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
                            relationship_prefix: str, aas_id: str = None) -> model.RelationshipElement:
        """Create a relationship element between EntryNode and a child Node.
        
        Args:
            system_id: System ID for deriving submodel path
            entity_name: Name of the child entity
            relationship_prefix: 'IsPartOf' or 'HasPart'
            aas_id: Unused, kept for API compatibility
        """
        # AASd-125 compliant: First key is AasIdentifiable (SUBMODEL),
        # subsequent keys are FragmentKeys (ENTITY)
        submodel_id = f"{self.base_url}/submodels/instances/{system_id}/HierarchicalStructures"
        
        return self.element_factory.create_relationship(
            id_short=f"{relationship_prefix}_{entity_name}",
            first=model.ModelReference(
                (
                    model.Key(model.KeyTypes.SUBMODEL, submodel_id),
                    model.Key(model.KeyTypes.ENTITY, "EntryNode")
                ),
                model.Entity
            ),
            second=model.ModelReference(
                (
                    model.Key(model.KeyTypes.SUBMODEL, submodel_id),
                    model.Key(model.KeyTypes.ENTITY, "EntryNode"),
                    model.Key(model.KeyTypes.ENTITY, entity_name)
                ),
                model.Entity
            ),
            semantic_id=self.semantic_factory.HIERARCHICAL_RELATIONSHIP
        )
