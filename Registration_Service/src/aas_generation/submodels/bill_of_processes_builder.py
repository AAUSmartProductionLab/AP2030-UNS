"""Bill of Processes Submodel Builder for AAS generation.

This builder creates the BillOfProcesses submodel for Product AAS,
which defines the ordered sequence of production steps with their
semantic IDs for capability matching.
"""

from typing import Dict, List, Any, Optional
from basyx.aas import model

from ..semantic_ids import SemanticIdCatalog


class BillOfProcessesSubmodelBuilder:
    """
    Builder class for creating BillOfProcesses submodel.
    
    The BillOfProcesses submodel represents the ordered sequence of
    production steps required to manufacture a product. Each step
    has a semantic ID that can be matched to resource capabilities.
    """
    
    # Semantic IDs
    BILL_OF_PROCESSES_SEMANTIC_ID = SemanticIdCatalog.BILL_OF_PROCESSES_SUBMODEL
    PROCESS_STEP_SEMANTIC_ID = SemanticIdCatalog.PROCESS_STEP_SUBMODEL
    
    # CSSx capability IRI prefix
    CSSX_BASE = "http://www.w3id.org/aau-ra/cssx#"
    
    def __init__(self, base_url: str, semantic_factory, element_factory):
        self.base_url = base_url
        self.semantic_factory = semantic_factory
        self.element_factory = element_factory
    
    def build(self, system_id: str, config: Dict) -> Optional[model.Submodel]:
        """
        Create the BillOfProcesses submodel.
        
        Process steps are direct children of the submodel (no Processes wrapper).
        Each step has id_short='Step_N', a displayName with the capability name,
        and a semanticId referencing the CSSx capability class IRI.
        
        Config format:
            BillOfProcesses:
                Processes:
                    - idShort: 'Loading'
                      semanticId: 'cssx:Loading'
                      sequenceNumber: 1
                      ...
        """
        bop_config = config.get('BillOfProcesses', {}) or {}
        if not bop_config:
            return None

        processes = bop_config.get('Processes', [])
        
        # Create process step elements as direct submodel children
        process_elements = []
        for process_entry in processes:
            if isinstance(process_entry, dict):
                process_name = process_entry.get('idShort', '')
                if process_name:
                    step_element = self._create_process_step(
                        process_name, process_entry
                    )
                    process_elements.append(step_element)
        
        if not process_elements:
            return None
        
        # Create submodel semantic ID
        semantic_id_value = bop_config.get(
            'semanticId', bop_config.get('semantic_id', self.BILL_OF_PROCESSES_SEMANTIC_ID))
        
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/BillOfProcesses",
            id_short="BillOfProcesses",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=self._create_semantic_reference(semantic_id_value),
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=process_elements
        )
        
        return submodel
    
    def _create_process_step(
        self, 
        process_name: str, 
        process_config: Dict
    ) -> model.SubmodelElementCollection:
        """
        Create a process step as a SubmodelElementCollection.
        
        id_short is Step_N (from sequenceNumber). displayName carries the
        human-readable name. semanticId is the CSSx capability class IRI.
        """
        elements = []
        
        # Step/sequence number
        step_num = process_config.get('sequenceNumber', process_config.get('step', 0))
        
        # Resolve semantic ID — expand cssx: prefix if present
        raw_sem_id = process_config.get('semanticId', process_config.get('semantic_id', ''))
        semantic_id = self._resolve_capability_iri(raw_sem_id)
        
        # Description
        description = process_config.get('description', '')
        if description:
            elements.append(
                model.Property(
                    id_short="Description",
                    value_type=model.datatypes.String,
                    value=description
                )
            )
        
        # Estimated duration (support both flat float and nested dict {value:, unit:})
        duration_cfg = process_config.get('estimatedDuration', None)
        if duration_cfg is not None:
            if isinstance(duration_cfg, dict):
                dur_value = duration_cfg.get('value', 0.0)
                dur_unit = duration_cfg.get('unit', 's')
                elements.append(
                    model.SubmodelElementCollection(
                        id_short="EstimatedDuration",
                        value=[
                            model.Property(
                                id_short="Value",
                                value_type=model.datatypes.Float,
                                value=float(dur_value)
                            ),
                            model.Property(
                                id_short="Unit",
                                value_type=model.datatypes.String,
                                value=dur_unit
                            ),
                        ]
                    )
                )
            else:
                elements.append(
                    model.Property(
                        id_short="EstimatedDuration",
                        value_type=model.datatypes.Float,
                        value=float(duration_cfg)
                    )
                )
        
        # Parameters (list-of-dict or dict)
        parameters = process_config.get('parameters', None)
        if parameters:
            param_elements = self._create_parameter_elements(parameters)
            if param_elements:
                elements.append(
                    model.SubmodelElementCollection(
                        id_short="Parameters",
                        value=param_elements
                    )
                )

        # Requirements (list-of-dict)
        requirements = process_config.get('requirements', None)
        if requirements:
            req_elements = self._create_parameter_elements(requirements)
            if req_elements:
                elements.append(
                    model.SubmodelElementCollection(
                        id_short="Requirements",
                        value=req_elements
                    )
                )
        
        # Build semantic reference from the capability IRI
        collection_semantic_id = self._create_semantic_reference(semantic_id) if semantic_id else None
        
        return model.SubmodelElementCollection(
            id_short=f"Step_{step_num}",
            display_name=model.MultiLanguageNameType({"en": process_name}),
            value=elements,
            semantic_id=collection_semantic_id
        )
    
    def _resolve_capability_iri(self, raw: str) -> str:
        """Expand cssx: prefix to full IRI, or return as-is."""
        if not raw:
            return ''
        if raw.startswith('cssx:'):
            return self.CSSX_BASE + raw[5:]
        return raw
    
    def _create_parameter_elements(self, params) -> List:
        """Create elements from a list-of-dict or dict parameter config.

        Each dict entry may have idShort, value, valueType, unit, nominalValue,
        tolerance, description, semanticId, etc.
        """
        elements = []
        if isinstance(params, list):
            for p in params:
                if not isinstance(p, dict):
                    continue
                id_short = p.get('idShort', '')
                if not id_short:
                    continue
                props = []
                for k, v in p.items():
                    if k in ('idShort', 'semanticId', 'unitSemanticId',
                             'complianceType', 'toleranceType'):
                        continue
                    if isinstance(v, list):
                        v = '; '.join(str(x) for x in v)
                    if isinstance(v, bool):
                        vt = model.datatypes.Boolean
                    elif isinstance(v, int):
                        vt = model.datatypes.Int
                    elif isinstance(v, float):
                        vt = model.datatypes.Float
                    else:
                        vt = model.datatypes.String
                        v = str(v)
                    props.append(model.Property(id_short=k, value_type=vt, value=v))
                sem = p.get('semanticId')
                elements.append(
                    model.SubmodelElementCollection(
                        id_short=id_short,
                        value=props,
                        semantic_id=self._create_semantic_reference(sem) if sem else None
                    )
                )
        elif isinstance(params, dict):
            for name, val in params.items():
                if isinstance(val, bool):
                    vt = model.datatypes.Boolean
                elif isinstance(val, int):
                    vt = model.datatypes.Int
                elif isinstance(val, float):
                    vt = model.datatypes.Float
                else:
                    vt = model.datatypes.String
                    val = str(val)
                elements.append(model.Property(id_short=name, value_type=vt, value=val))
        return elements

    def _create_semantic_reference(self, semantic_id: str) -> model.ExternalReference:
        """Create an external reference for a semantic ID"""
        return model.ExternalReference(
            (model.Key(
                type_=model.KeyTypes.GLOBAL_REFERENCE,
                value=semantic_id
            ),)
        )


