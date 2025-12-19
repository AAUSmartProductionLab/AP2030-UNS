/**
 * AAS (Asset Administration Shell) Service
 * 
 * Uses basyx-typescript-sdk for registry operations and aas-core3.0-typescript
 * types for building proper Submodel structures.
 */

import { toast } from 'react-toastify';
import { 
  AasRegistryClient, 
  SubmodelRepositoryClient,
  Configuration
} from 'basyx-typescript-sdk';
import {
  Submodel,
  Entity,
  EntityType,
  Property,
  SubmodelElementCollection,
  ReferenceElement,
  RelationshipElement,
  Reference,
  ReferenceTypes,
  Key,
  KeyTypes,
  ModellingKind,
  DataTypeDefXsd
} from '@aas-core-works/aas-core3.0-typescript/types';

class AasService {
  constructor() {
    // Service URLs from environment
    this.repositoryUrl = import.meta.env.VITE_AAS_REPOSITORY_URL || 'http://192.168.0.104:8081';
    this.shellRegistryUrl = import.meta.env.VITE_AAS_SHELL_REGISTRY_URL || 'http://192.168.0.104:8082';
    
    // Root AAS configuration
    this.rootSubmodelId = import.meta.env.VITE_ROOT_SUBMODEL_ID || 
      'https://smartproductionlab.aau.dk/submodels/instances/aauFillingLine/HierarchicalStructures';
    
    // SDK Clients
    this.registryClient = new AasRegistryClient();
    this.submodelClient = new SubmodelRepositoryClient();
    
    // SDK Configurations
    this.registryConfig = new Configuration({ basePath: this.shellRegistryUrl });
    this.repositoryConfig = new Configuration({ basePath: this.repositoryUrl });
  }

  // ========================================
  // Shell Registry Operations (SDK)
  // ========================================

  async getAllShells() {
    try {
      const result = await this.registryClient.getAllAssetAdministrationShellDescriptors({
        configuration: this.registryConfig
      });
      
      if (result.success && result.data?.result) {
        return result.data.result;
      }
      
      console.error('Failed to get shell descriptors:', result.error);
      return [];
    } catch (error) {
      console.error('Failed to fetch shell descriptors:', error);
      toast.error(`Failed to fetch AAS modules: ${error.message}`);
      return [];
    }
  }

