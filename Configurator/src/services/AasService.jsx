/**
 * AAS (Asset Administration Shell) Service - Simplified
 * 
 * Handles interactions with AAS Repository and Shell Registry:
 * - Repository (8081): AAS and Submodel data storage
 * - Shell Registry (8082): AAS descriptor discovery
 */

import { toast } from 'react-toastify';

class AasService {
  constructor() {
    // Service URLs
    this.repositoryUrl = import.meta.env.VITE_AAS_REPOSITORY_URL || 'http://192.168.0.104:8081';
    this.shellRegistryUrl = import.meta.env.VITE_AAS_SHELL_REGISTRY_URL || 'http://192.168.0.104:8082';
    
    // Root AAS configuration
    this.rootAasId = import.meta.env.VITE_ROOT_AAS_ID || 'https://smartproductionlab.aau.dk/aas/aauFillingLine';
    this.rootSubmodelId = import.meta.env.VITE_ROOT_SUBMODEL_ID || 
      'https://smartproductionlab.aau.dk/submodels/instances/aauFillingLine/HierarchicalStructures';
  }

  // ========================================
  // Base64 Encoding/Decoding
  // ========================================

  encodeAasId(id) {
    try {
      return btoa(id);
    } catch (error) {
      console.error('Failed to encode AAS ID:', error);
      throw new Error('Invalid AAS identifier for encoding');
    }
  }

  decodeAasId(encodedId) {
    try {
      return atob(encodedId);
    } catch (error) {
      console.error('Failed to decode AAS ID:', error);
      throw new Error('Invalid Base64-encoded identifier');
    }
  }

  // ========================================
  // HTTP Request Wrapper
  // ========================================

