"""Bill of Processes Submodel Builder for AAS generation.

This builder creates the BillOfProcesses submodel for Product AAS,
which defines the ordered sequence of production steps with their
semantic IDs for capability matching.
"""

from typing import Dict, List, Any, Optional
from basyx.aas import model


class BillOfProcessesSubmodelBuilder:
    """
    Builder class for creating BillOfProcesses submodel.
    
    The BillOfProcesses submodel represents the ordered sequence of
    production steps required to manufacture a product. Each step
    has a semantic ID that can be matched to resource capabilities.
    """
    
    # Semantic IDs
    BILL_OF_PROCESSES_SEMANTIC_ID = "https://smartproductionlab.aau.dk/submodels/BillOfProcesses/1/0"
    PROCESS_STEP_SEMANTIC_ID = "https://smartproductionlab.aau.dk/submodels/ProcessStep/1/0"
    
    def __init__(self, base_url: str, semantic_factory, element_factory):
        """
        Initialize the BillOfProcesses submodel builder.
        
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
        Create the BillOfProcesses submodel.
        
        Config format:
            BillOfProcesses:
                semantic_id: 'optional-override'
                Processes:
                    - ProcessName:
                        step: 1
                        semantic_id: 'https://...'
                        description: 'Description'
                        estimatedDuration: 5.0
                        parameters:
                            key: value
        
        Args:
            system_id: Unique identifier for the system
            config: Configuration dictionary containing BillOfProcesses section
            
        Returns:
            BillOfProcesses submodel instance
        """
        bop_config = config.get('BillOfProcesses', {}) or {}
        processes = bop_config.get('Processes', [])
        
        # Create process step elements
        process_elements = []
        
        for process_entry in processes:
            if isinstance(process_entry, dict):
                for process_name, process_config in process_entry.items():
                    if isinstance(process_config, dict):
                        step_element = self._create_process_step(
                            process_name, process_config
                        )
                        process_elements.append(step_element)
        
        # Create the Processes list
        processes_list = model.SubmodelElementList(
            id_short="Processes",
            type_value_list_element=model.SubmodelElementCollection,
            value=process_elements,
            semantic_id=self._create_semantic_reference(
                "https://smartproductionlab.aau.dk/submodels/ProcessList/1/0"
            )
        )
        
        # Create submodel semantic ID
        semantic_id_value = bop_config.get('semantic_id', self.BILL_OF_PROCESSES_SEMANTIC_ID)
        
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/BillOfProcesses",
            id_short="BillOfProcesses",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=self._create_semantic_reference(semantic_id_value),
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=[processes_list]
        )
        
        return submodel
    
    def _create_process_step(
        self, 
        process_name: str, 
        process_config: Dict
    ) -> model.SubmodelElementCollection:
        """
        Create a process step element.
        
        NOTE: Per AASd-120 constraint, items in a SubmodelElementList must NOT have id_short.
        Instead, we use displayName (a valid Referable attribute) to identify the process.
        The semanticId on the collection identifies the process type.
        
        Args:
            process_name: Name of the process step (stored in displayName)
            process_config: Configuration for the process step
            
        Returns:
            SubmodelElementCollection representing the process step
        """
        elements = []
        
        # Step number
        step_num = process_config.get('step', 0)
        elements.append(
            model.Property(
                id_short="Step",
                value_type=model.datatypes.Int,
                value=step_num
            )
        )
        
        # Semantic ID as property (for easy querying)
        semantic_id = process_config.get('semantic_id', '')
        if semantic_id:
            elements.append(
                model.Property(
                    id_short="SemanticId",
                    value_type=model.datatypes.String,
                    value=semantic_id
                )
            )
        
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
        
        # Estimated duration
        duration = process_config.get('estimatedDuration', 0.0)
        if duration:
            elements.append(
                model.Property(
                    id_short="EstimatedDuration",
                    value_type=model.datatypes.Float,
                    value=float(duration)
                )
            )
        
        # Parameters as nested collection
        parameters = process_config.get('parameters', {})
        if parameters:
            param_elements = []
            for param_name, param_value in parameters.items():
                # Determine value type
                if isinstance(param_value, bool):
                    value_type = model.datatypes.Boolean
                elif isinstance(param_value, int):
                    value_type = model.datatypes.Int
                elif isinstance(param_value, float):
                    value_type = model.datatypes.Float
                else:
                    value_type = model.datatypes.String
                    param_value = str(param_value)
                
                param_elements.append(
                    model.Property(
                        id_short=param_name,
                        value_type=value_type,
                        value=param_value
                    )
                )
            
            if param_elements:
                elements.append(
                    model.SubmodelElementCollection(
                        id_short="Parameters",
                        value=param_elements
                    )
                )
        
        # Create collection with semantic ID from process config
        # AASd-120: Items in SubmodelElementList must NOT have id_short
        # The process is identified by displayName (valid Referable attribute) and semanticId
        collection_semantic_id = None
        if semantic_id:
            collection_semantic_id = self._create_semantic_reference(semantic_id)
        
        return model.SubmodelElementCollection(
            id_short=None,
            display_name=model.MultiLanguageNameType({"en": process_name}),
            value=elements,
            semantic_id=collection_semantic_id
        )
    
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
    """
    
    REQUIREMENTS_SEMANTIC_ID = "https://smartproductionlab.aau.dk/submodels/Requirements/1/0"
    
    def __init__(self, base_url: str, semantic_factory, element_factory):
        """
        Initialize the Requirements submodel builder.
        
        Args:
            base_url: Base URL for AAS identifiers
            semantic_factory: SemanticIdFactory instance
            element_factory: AASElementFactory instance
        """
        self.base_url = base_url
        self.semantic_factory = semantic_factory
        self.element_factory = element_factory
    
    def build(self, system_id: str, config: Dict) -> model.Submodel:
        """
        Create the Requirements submodel.
        
        Args:
            system_id: Unique identifier for the system
            config: Configuration dictionary containing Requirements section
            
        Returns:
            Requirements submodel instance
        """
        req_config = config.get('Requirements', {}) or {}
        
        submodel_elements = []
        
        # Environmental requirements
        env_config = req_config.get('Environmental', {})
        if env_config:
            env_collection = self._create_environmental_collection(env_config)
            submodel_elements.append(env_collection)
        
        # In-process control requirements
        ipc_config = req_config.get('InProcessControl', {})
        if ipc_config:
            ipc_collection = self._create_ipc_collection(ipc_config)
            submodel_elements.append(ipc_collection)
        
        # Quality control requirements
        qc_config = req_config.get('QualityControl', {})
        if qc_config:
            qc_collection = self._create_qc_collection(qc_config)
            submodel_elements.append(qc_collection)
        
        semantic_id_value = req_config.get('semantic_id', self.REQUIREMENTS_SEMANTIC_ID)
        
        submodel = model.Submodel(
            id_=f"{self.base_url}/submodels/instances/{system_id}/Requirements",
            id_short="Requirements",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=self._create_semantic_reference(semantic_id_value),
            administration=model.AdministrativeInformation(version="1", revision="0"),
            submodel_element=submodel_elements
        )
        
        return submodel
    
    def _create_environmental_collection(self, config: Dict) -> model.SubmodelElementCollection:
        """Create Environmental requirements collection"""
        elements = []
        
        for req_name, req_config in config.items():
            if isinstance(req_config, dict):
                req_elements = self._create_requirement_elements(req_config)
                elements.append(
                    model.SubmodelElementCollection(
                        id_short=req_name,
                        value=req_elements,
                        semantic_id=self._create_semantic_reference(
                            req_config.get('semantic_id', '')
                        ) if req_config.get('semantic_id') else None
                    )
                )
        
        return model.SubmodelElementCollection(
            id_short="Environmental",
            value=elements
        )
    
    def _create_ipc_collection(self, config: Dict) -> model.SubmodelElementCollection:
        """Create In-Process Control requirements collection"""
        elements = []
        
        for req_name, req_config in config.items():
            if isinstance(req_config, dict):
                req_elements = self._create_rate_requirement_elements(req_config)
                elements.append(
                    model.SubmodelElementCollection(
                        id_short=req_name,
                        value=req_elements,
                        semantic_id=self._create_semantic_reference(
                            req_config.get('semantic_id', '')
                        ) if req_config.get('semantic_id') else None
                    )
                )
        
        return model.SubmodelElementCollection(
            id_short="InProcessControl",
            value=elements
        )
    
    def _create_qc_collection(self, config: Dict) -> model.SubmodelElementCollection:
        """Create Quality Control requirements collection"""
        elements = []
        
        for req_name, req_config in config.items():
            if isinstance(req_config, dict):
                req_elements = self._create_rate_requirement_elements(req_config)
                
                # Add sample size if present
                if 'sampleSize' in req_config:
                    req_elements.append(
                        model.Property(
                            id_short="SampleSize",
                            value_type=model.datatypes.Int,
                            value=req_config['sampleSize']
                        )
                    )
                
                elements.append(
                    model.SubmodelElementCollection(
                        id_short=req_name,
                        value=req_elements,
                        semantic_id=self._create_semantic_reference(
                            req_config.get('semantic_id', '')
                        ) if req_config.get('semantic_id') else None
                    )
                )
        
        return model.SubmodelElementCollection(
            id_short="QualityControl",
            value=elements
        )
    
    def _create_requirement_elements(self, config: Dict) -> List:
        """Create elements for a basic requirement"""
        elements = []
        
        if 'value' in config:
            value = config['value']
            if isinstance(value, (int, float)):
                elements.append(
                    model.Property(
                        id_short="Value",
                        value_type=model.datatypes.Float if isinstance(value, float) else model.datatypes.Int,
                        value=value
                    )
                )
            else:
                elements.append(
                    model.Property(
                        id_short="Value",
                        value_type=model.datatypes.String,
                        value=str(value)
                    )
                )
        
        if 'unit' in config:
            elements.append(
                model.Property(
                    id_short="Unit",
                    value_type=model.datatypes.String,
                    value=config['unit']
                )
            )
        
        if 'tolerance' in config:
            elements.append(
                model.Property(
                    id_short="Tolerance",
                    value_type=model.datatypes.Float,
                    value=float(config['tolerance'])
                )
            )
        
        return elements
    
    def _create_rate_requirement_elements(self, config: Dict) -> List:
        """Create elements for a rate-based requirement"""
        elements = []
        
        if 'rate' in config:
            elements.append(
                model.Property(
                    id_short="Rate",
                    value_type=model.datatypes.Float,
                    value=float(config['rate'])
                )
            )
        
        if 'unit' in config:
            elements.append(
                model.Property(
                    id_short="Unit",
                    value_type=model.datatypes.String,
                    value=config['unit']
                )
            )
        
        if 'appliesTo' in config:
            elements.append(
                model.Property(
                    id_short="AppliesTo",
                    value_type=model.datatypes.String,
                    value=config['appliesTo']
                )
            )
        
        if 'description' in config:
            elements.append(
                model.Property(
                    id_short="Description",
                    value_type=model.datatypes.String,
                    value=config['description']
                )
            )
        
        return elements
    
    def _create_semantic_reference(self, semantic_id: str) -> model.ExternalReference:
        """Create an external reference for a semantic ID"""
        return model.ExternalReference(
            (model.Key(
                type_=model.KeyTypes.GLOBAL_REFERENCE,
                value=semantic_id
            ),)
        )