  async getFullShell(endpoint) {
    try {
      const response = await fetch(endpoint, {
        headers: { 'Content-Type': 'application/json' }
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error(`Failed to fetch full shell from ${endpoint}:`, error);
      return null;
    }
  }

  // ========================================
  // Module Catalog Building
  // ========================================

  async buildModuleCatalog() {
    try {
      const shellDescriptors = await this.getAllShells();
      
      // Filter out shuttles and root system
      const excludePatterns = ['shuttle', 'aauFillingLine'];
      
      const moduleDescriptors = shellDescriptors.filter(shell => {
        const idShort = shell.idShort?.toLowerCase() || '';
        const id = shell.id?.toLowerCase() || '';
        
        return !excludePatterns.some(pattern => 
          idShort.includes(pattern) || id.includes(pattern)
        );
      });
      
      // Fetch full shell details
      const shellPromises = moduleDescriptors.map(async (descriptor) => {
        const endpoint = descriptor.endpoints?.[0]?.protocolInformation?.href;
        if (endpoint) {
          const fullShell = await this.getFullShell(endpoint);
          return fullShell || descriptor;
        }
        return descriptor;
      });
      
      const shells = await Promise.all(shellPromises);
      
      // Extract module data with full AAS metadata
      const modules = shells.map(shell => {
        const hierarchicalSubmodel = shell.submodels?.find(sm => 
          sm.keys?.[0]?.value?.includes('HierarchicalStructures')
        );
        
        // Extract asset information
        const assetInfo = shell.assetInformation || {};
        const assetId = assetInfo.globalAssetId || shell.id;
        const assetKind = assetInfo.assetKind || 'Instance';
        const assetType = assetInfo.assetType || this.inferAssetType(shell.idShort);
        
        return {
          name: shell.idShort || 'Unknown Module',
          displayName: this.formatDisplayName(shell.idShort),
          aasId: shell.id,
          assetId: assetId,
          assetKind: assetKind,
          assetType: assetType,
          submodelId: hierarchicalSubmodel?.keys?.[0]?.value || null,
          description: shell.description?.[0]?.text || ''
        };
      });
      
      // Sort modules by assetType
      modules.sort((a, b) => {
        const typeOrder = ['Filling', 'Stoppering', 'Loading', 'Unloading', 'Camera', 'PlanarTable', 'Other'];
        const aIndex = typeOrder.indexOf(a.assetType);
        const bIndex = typeOrder.indexOf(b.assetType);
        const aOrder = aIndex === -1 ? typeOrder.length : aIndex;
        const bOrder = bIndex === -1 ? typeOrder.length : bIndex;
        return aOrder - bOrder;
      });
      
      return modules;
    } catch (error) {
      console.error('Failed to build module catalog:', error);
      toast.error(`Failed to build module catalog: ${error.message}`);
      return [];
    }
  }

  inferAssetType(idShort) {
    if (!idShort) return 'Other';
    const lower = idShort.toLowerCase();
    
    if (lower.includes('filling')) return 'Filling';
    if (lower.includes('stoppering')) return 'Stoppering';
    if (lower.includes('loading') && !lower.includes('unloading')) return 'Loading';
    if (lower.includes('unloading')) return 'Unloading';
    if (lower.includes('camera')) return 'Camera';
    if (lower.includes('planar')) return 'PlanarTable';
    
    return 'Other';
  }

  buildCategorizedCatalog(modules) {
    // Group modules by assetType
    const groupedByType = {};
    
    modules.forEach(module => {
      const assetType = module.assetType || 'Other';
      if (!groupedByType[assetType]) {
        groupedByType[assetType] = [];
      }
      groupedByType[assetType].push(module);
    });
    
    // Color map for different asset types
    const typeColors = {
      'Filling': '#1E7D74',
      'Stoppering': '#30A399',
      'Loading': '#0087CD',
      'Unloading': '#00A0F0',
      'Camera': '#9B4DCA',
      'PlanarTable': '#136058',
      'Other': '#666666'
    };
    
    // Build categories from grouped modules
    const categories = Object.entries(groupedByType).map(([assetType, typeModules]) => {
      const nodes = typeModules.map((module) => ({
        id: module.name.toLowerCase().replace(/\s+/g, '-'),
        title: module.displayName,
        color: typeColors[assetType] || '#666666',
        aasId: module.aasId,
        submodelId: module.submodelId,
        assetId: module.assetId,
        assetKind: module.assetKind,
        assetType: module.assetType,
        description: module.description
      }));
      
      return {
        id: `category-${assetType.toLowerCase()}`,
        name: assetType,
        assetType: assetType,
        nodes: nodes
      };
    });
    
    // Sort categories by asset type order
    const typeOrder = ['Filling', 'Stoppering', 'Loading', 'Unloading', 'Camera', 'PlanarTable', 'Other'];
    categories.sort((a, b) => {
      const aIndex = typeOrder.indexOf(a.assetType);
      const bIndex = typeOrder.indexOf(b.assetType);
      return (aIndex === -1 ? typeOrder.length : aIndex) - (bIndex === -1 ? typeOrder.length : bIndex);
    });
    
    return categories;
  }

  formatDisplayName(idShort) {
    if (!idShort) return 'Unknown';
    
    let name = idShort;
    
    if (name.endsWith('AAS')) {
      name = name.slice(0, -3);
    }
    
    name = name
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .replace(/^./, str => str.toUpperCase())
      .trim();
    
    return name + ' AAS';
  }

  // ========================================
  // Repository Operations (SDK)
  // ========================================

  async getHierarchicalStructures(submodelId = null) {
    try {
      const id = submodelId || this.rootSubmodelId;
      
      const result = await this.submodelClient.getSubmodelById({
        configuration: this.repositoryConfig,
        submodelIdentifier: id
      });
      
      if (result.success) {
        return result.data;
      }
      
      throw new Error(result.error?.message || 'Failed to get submodel');
    } catch (error) {
      console.error('Failed to fetch HierarchicalStructures:', error);
      toast.error(`Failed to load configuration: ${error.message}`);
      throw error;
    }
  }

  async putHierarchicalStructures(submodelData, submodelId = null) {
    try {
      const id = submodelId || this.rootSubmodelId;
      
      const result = await this.submodelClient.putSubmodelById({
        configuration: this.repositoryConfig,
        submodelIdentifier: id,
        submodel: submodelData
      });
      
      if (result.success) {
        toast.success('Configuration saved to AAS successfully!');
        return result.data || submodelData;
      }
      
      throw new Error(result.error?.message || 'Failed to update submodel');
    } catch (error) {
      console.error('Failed to update HierarchicalStructures:', error);
      toast.error(`Failed to save configuration: ${error.message}`);
      throw error;
    }
  }

  // ========================================
  // Data Transformation (Using SDK Types)
  // ========================================

  getGenericName(assetType, instanceName) {
    if (assetType && assetType !== 'Other') {
      return assetType;
    }
    
    if (instanceName) {
      const lowerName = instanceName.toLowerCase();
      if (lowerName.includes('filling')) return 'Filling';
      if (lowerName.includes('stoppering')) return 'Stoppering';
      if (lowerName.includes('loading') && !lowerName.includes('unloading')) return 'Loading';
      if (lowerName.includes('unloading')) return 'Unloading';
      if (lowerName.includes('camera')) return 'Camera';
      if (lowerName.includes('planar')) return 'PlanarTable';
    }
    
    return (instanceName || 'Unknown').replace(/\s+/g, '').replace(/[^a-zA-Z0-9]/g, '');
  }

  /**
   * Create a Reference using SDK types
   */
  createReference(type, keys) {
    return new Reference(type, keys);
  }

  /**
   * Create a Key using SDK types
   */
  createKey(type, value) {
    return new Key(type, value);
  }

  /**
   * Create a Property using SDK types
   */
  createProperty(idShort, value, valueType = DataTypeDefXsd.String, semanticId = null) {
    return new Property(
      valueType,
      null,  // extensions
      null,  // category
      idShort,
      null,  // displayName
      null,  // description
      semanticId,
      null,  // supplementalSemanticIds
      null,  // qualifiers
      null,  // embeddedDataSpecifications
      value?.toString() || ''
    );
  }

  /**
   * Create a SubmodelElementCollection using SDK types
   */
  createSubmodelElementCollection(idShort, elements, semanticId = null) {
    return new SubmodelElementCollection(
      null,  // extensions
      null,  // category
      idShort,
      null,  // displayName
      null,  // description
      semanticId,
      null,  // supplementalSemanticIds
      null,  // qualifiers
      null,  // embeddedDataSpecifications
      elements
    );
  }

  /**
   * Create a ReferenceElement using SDK types
   */
  createReferenceElement(idShort, reference, semanticId = null) {
    return new ReferenceElement(
      null,  // extensions
      null,  // category
      idShort,
      null,  // displayName
      null,  // description
      semanticId,
      null,  // supplementalSemanticIds
      null,  // qualifiers
      null,  // embeddedDataSpecifications
      reference
    );
  }

  /**
   * Create an Entity using SDK types
   */
  createEntity(idShort, entityType, globalAssetId, statements, semanticId = null) {
    return new Entity(
      entityType,
      null,  // extensions
      null,  // category
      idShort,
      null,  // displayName
      null,  // description
      semanticId,
      null,  // supplementalSemanticIds
      null,  // qualifiers
      null,  // embeddedDataSpecifications
      statements,
      globalAssetId,
      null   // specificAssetIds
    );
  }

  /**
   * Create a RelationshipElement using SDK types
   */
  createRelationshipElement(idShort, first, second, semanticId = null) {
    return new RelationshipElement(
      first,
      second,
      null,  // extensions
      null,  // category
      idShort,
      null,  // displayName
      null,  // description
      semanticId,
      null,  // supplementalSemanticIds
      null,  // qualifiers
      null   // embeddedDataSpecifications
    );
  }

  /**
   * Create a Submodel using SDK types
   */
  createSubmodel(id, idShort, elements, semanticId = null) {
    return new Submodel(
      id,
      null,  // extensions
      null,  // category
      idShort,
      null,  // displayName
      null,  // description
      null,  // administration
      ModellingKind.Instance,
      semanticId,
      null,  // supplementalSemanticIds
      null,  // qualifiers
      null,  // embeddedDataSpecifications
      elements
    );
  }

  /**
   * Create an Entity node for a station
   */
  createEntityNode(idShort, globalAssetId, x, y, yaw = 0, instanceSubmodelId = null) {
    // Create Location collection with x, y, yaw properties
    const locationSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/Location')]
    );
    
    const locationProperties = [
      this.createProperty('x', x, DataTypeDefXsd.Float),
      this.createProperty('y', y, DataTypeDefXsd.Float),
      this.createProperty('yaw', yaw, DataTypeDefXsd.Float)
    ];
    
    const locationCollection = this.createSubmodelElementCollection('Location', locationProperties, locationSemanticId);
    
    const statements = [locationCollection];
    
    // Add SameAs reference if instanceSubmodelId is provided
    if (instanceSubmodelId) {
      const sameAsSemanticId = this.createReference(
        ReferenceTypes.ExternalReference,
        [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/1/0/SameAs')]
      );
      
      const sameAsReference = this.createReference(
        ReferenceTypes.ModelReference,
        [
          this.createKey(KeyTypes.Submodel, instanceSubmodelId),
          this.createKey(KeyTypes.Entity, 'EntryNode')
        ]
      );
      
      const sameAsElement = this.createReferenceElement('SameAs', sameAsReference, sameAsSemanticId);
      statements.push(sameAsElement);
    }
    
    const nodeSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/1/0/Node')]
    );
    
    return this.createEntity(idShort, EntityType.SelfManagedEntity, globalAssetId, statements, nodeSemanticId);
  }

  /**
   * Create a RelationshipElement for parent-child relationship
   */
  createRelationshipElementForHierarchy(idShort, parentNodeId, childNodeId) {
    const submodelId = this.rootSubmodelId;
    
    const firstRef = this.createReference(
      ReferenceTypes.ModelReference,
      [
        this.createKey(KeyTypes.Submodel, submodelId),
        this.createKey(KeyTypes.Entity, parentNodeId)
      ]
    );
    
    const secondRef = this.createReference(
      ReferenceTypes.ModelReference,
      [
        this.createKey(KeyTypes.Submodel, submodelId),
        this.createKey(KeyTypes.Entity, parentNodeId),
        this.createKey(KeyTypes.Entity, childNodeId)
      ]
    );
    
    const semanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/1/0/IsPartOf')]
    );
    
    return this.createRelationshipElement(idShort, firstRef, secondRef, semanticId);
  }