  async request(url, options = {}, timeout = 10000) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        }
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }

      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        return await response.json();
      }
      
      return await response.text();
    } catch (error) {
      clearTimeout(timeoutId);
      
      if (error.name === 'AbortError') {
        throw new Error('Request timeout - AAS service not responding');
      }
      
      console.error('AAS Service request failed:', error);
      throw error;
    }
  }

  // ========================================
  // Shell Registry Operations
  // ========================================

  async getAllShells() {
    try {
      const url = `${this.shellRegistryUrl}/shell-descriptors`;
      const response = await this.request(url);
      
      if (response.result && Array.isArray(response.result)) {
        return response.result;
      }
      
      if (Array.isArray(response)) {
        return response;
      }
      
      console.warn('Unexpected shell descriptors response format:', response);
      return [];
    } catch (error) {
      console.error('Failed to fetch shell descriptors:', error);
      toast.error(`Failed to fetch AAS modules: ${error.message}`);
      return [];
    }
  }

  async getFullShell(endpoint) {
    try {
      return await this.request(endpoint);
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
    
    // Don't add spaces, just return as-is but ensure proper capitalization
    // Remove 'AAS' suffix if present for cleaner display, then add it back properly
    let name = idShort;
    
    // Handle common patterns
    if (name.endsWith('AAS')) {
      name = name.slice(0, -3); // Remove AAS suffix
    }
    
    // Add spaces before capitals for readability, but keep it clean
    name = name
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .replace(/^./, str => str.toUpperCase())
      .trim();
    
    return name + ' AAS';
  }

  // ========================================
  // Repository Operations
  // ========================================

  async getHierarchicalStructures(submodelId = null) {
    try {
      const id = submodelId || this.rootSubmodelId;
      const encodedId = this.encodeAasId(id);
      const url = `${this.repositoryUrl}/submodels/${encodedId}`;
      
      return await this.request(url);
    } catch (error) {
      console.error('Failed to fetch HierarchicalStructures:', error);
      toast.error(`Failed to load configuration: ${error.message}`);
      throw error;
    }
  }

  async putHierarchicalStructures(submodelData, submodelId = null) {
    try {
      const id = submodelId || this.rootSubmodelId;
      const encodedId = this.encodeAasId(id);
      const url = `${this.repositoryUrl}/submodels/${encodedId}`;
      
      const result = await this.request(url, {
        method: 'PUT',
        body: JSON.stringify(submodelData)
      });
      
      toast.success('Configuration saved to AAS successfully!');
      return result;
    } catch (error) {
      console.error('Failed to update HierarchicalStructures:', error);
      toast.error(`Failed to save configuration: ${error.message}`);
      throw error;
    }
  }

  // ========================================
  // Data Transformation
  // ========================================

  /**
   * Get a generic/clean name for use as idShort in HierarchicalStructures.
   * Uses the assetType if available, otherwise infers from the instance name.
   */
  getGenericName(assetType, instanceName) {
    // Use assetType directly if available
    if (assetType && assetType !== 'Other') {
      return assetType;
    }
    
    // Fallback: infer from instance name
    if (instanceName) {
      const lowerName = instanceName.toLowerCase();
      if (lowerName.includes('filling')) return 'Filling';
      if (lowerName.includes('stoppering')) return 'Stoppering';
      if (lowerName.includes('loading') && !lowerName.includes('unloading')) return 'Loading';
      if (lowerName.includes('unloading')) return 'Unloading';
      if (lowerName.includes('camera')) return 'Camera';
      if (lowerName.includes('planar')) return 'PlanarTable';
    }
    
    // Last resort: sanitize the instance name
    return (instanceName || 'Unknown').replace(/\s+/g, '').replace(/[^a-zA-Z0-9]/g, '');
  }

  transformLayoutDataToHierarchicalStructures(layoutData) {
    const submodelId = this.rootSubmodelId;
    const rootAssetId = 'https://smartproductionlab.aau.dk/assets/aauFillingLine';
    
    // Build child entities from stations using their actual AAS data
    const childEntities = layoutData.Stations.map(station => {
      const instanceName = station['Instance Name'];
      const assetType = station['AssetType'];
      
      // Get generic name for the entity idShort (e.g., "Filling", "Camera")
      const genericName = this.getGenericName(assetType, instanceName);
      
      // Use the actual asset ID and submodel ID from the placed module
      const globalAssetId = station['AssetId'] || 
        `https://smartproductionlab.aau.dk/assets/${genericName.toLowerCase()}`;
      const instanceSubmodelId = station['SubmodelId']; // HierarchicalStructures submodel of this asset
      
      const approachPos = station["Approach Position"] || [0, 0, 0];
      const xMM = Array.isArray(approachPos) ? approachPos[0] : 0;
      const yMM = Array.isArray(approachPos) ? approachPos[1] : 0;
      const yaw = Array.isArray(approachPos) ? approachPos[2] : 0;
      
      return this.createEntityNode(genericName, globalAssetId, xMM, yMM, yaw, instanceSubmodelId);
    });
    
    // Build relationships using generic names
    const relationships = layoutData.Stations.map(station => {
      const genericName = this.getGenericName(station['AssetType'], station['Instance Name']);
      return this.createRelationshipElement(`Has${genericName}`, 'EntryNode', genericName);
    });
    
    return {
      modelType: 'Submodel',
      kind: 'Instance',
      semanticId: {
        type: 'ExternalReference',
        keys: [{
          type: 'GlobalReference',
          value: 'https://admin-shell.io/idta/HierarchicalStructures/1/0'
        }]
      },
      id: submodelId,
      idShort: 'HierarchicalStructures',
      submodelElements: [
        {
          modelType: 'Property',
          value: 'OneDown',
          valueType: 'xs:string',
          semanticId: {
            type: 'ExternalReference',
            keys: [{
              type: 'GlobalReference',
              value: 'https://admin-shell.io/idta/HierarchicalStructures/1/0/Archetype'
            }]
          },
          idShort: 'Archetype'
        },
        {
          modelType: 'Entity',
          entityType: 'SelfManagedEntity',
          globalAssetId: rootAssetId,
          statements: childEntities,
          semanticId: {
            type: 'ExternalReference',
            keys: [{
              type: 'GlobalReference',
              value: 'https://admin-shell.io/idta/HierarchicalStructures/1/0/EntryNode'
            }]
          },
          idShort: 'EntryNode'
        },
        ...relationships
      ]
    };
  }

  transformHierarchicalStructuresToLayoutData(hierarchicalStructures, moduleCatalog) {
    try {
      const entryNode = hierarchicalStructures.submodelElements?.find(
        el => el.idShort === 'EntryNode' && el.modelType === 'Entity'
      );
      
      if (!entryNode || !entryNode.statements) {
        console.warn('No EntryNode found in HierarchicalStructures');
        return { Stations: [] };
      }
      
      const stations = entryNode.statements
        .filter(statement => statement.modelType === 'Entity')
        .map((entity, index) => {
          const locationCollection = entity.statements?.find(
            s => s.idShort === 'Location' && s.modelType === 'SubmodelElementCollection'
          );
          
          const xProp = locationCollection?.value?.find(p => p.idShort === 'x');
          const yProp = locationCollection?.value?.find(p => p.idShort === 'y');
          const yawProp = locationCollection?.value?.find(p => p.idShort === 'yaw');
          
          const xMM = parseFloat(xProp?.value || 0);
          const yMM = parseFloat(yProp?.value || 0);
          const yaw = parseFloat(yawProp?.value || 0);
          
          const approachPosition = [xMM, yMM, yaw];
          
          const sameAsRef = entity.statements?.find(
            s => s.idShort === 'SameAs' && s.modelType === 'ReferenceElement'
          );
          const submodelId = sameAsRef?.value?.keys?.find(k => k.type === 'Submodel')?.value || null;
          
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

  // ========================================
  // Helper Functions
  // ========================================

  createEntityNode(idShort, globalAssetId, x, y, yaw = 0, instanceSubmodelId = null) {
    const statements = [
      {
        modelType: 'SubmodelElementCollection',
        semanticId: {
          type: 'ExternalReference',
          keys: [{
            type: 'GlobalReference',
            value: 'https://smartproductionlab.aau.dk/semantics/Location'
          }]
        },
        idShort: 'Location',
        value: [
          {
            modelType: 'Property',
            value: x.toString(),
            valueType: 'xs:float',
            idShort: 'x'
          },
          {
            modelType: 'Property',
            value: y.toString(),
            valueType: 'xs:float',
            idShort: 'y'
          },
          {
            modelType: 'Property',
            value: yaw.toString(),
            valueType: 'xs:float',
            idShort: 'yaw'
          }
        ]
      }
    ];
    
    // Add SameAs reference if submodel ID is provided
    if (instanceSubmodelId) {
      statements.push({
        modelType: 'ReferenceElement',
        semanticId: {
          type: 'ExternalReference',
          keys: [{
            type: 'GlobalReference',
            value: 'https://admin-shell.io/idta/HierarchicalStructures/1/0/SameAs'
          }]
        },
        idShort: 'SameAs',
        value: {
          type: 'ModelReference',
          keys: [
            {
              type: 'Submodel',
              value: instanceSubmodelId
            },
            {
              type: 'Entity',
              value: 'EntryNode'
            }
          ]
        }
      });
    }
    
    const entity = {
      modelType: 'Entity',
      entityType: 'SelfManagedEntity',
      globalAssetId: globalAssetId,
      statements: statements,
      semanticId: {
        type: 'ExternalReference',
        keys: [{
          type: 'GlobalReference',
          value: 'https://admin-shell.io/idta/HierarchicalStructures/1/0/Node'
        }]
      },
      idShort: idShort
    };
    
    return entity;
  }

  createRelationshipElement(idShort, parentNodeId, childNodeId) {
    const submodelId = this.rootSubmodelId;
    
    return {
      modelType: 'RelationshipElement',
      first: {
        type: 'ModelReference',
        keys: [
          {
            type: 'Submodel',
            value: submodelId
          },
          {
            type: 'Entity',
            value: parentNodeId
          }
        ]
      },
      second: {
        type: 'ModelReference',
        keys: [
          {
            type: 'Submodel',
            value: submodelId
          },
          {
            type: 'Entity',
            value: parentNodeId
          },
          {
            type: 'Entity',
            value: childNodeId
          }
        ]
      },
      semanticId: {
        type: 'ExternalReference',
        keys: [{
          type: 'GlobalReference',
          value: 'https://admin-shell.io/idta/HierarchicalStructures/1/0/IsPartOf'
        }]
      },
      idShort: idShort
    };
  }
}

const aasService = new AasService();
export default aasService;