class RequirementsSubmodelBuilder:
    """
    Builder class for creating Requirements submodel for Product AAS.
    
    The Requirements submodel captures production requirements including:
    - Environmental conditions
    - In-process controls with rates
    - Quality control specifications
    
    Config format (list-of-dict):
        Requirements:
            Environmental:
                - idShort: 'AmbientTemperature'
                  nominalValue: 22.0
                  tolerance: 2.0
                  unit: '°C'
            InProcessControl:
                - idShort: 'WeighingCheck'
                  samplingRate: 100
                  unit: '%'
            QualityControl:
                - idShort: 'LabSamples'
                  quantity: 50
                  unit: 'units'
    """
    
    REQUIREMENTS_SEMANTIC_ID = SemanticIdCatalog.REQUIREMENTS_SUBMODEL
    
    def __init__(self, base_url: str, semantic_factory, element_factory):
        self.base_url = base_url
        self.semantic_factory = semantic_factory
        self.element_factory = element_factory
    
    def build(self, system_id: str, config: Dict) -> Optional[model.Submodel]:
        req_config = config.get('Requirements', {}) or {}
        if not req_config:
            return None
        
        submodel_elements = []
        
        for section_name in ('Environmental', 'InProcessControl', 'QualityControl'):
            section_cfg = req_config.get(section_name, None)
            if not section_cfg:
                continue
            collection = self._create_section_collection(section_name, section_cfg)
            if collection:
                submodel_elements.append(collection)
        
        if not submodel_elements:
            return None
        
        semantic_id_value = req_config.get(
            'semanticId', req_config.get('semantic_id', self.REQUIREMENTS_SEMANTIC_ID))
        
        return model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/Requirements",
            id_short="Requirements",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=self._create_semantic_reference(semantic_id_value),
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=submodel_elements
        )
    
    def _create_section_collection(
        self, section_name: str, section_cfg
    ) -> Optional[model.SubmodelElementCollection]:
        """Create a requirements section (Environmental, IPC, or QC) from list or dict."""
        elements = []
        
        if isinstance(section_cfg, list):
            for item in section_cfg:
                if not isinstance(item, dict):
                    continue
                id_short = item.get('idShort', '')
                if not id_short:
                    continue
                props = []
                for k, v in item.items():
                    if k in ('idShort', 'semanticId', 'unitSemanticId',
                             'complianceType', 'toleranceType'):
                        continue
                    if isinstance(v, list):
                        v = '; '.join(str(x) for x in v)
                    if isinstance(v, bool):
                        vt = model.datatypes.Boolean
                    elif isinstance(v, int):
                        vt = model.datatypes.Int
                    elif isinstance(v, float):
                        vt = model.datatypes.Float
                    else:
                        vt = model.datatypes.String
                        v = str(v)
                    props.append(model.Property(id_short=k, value_type=vt, value=v))
                sem = item.get('semanticId')
                elements.append(
                    model.SubmodelElementCollection(
                        id_short=id_short,
                        value=props,
                        semantic_id=self._create_semantic_reference(sem) if sem else None
                    )
                )
        elif isinstance(section_cfg, dict):
            for req_name, req_config in section_cfg.items():
                if not isinstance(req_config, dict):
                    continue
                props = self._dict_to_properties(req_config)
                sem = req_config.get('semantic_id', req_config.get('semanticId'))
                elements.append(
                    model.SubmodelElementCollection(
                        id_short=req_name,
                        value=props,
                        semantic_id=self._create_semantic_reference(sem) if sem else None
                    )
                )
        
        if not elements:
            return None
        return model.SubmodelElementCollection(id_short=section_name, value=elements)
    
    def _dict_to_properties(self, cfg: Dict) -> List:
        """Convert a flat dict to a list of Property elements."""
        props = []
        for k, v in cfg.items():
            if k in ('semantic_id', 'semanticId'):
                continue
            if isinstance(v, bool):
                vt = model.datatypes.Boolean
            elif isinstance(v, int):
                vt = model.datatypes.Int
            elif isinstance(v, float):
                vt = model.datatypes.Float
            else:
                vt = model.datatypes.String
                v = str(v)
            props.append(model.Property(id_short=k, value_type=vt, value=v))
        return props
    
    def _create_semantic_reference(self, semantic_id: str) -> model.ExternalReference:
        """Create an external reference for a semantic ID"""
        return model.ExternalReference(
            (model.Key(
                type_=model.KeyTypes.GLOBAL_REFERENCE,
                value=semantic_id
            ),)
        )