  transformLayoutDataToHierarchicalStructures(layoutData) {
    const submodelId = this.rootSubmodelId;
    const rootAssetId = 'https://smartproductionlab.aau.dk/assets/aauFillingLine';
    
    // Build child entities from stations
    const childEntities = layoutData.Stations.map(station => {
      const instanceName = station['Instance Name'];
      const assetType = station['AssetType'];
      const genericName = this.getGenericName(assetType, instanceName);
      
      const globalAssetId = station['AssetId'] || 
        `https://smartproductionlab.aau.dk/assets/${genericName.toLowerCase()}`;
      const instanceSubmodelId = station['SubmodelId'];
      
      const approachPos = station["Approach Position"] || [0, 0, 0];
      const xMM = Array.isArray(approachPos) ? approachPos[0] : 0;
      const yMM = Array.isArray(approachPos) ? approachPos[1] : 0;
      const yaw = Array.isArray(approachPos) ? approachPos[2] : 0;
      
      return this.createEntityNode(genericName, globalAssetId, xMM, yMM, yaw, instanceSubmodelId);
    });
    
    // Build relationships
    const relationships = layoutData.Stations.map(station => {
      const genericName = this.getGenericName(station['AssetType'], station['Instance Name']);
      return this.createRelationshipElementForHierarchy(`Has${genericName}`, 'EntryNode', genericName);
    });
    
    // Create Archetype property
    const archetypeSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/1/0/Archetype')]
    );
    const archetypeProperty = this.createProperty('Archetype', 'OneDown', DataTypeDefXsd.String, archetypeSemanticId);
    
    // Create EntryNode entity
    const entryNodeSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/1/0/EntryNode')]
    );
    const entryNode = this.createEntity('EntryNode', EntityType.SelfManagedEntity, rootAssetId, childEntities, entryNodeSemanticId);
    
    // Create the Submodel
    const submodelSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/1/0')]
    );
    
    const submodelElements = [archetypeProperty, entryNode, ...relationships];
    
    return this.createSubmodel(submodelId, 'HierarchicalStructures', submodelElements, submodelSemanticId);
  }

  transformHierarchicalStructuresToLayoutData(hierarchicalStructures, moduleCatalog) {
    try {
      // Handle both SDK Submodel objects and raw JSON
      const submodelElements = hierarchicalStructures.submodelElements || [];
      
      const entryNode = submodelElements.find(
        el => (el.idShort === 'EntryNode') && 
              (el.modelType === 'Entity' || el.modelType?.() === 'Entity' || el.entityType)
      );
      
      if (!entryNode) {
        console.warn('No EntryNode found in HierarchicalStructures');
        return { Stations: [] };
      }
      
      // Get statements - handle both SDK objects and raw JSON
      const statements = entryNode.statements || [];
      
      const stations = statements
        .filter(statement => 
          statement.modelType === 'Entity' || 
          statement.modelType?.() === 'Entity' || 
          statement.entityType
        )
        .map((entity, index) => {
          // Find Location collection
          const entityStatements = entity.statements || [];
          const locationCollection = entityStatements.find(
            s => s.idShort === 'Location' && 
                (s.modelType === 'SubmodelElementCollection' || s.value)
          );
          
          const locationValues = locationCollection?.value || [];
          const xProp = locationValues.find(p => p.idShort === 'x');
          const yProp = locationValues.find(p => p.idShort === 'y');
          const yawProp = locationValues.find(p => p.idShort === 'yaw');
          
          const xMM = parseFloat(xProp?.value || 0);
          const yMM = parseFloat(yProp?.value || 0);
          const yaw = parseFloat(yawProp?.value || 0);
          
          const approachPosition = [xMM, yMM, yaw];
          
          // Find SameAs reference
          const sameAsRef = entityStatements.find(
            s => s.idShort === 'SameAs' && 
                (s.modelType === 'ReferenceElement' || s.value?.keys)
          );
          
          const submodelId = sameAsRef?.value?.keys?.find(k => k.type === 'Submodel')?.value || null;
          
          // Match with module catalog
          const module = moduleCatalog.find(m => m.aasId === entity.globalAssetId);
          
          return {
            Name: entity.idShort,
            'Instance Name': module?.name || entity.idShort,
            StationId: index,
            AasId: entity.globalAssetId,
            SubmodelId: submodelId,
            'Approach Position': approachPosition,
            'Process Position': approachPosition
          };
        });
      
      return { Stations: stations };
    } catch (error) {
      console.error('Failed to transform HierarchicalStructures:', error);
      toast.error(`Failed to parse configuration: ${error.message}`);
      return { Stations: [] };
    }
  }
}

const aasService = new AasService();
export default aasService;
