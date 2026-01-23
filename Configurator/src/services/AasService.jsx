/**
 * AAS (Asset Administration Shell) Service
 * 
 * Uses basyx-typescript-sdk for registry operations and aas-core3.0-typescript
 * types for building proper Submodel structures.
 */

import { toast } from 'react-toastify';
import { 
  AasRegistryClient, 
  AasRepositoryClient,
  SubmodelRepositoryClient,
  Configuration,
  AssetAdministrationShellDescriptor,
  SubmodelDescriptor
} from 'basyx-typescript-sdk';
import {
  AssetAdministrationShell,
  AssetInformation,
  AssetKind,
  Submodel,
  Entity,
  EntityType,
  SpecificAssetId,
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
    this.repositoryUrl = import.meta.env.VITE_AAS_REPOSITORY_URL || 'http://localhost:8081';
    this.shellRegistryUrl = import.meta.env.VITE_AAS_SHELL_REGISTRY_URL || 'http://localhost:8082';
    
    // Root AAS configuration
    this.rootAasId = import.meta.env.VITE_ROOT_AAS_ID ||
      'https://smartproductionlab.aau.dk/aas/aauFillingLineAAS';
    this.rootSubmodelId = import.meta.env.VITE_ROOT_SUBMODEL_ID || 
      'https://smartproductionlab.aau.dk/submodels/instances/aauFillingLineAAS/HierarchicalStructures';
    
    // Planar Table AAS configuration (default child of aauFillingLine)
    this.planarTableAasId = 'https://smartproductionlab.aau.dk/aas/planarTableAAS';
    this.planarTableHierarchicalStructuresId = 'https://smartproductionlab.aau.dk/submodels/instances/planarTableAAS/HierarchicalStructures';
    
    // SDK Clients
    this.registryClient = new AasRegistryClient();
    this.aasRepositoryClient = new AasRepositoryClient();
    this.submodelClient = new SubmodelRepositoryClient();
    
    // SDK Configurations
    this.registryConfig = new Configuration({ basePath: this.shellRegistryUrl });
    this.repositoryConfig = new Configuration({ basePath: this.repositoryUrl });
  }

  // ========================================
  // Utility Methods
  // ========================================

  /**
   * Base64 URL encode a string (for AAS/Submodel IDs in endpoints)
   * @param {string} str - The string to encode
   * @returns {string} Base64 URL encoded string
   */
  base64UrlEncode(str) {
    return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  /**
   * Create endpoint object for descriptors
   * @param {string} interfaceName - The interface name (e.g., 'AAS-3.0', 'SUBMODEL-3.0')
   * @param {string} href - The endpoint URL
   * @returns {Object} Endpoint object
   */
  createEndpoint(interfaceName, href) {
    return {
      _interface: interfaceName,
      protocolInformation: { href }
    };
  }

  /**
   * Normalize enum values to their string names
   * @param {Object} enumObj - Enum object
   * @param {string|number|null} value - Enum value
   * @returns {string|null}
   */
  normalizeEnumValue(enumObj, value) {
    if (value === null || value === undefined) return null;
    if (typeof value === 'string') return value;
    
    // aas-core3 TypeScript enums are numeric, so enumObj[numericValue] gives the string name
    // For example: ReferenceTypes[0] => "ExternalReference"
    const enumName = enumObj?.[value];
    if (typeof enumName === 'string') {
      return enumName;
    }
    
    // Fallback: if enumObj is not indexed properly, use known mappings
    // This handles ReferenceTypes specifically
    if (enumObj === ReferenceTypes) {
      const refTypeMap = {
        0: 'ExternalReference',
        1: 'ModelReference'
      };
      return refTypeMap[value] || String(value);
    }
    
    // Handle KeyTypes
    if (enumObj === KeyTypes) {
      const keyTypeMap = {
        0: 'AnnotatedRelationshipElement',
        1: 'AssetAdministrationShell',
        2: 'BasicEventElement',
        3: 'Blob',
        4: 'Capability',
        5: 'ConceptDescription',
        6: 'DataElement',
        7: 'Entity',
        8: 'EventElement',
        9: 'File',
        10: 'FragmentReference',
        11: 'GlobalReference',
        12: 'Identifiable',
        13: 'MultiLanguageProperty',
        14: 'Operation',
        15: 'Property',
        16: 'Range',
        17: 'Referable',
        18: 'ReferenceElement',
        19: 'RelationshipElement',
        20: 'Submodel',
        21: 'SubmodelElement',
        22: 'SubmodelElementCollection',
        23: 'SubmodelElementList'
      };
      return keyTypeMap[value] || String(value);
    }
    
    return String(value);
  }

  /**
   * Normalize DataTypeDefXsd to xs:* string
   * @param {string|number} valueType
   * @returns {string|null}
   */
  normalizeXsdType(valueType) {
    if (valueType === null || valueType === undefined) return null;
    if (typeof valueType === 'string') {
      if (valueType.startsWith('xs:')) return valueType;
      const mapByName = {
        String: 'xs:string',
        Float: 'xs:float',
        Int: 'xs:int',
        DateTime: 'xs:dateTime',
        Boolean: 'xs:boolean',
        Double: 'xs:double',
        Long: 'xs:long',
        Short: 'xs:short',
        Byte: 'xs:byte'
      };
      return mapByName[valueType] || valueType;
    }

    const name = this.normalizeEnumValue(DataTypeDefXsd, valueType);
    const mapByName = {
      String: 'xs:string',
      Float: 'xs:float',
      Int: 'xs:int',
      DateTime: 'xs:dateTime',
      Boolean: 'xs:boolean',
      Double: 'xs:double',
      Long: 'xs:long',
      Short: 'xs:short',
      Byte: 'xs:byte'
    };
    return mapByName[name] || name;
  }

  /**
   * Normalize Reference object to AAS JSON format (string enums)
   * @param {Object} reference
   * @returns {Object|null}
   */
  normalizeReference(reference) {
    if (!reference) return null;
    return {
      type: this.normalizeEnumValue(ReferenceTypes, reference.type),
      keys: (reference.keys || []).map(key => ({
        type: this.normalizeEnumValue(KeyTypes, key.type),
        value: key.value
      })),
      referredSemanticId: reference.referredSemanticId || null
    };
  }

  /**
   * Strip null/undefined values recursively from objects/arrays
   * @param {any} value
   * @returns {any}
   */
  stripNulls(value) {
    if (Array.isArray(value)) {
      return value
        .map(item => this.stripNulls(item))
        .filter(item => item !== undefined && item !== null);
    }

    if (value && typeof value === 'object') {
      const cleaned = {};
      Object.entries(value).forEach(([key, val]) => {
        if (val === undefined || val === null) return;
        const next = this.stripNulls(val);
        if (next === undefined || next === null) return;
        cleaned[key] = next;
      });
      return cleaned;
    }

    return value;
  }

  /**
   * Normalize SubmodelElement to AAS JSON format (string enums, modelType fields)
   * @param {Object} element
   * @returns {Object}
   */
  normalizeSubmodelElement(element) {
    if (!element) return null;

    const base = {
      extensions: element.extensions ?? null,
      idShort: element.idShort,
      displayName: element.displayName ?? null,
      category: element.category ?? null,
      description: element.description ?? null,
      semanticId: this.normalizeReference(element.semanticId),
      supplementalSemanticIds: (element.supplementalSemanticIds || null)?.map(ref => this.normalizeReference(ref)) || null,
      qualifiers: element.qualifiers ?? null,
      embeddedDataSpecifications: element.embeddedDataSpecifications ?? null
    };

    // RelationshipElement
    if (element.first && element.second) {
      return {
        modelType: 'RelationshipElement',
        ...base,
        first: this.normalizeReference(element.first),
        second: this.normalizeReference(element.second)
      };
    }

    // Entity
    if (element.entityType !== undefined || Array.isArray(element.statements)) {
      return {
        modelType: 'Entity',
        ...base,
        statements: (element.statements || []).map(el => this.normalizeSubmodelElement(el)),
        entityType: this.normalizeEnumValue(EntityType, element.entityType),
        globalAssetId: element.globalAssetId ?? null,
        specificAssetIds: element.specificAssetIds ?? null
      };
    }

    // SubmodelElementCollection
    if (Array.isArray(element.value)) {
      return {
        modelType: 'SubmodelElementCollection',
        ...base,
        value: element.value.map(el => this.normalizeSubmodelElement(el))
      };
    }

    // ReferenceElement
    if (element.value && element.value.type !== undefined && element.value.keys) {
      return {
        modelType: 'ReferenceElement',
        ...base,
        value: this.normalizeReference(element.value)
      };
    }

    // Property
    if (element.valueType !== undefined) {
      return {
        modelType: 'Property',
        ...base,
        valueType: this.normalizeXsdType(element.valueType),
        value: element.value ?? null,
        valueId: element.valueId ?? null
      };
    }

    // Fallback
    return {
      modelType: element.modelType || 'SubmodelElement',
      ...base,
      value: element.value ?? null
    };
  }

  /**
   * Normalize Submodel to AAS JSON format (string enums, modelType fields)
   * @param {Object} submodel
   * @returns {Object}
   */
  normalizeSubmodel(submodel) {
    if (!submodel) return null;
    return this.stripNulls({
      modelType: 'Submodel',
      id: submodel.id,
      idShort: submodel.idShort,
      displayName: submodel.displayName ?? null,
      category: submodel.category ?? null,
      description: submodel.description ?? null,
      administration: submodel.administration ?? null,
      kind: this.normalizeEnumValue(ModellingKind, submodel.kind) || 'Instance',
      semanticId: this.normalizeReference(submodel.semanticId),
      supplementalSemanticIds: (submodel.supplementalSemanticIds || null)?.map(ref => this.normalizeReference(ref)) || null,
      qualifiers: submodel.qualifiers ?? null,
      embeddedDataSpecifications: submodel.embeddedDataSpecifications ?? null,
      submodelElements: (submodel.submodelElements || []).map(el => this.normalizeSubmodelElement(el))
    });
  }

  /**
   * Generate a unique global asset ID using base64-encoded UUID
   * Format: https://smartproductionlab.aau.dk/assets/{base64(uuid)}
   * @param {string} uuid - The UUID to encode (if not provided, a new one should be passed)
   * @returns {string} The global asset ID URL
   */
  generateGlobalAssetId(uuid) {
    const baseUrl = 'https://smartproductionlab.aau.dk';
    const encodedUuid = this.base64UrlEncode(uuid);
    return `${baseUrl}/assets/${encodedUuid}`;
  }

  // ========================================
  // Shell Registry Operations (SDK) - Generic CRUD
  // ========================================

  /**
   * Get all AAS shell descriptors from registry
   * @returns {Promise<Array>} Array of shell descriptors
   */
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

  /**
   * Build a lookup map from AAS ID and idShort to globalAssetId
   * Fetches shell descriptors from registry and creates lookup maps
   * @returns {Promise<Object>} Object with byId and byIdShort maps
   */
  async buildGlobalAssetIdLookup() {
    try {
      const shellDescriptors = await this.getAllShells();
      const byId = {};
      const byIdShort = {};
      
      for (const descriptor of shellDescriptors) {
        if (descriptor.globalAssetId) {
          if (descriptor.id) {
            byId[descriptor.id] = descriptor.globalAssetId;
          }
          if (descriptor.idShort) {
            byIdShort[descriptor.idShort] = descriptor.globalAssetId;
            // Also map without 'AAS' suffix for convenience
            const shortName = descriptor.idShort.replace(/AAS$/i, '');
            if (shortName !== descriptor.idShort) {
              byIdShort[shortName] = descriptor.globalAssetId;
            }
          }
        }
      }
      
      return { byId, byIdShort };
    } catch (error) {
      console.error('Failed to build globalAssetId lookup:', error);
      return { byId: {}, byIdShort: {} };
    }
  }

  /**
   * Get a single AAS shell descriptor by ID
   * @param {string} aasId - The AAS identifier
   * @returns {Promise<Object>} The shell descriptor
   */
  async getShellDescriptor(aasId) {
    try {
      const result = await this.registryClient.getAssetAdministrationShellDescriptorById({
        configuration: this.registryConfig,
        aasIdentifier: aasId
      });
      
      if (result.success) {
        return result.data;
      }
      
      throw new Error(result.error?.message || 'Failed to get shell descriptor');
    } catch (error) {
      console.error(`Failed to fetch shell descriptor ${aasId}:`, error);
      throw error;
    }
  }

  /**
   * Register (create) a new AAS shell descriptor
   * @param {Object} descriptor - The AAS shell descriptor
   * @returns {Promise<Object>} The created descriptor
   */
  async postShellDescriptor(descriptor) {
    try {
      const result = await this.registryClient.postAssetAdministrationShellDescriptor({
        configuration: this.registryConfig,
        assetAdministrationShellDescriptor: descriptor
      });
      
      if (result.success) {
        return result.data || descriptor;
      }
      
      throw new Error(result.error?.message || 'Failed to register shell descriptor');
    } catch (error) {
      console.error('Failed to register shell descriptor:', error);
      throw error;
    }
  }

  /**
   * Update an existing AAS shell descriptor
   * @param {string} aasId - The AAS identifier
   * @param {Object} descriptor - The updated AAS shell descriptor
   * @returns {Promise<Object>} The updated descriptor
   */
  async putShellDescriptor(aasId, descriptor) {
    try {
      const result = await this.registryClient.putAssetAdministrationShellDescriptorById({
        configuration: this.registryConfig,
        aasIdentifier: aasId,
        assetAdministrationShellDescriptor: descriptor
      });
      
      if (result.success) {
        return result.data || descriptor;
      }
      
      throw new Error(result.error?.message || 'Failed to update shell descriptor');
    } catch (error) {
      console.error(`Failed to update shell descriptor ${aasId}:`, error);
      throw error;
    }
  }

  /**
   * Deregister (delete) an AAS shell descriptor
   * @param {string} aasId - The AAS identifier
   * @returns {Promise<boolean>} True if successful
   */
  async deleteShellDescriptor(aasId) {
    try {
      const result = await this.registryClient.deleteAssetAdministrationShellDescriptorById({
        configuration: this.registryConfig,
        aasIdentifier: aasId
      });
      
      if (result.success) {
        return true;
      }
      
      throw new Error(result.error?.message || 'Failed to delete shell descriptor');
    } catch (error) {
      console.error(`Failed to delete shell descriptor ${aasId}:`, error);
      throw error;
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
      
      // Fetch full shell details to get assetType
      const shellPromises = shellDescriptors.map(async (descriptor) => {
        const endpoint = descriptor.endpoints?.[0]?.protocolInformation?.href;
        if (endpoint) {
          const fullShell = await this.getFullShell(endpoint);
          return fullShell || descriptor;
        }
        return descriptor;
      });
      
      const shells = await Promise.all(shellPromises);
      
      // Filter to only include CPPM resources (Cyber-Physical Production Modules)
      // AssetType format: https://smartproductionlab.aau.dk/Resource/{SystemType}/{Category}/{InstanceName}
      // - CPPS: Cyber-Physical Production System (full system, exclude)
      // - CPPM: Cyber-Physical Production Module (modules, include)
      // - CPS: Cyber-Physical System (sub-parts of modules, exclude)
      const cppmShells = shells.filter(shell => {
        const assetType = shell.assetInformation?.assetType || '';
        // Only include Resource/CPPM entries
        return assetType.includes('/Resource/CPPM/');
      });
      
      // Extract module data with full AAS metadata
      const modules = cppmShells.map(shell => {
        const hierarchicalSubmodel = shell.submodels?.find(sm => 
          sm.keys?.[0]?.value?.includes('HierarchicalStructures')
        );
        
        // Extract asset information
        const assetInfo = shell.assetInformation || {};
        const assetId = assetInfo.globalAssetId || shell.id;
        const assetKind = assetInfo.assetKind || 'Instance';
        const assetTypeUrl = assetInfo.assetType || '';
        
        // Extract category from assetType URL (e.g., DispensingSystem from .../CPPM/DispensingSystem/...)
        const category = this.extractCategoryFromAssetType(assetTypeUrl);
        
        return {
          name: shell.idShort || 'Unknown Module',
          displayName: this.formatDisplayName(shell.idShort),
          aasId: shell.id,
          assetId: assetId,
          assetKind: assetKind,
          assetType: category,
          assetTypeUrl: assetTypeUrl,
          submodelId: hierarchicalSubmodel?.keys?.[0]?.value || null,
          description: shell.description?.[0]?.text || ''
        };
      });
      
      // Sort modules by category
      const categoryOrder = [
        'DispensingSystem', 'StopperingSystem', 'LoadingSystem', 
        'UnloadingSystem', 'QualityControlSystem', 'MovementSystem', 'Other'
      ];
      modules.sort((a, b) => {
        const aIndex = categoryOrder.indexOf(a.assetType);
        const bIndex = categoryOrder.indexOf(b.assetType);
        const aOrder = aIndex === -1 ? categoryOrder.length : aIndex;
        const bOrder = bIndex === -1 ? categoryOrder.length : bIndex;
        return aOrder - bOrder;
      });
      
      return modules;
    } catch (error) {
      console.error('Failed to build module catalog:', error);
      toast.error(`Failed to build module catalog: ${error.message}`);
      return [];
    }
  }

  /**
   * Extract the category from an assetType URL
   * Format: https://smartproductionlab.aau.dk/Resource/CPPM/{Category}/{InstanceName}
   * @param {string} assetTypeUrl - The full assetType URL
   * @returns {string} The category (e.g., 'DispensingSystem', 'LoadingSystem')
   */
  extractCategoryFromAssetType(assetTypeUrl) {
    if (!assetTypeUrl) return 'Other';
    
    // Match pattern: /Resource/CPPM/{Category}/
    const match = assetTypeUrl.match(/\/Resource\/CPPM\/([^\/]+)/);
    if (match && match[1]) {
      return match[1];
    }
    
    return 'Other';
  }

  /**
   * @deprecated Use extractCategoryFromAssetType instead
   * Legacy method for inferring asset type from idShort
   */
  inferAssetType(idShort) {
    if (!idShort) return 'Other';
    const lower = idShort.toLowerCase();
    
    if (lower.includes('filling') || lower.includes('dispensing')) return 'DispensingSystem';
    if (lower.includes('stoppering')) return 'StopperingSystem';
    if (lower.includes('loading') && !lower.includes('unloading')) return 'LoadingSystem';
    if (lower.includes('unloading')) return 'UnloadingSystem';
    if (lower.includes('camera')) return 'QualityControlSystem';
    if (lower.includes('planar') && !lower.includes('shuttle')) return 'MovementSystem';
    
    return 'Other';
  }

  buildCategorizedCatalog(modules) {
    // Group modules by category (extracted from assetType)
    const groupedByCategory = {};
    
    modules.forEach(module => {
      const category = module.assetType || 'Other';
      if (!groupedByCategory[category]) {
        groupedByCategory[category] = [];
      }
      groupedByCategory[category].push(module);
    });
    
    // Color map for different CPPM categories
    const categoryColors = {
      'DispensingSystem': '#1E7D74',
      'StopperingSystem': '#30A399',
      'LoadingSystem': '#0087CD',
      'UnloadingSystem': '#00A0F0',
      'QualityControlSystem': '#9B4DCA',
      'MovementSystem': '#136058',
      'Other': '#666666'
    };
    
    // Display names for categories
    const categoryDisplayNames = {
      'DispensingSystem': 'Dispensing Systems',
      'StopperingSystem': 'Stoppering Systems',
      'LoadingSystem': 'Loading Systems',
      'UnloadingSystem': 'Unloading Systems',
      'QualityControlSystem': 'Quality Control',
      'MovementSystem': 'Movement Systems',
      'Other': 'Other Modules'
    };
    
    // Build categories from grouped modules
    const categories = Object.entries(groupedByCategory).map(([category, categoryModules]) => {
      const nodes = categoryModules.map((module) => ({
        id: module.name.toLowerCase().replace(/\s+/g, '-'),
        title: module.displayName,
        color: categoryColors[category] || '#666666',
        aasId: module.aasId,
        submodelId: module.submodelId,
        assetId: module.assetId,
        assetKind: module.assetKind,
        assetType: module.assetType,
        assetTypeUrl: module.assetTypeUrl,
        abstractId: module.assetType,  // Used for MQTT topic subscription
        description: module.description
      }));
      
      return {
        id: `category-${category.toLowerCase()}`,
        name: categoryDisplayNames[category] || category,
        assetType: category,
        nodes: nodes
      };
    });
    
    // Sort categories by defined order
    const categoryOrder = [
      'DispensingSystem', 'StopperingSystem', 'LoadingSystem', 
      'UnloadingSystem', 'QualityControlSystem', 'MovementSystem', 'Other'
    ];
    categories.sort((a, b) => {
      const aIndex = categoryOrder.indexOf(a.assetType);
      const bIndex = categoryOrder.indexOf(b.assetType);
      return (aIndex === -1 ? categoryOrder.length : aIndex) - (bIndex === -1 ? categoryOrder.length : bIndex);
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
  // Repository Operations (SDK) - Generic CRUD
  // ========================================

  /**
   * Get a submodel by ID (generic)
   * @param {string} submodelId - The submodel identifier
   * @returns {Promise<Object>} The submodel data
   */
  async getSubmodel(submodelId) {
    try {
      const result = await this.submodelClient.getSubmodelById({
        configuration: this.repositoryConfig,
        submodelIdentifier: submodelId
      });
      
      if (result.success) {
        return result.data;
      }
      
      throw new Error(result.error?.message || 'Failed to get submodel');
    } catch (error) {
      console.error(`Failed to fetch submodel ${submodelId}:`, error);
      throw error;
    }
  }

  /**
   * Get a submodel by ID using raw REST (returns JSON as stored in repo)
   * @param {string} submodelId - The submodel identifier
   * @returns {Promise<Object>} The raw submodel JSON
   */
  async getSubmodelRaw(submodelId) {
    const encodedId = this.base64UrlEncode(submodelId);
    const url = `${this.repositoryUrl}/submodels/${encodedId}`;
    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json' }
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Raw GET submodel failed: ${response.status} ${text}`);
    }

    return await response.json();
  }

  /**
   * Put a submodel by ID using raw REST
   * @param {string} submodelId - The submodel identifier
   * @param {Object} submodelData - The raw submodel JSON
   * @returns {Promise<Object>} The updated submodel JSON
   */
  async putSubmodelRaw(submodelId, submodelData) {
    const encodedId = this.base64UrlEncode(submodelId);
    const url = `${this.repositoryUrl}/submodels/${encodedId}`;
    const response = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(submodelData)
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Raw PUT submodel failed: ${response.status} ${text}`);
    }

    try {
      return await response.json();
    } catch {
      return submodelData;
    }
  }

  /**
   * Post a submodel using raw REST
   * @param {Object} submodelData - The raw submodel JSON
   * @returns {Promise<Object>} The created submodel JSON
   */
  async postSubmodelRaw(submodelData) {
    const url = `${this.repositoryUrl}/submodels`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(submodelData)
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Raw POST submodel failed: ${response.status} ${text}`);
    }

    try {
      return await response.json();
    } catch {
      return submodelData;
    }
  }

  /**
   * Build a raw update payload by merging normalized payload into existing raw JSON
   * @param {string} submodelId
   * @param {Object} normalizedSubmodel
   * @returns {Promise<Object>}
   */
  async buildRawUpdatePayload(submodelId, normalizedSubmodel) {
    const existing = await this.getSubmodelRaw(submodelId);
    return {
      ...existing,
      id: normalizedSubmodel.id || existing.id,
      idShort: normalizedSubmodel.idShort || existing.idShort,
      kind: normalizedSubmodel.kind || existing.kind,
      semanticId: normalizedSubmodel.semanticId || existing.semanticId,
      displayName: normalizedSubmodel.displayName ?? existing.displayName,
      submodelElements: normalizedSubmodel.submodelElements || existing.submodelElements
    };
  }

  /**
   * Update/put a submodel by ID (generic)
   * @param {string} submodelId - The submodel identifier
   * @param {Object} submodelData - The submodel data (SDK Submodel object or JSON)
   * @returns {Promise<Object>} The updated submodel data
   */
  async putSubmodel(submodelId, submodelData) {
    try {
      console.log('putSubmodel - input submodelData:', JSON.stringify(submodelData, null, 2));
      const normalizedSubmodel = this.normalizeSubmodel(submodelData);
      console.log('putSubmodel - normalizedSubmodel:', JSON.stringify(normalizedSubmodel, null, 2));
      try {
        const rawPayload = await this.buildRawUpdatePayload(submodelId, normalizedSubmodel);
        console.log('putSubmodel - rawPayload:', JSON.stringify(rawPayload, null, 2));
        return await this.putSubmodelRaw(submodelId, rawPayload);
      } catch (rawError) {
        const rawMessage = rawError?.message || '';
        if (rawMessage.includes('404') || rawMessage.includes('ElementDoesNotExistException')) {
          return await this.postSubmodelRaw(normalizedSubmodel);
        }
        throw rawError;
      }
    } catch (error) {
      throw error;
    }
  }

  /**
   * Create a new submodel (generic)
   * @param {Object} submodelData - The submodel data (SDK Submodel object or JSON)
   * @returns {Promise<Object>} The created submodel data
   */
  async postSubmodel(submodelData) {
    try {
      const normalizedSubmodel = this.normalizeSubmodel(submodelData);
      return await this.postSubmodelRaw(normalizedSubmodel);
    } catch (error) {
      throw error;
    }
  }

  /**
   * Save or update a submodel - checks existence first to avoid 409 conflicts
   * @param {string} submodelId - The submodel identifier
   * @param {Object} submodelData - The submodel data
   * @returns {Promise<Object>} The saved submodel data
   */
  async saveOrUpdateSubmodel(submodelId, submodelData) {
    let submodelExists = false;
    
    // First check if submodel exists by listing (avoids 404 console error)
    try {
      const listResult = await this.submodelClient.getAllSubmodels({
        configuration: this.repositoryConfig
      });

      if (listResult.success && listResult.data?.result) {
         submodelExists = listResult.data.result.some(sm => sm.id === submodelId);
      } else {
         // Fallback: check directly (may cause 404)
         const existsResult = await this.submodelClient.getSubmodelById({
            configuration: this.repositoryConfig,
            submodelIdentifier: submodelId
         });
         submodelExists = existsResult.success === true;
      }
    } catch (checkError) {
      submodelExists = false;
    }
    
    if (submodelExists) {
      // Submodel exists, update it
      console.log(`Updating existing submodel: ${submodelId}`);
      const result = await this.putSubmodel(submodelId, submodelData);
      return result;
    }
    
    // Create new submodel using raw method for better error messages
    console.log(`Creating new submodel: ${submodelId}`);
    try {
      // If submodel already has modelType, it's pre-normalized JSON - use as-is
      // Otherwise normalize from SDK types to JSON
      const submodelJson = submodelData.modelType === 'Submodel' 
        ? submodelData 
        : this.normalizeSubmodel(submodelData);
      
      console.log('Posting submodel JSON:', JSON.stringify(submodelJson, null, 2));
      const result = await this.postSubmodelRaw(submodelJson);
      console.log(`Successfully created submodel: ${submodelId}`);
      return result;
    } catch (createError) {
      console.error(`Failed to create submodel ${submodelId}:`, createError);
      throw createError;
    }
  }

  /**
   * Create a submodel descriptor for registry registration
   * @param {string} submodelId - The submodel identifier
   * @param {Object} submodel - Optional submodel object for additional metadata
   * @returns {SubmodelDescriptor} The descriptor object
   */
  createSubmodelDescriptor(submodelId, submodel = null) {
    const encodedId = this.base64UrlEncode(submodelId);
    const endpoint = this.createEndpoint('SUBMODEL-3.0', `${this.repositoryUrl}/submodels/${encodedId}`);
    
    return new SubmodelDescriptor(
      submodelId,
      [endpoint],
      submodel?.idShort ?? null,
      submodel?.description ?? null,
      submodel?.displayName ?? null,
      submodel?.semanticId ?? null,
      submodel?.administration ?? null
    );
  }

  /**
   * Register submodel descriptors for an AAS in the registry
   * @param {string} aasId - The AAS identifier
   * @param {Array} submodelIds - Array of submodel IDs to register
   */
  async registerSubmodelDescriptors(aasId, submodelIds) {
    for (const submodelId of submodelIds) {
      try {
        const descriptor = this.createSubmodelDescriptor(submodelId);
        console.log(`Registering submodel descriptor: ${submodelId}`);
        
        const result = await this.registryClient.postSubmodelDescriptorThroughSuperpath({
          configuration: this.registryConfig,
          aasIdentifier: aasId,
          submodelDescriptor: descriptor
        });
        
        if (result.success) {
          console.log(`Successfully registered submodel descriptor: ${submodelId}`);
        } else {
          console.warn(`Failed to register submodel descriptor: ${result.error?.message}`);
        }
      } catch (error) {
        console.warn(`Submodel descriptor registration warning for ${submodelId}:`, error.message);
      }
    }
  }

  /**
   * Delete a submodel by ID (generic)
   * @param {string} submodelId - The submodel identifier
   * @returns {Promise<boolean>} True if successful
   */
  async deleteSubmodel(submodelId) {
    try {
      const result = await this.submodelClient.deleteSubmodelById({
        configuration: this.repositoryConfig,
        submodelIdentifier: submodelId
      });
      
      if (result.success) {
        return true;
      }
      
      throw new Error(result.error?.message || 'Failed to delete submodel');
    } catch (error) {
      console.error(`Failed to delete submodel ${submodelId}:`, error);
      throw error;
    }
  }

  /**
   * Get all submodels from the repository
   * @returns {Promise<Array>} Array of submodels
   */
  async getAllSubmodels() {
    try {
      const result = await this.submodelClient.getAllSubmodels({
        configuration: this.repositoryConfig
      });
      
      if (result.success && result.data?.result) {
        return result.data.result;
      }
      
      console.error('Failed to get submodels:', result.error);
      return [];
    } catch (error) {
      console.error('Failed to fetch submodels:', error);
      return [];
    }
  }

  // ========================================
  // Convenience methods with toast notifications
  // ========================================

  async getHierarchicalStructures(submodelId = null) {
    try {
      const id = submodelId || this.rootSubmodelId;
      return await this.getSubmodel(id);
    } catch (error) {
      toast.error(`Failed to load configuration: ${error.message}`);
      throw error;
    }
  }

  async putHierarchicalStructures(submodelData, submodelId = null) {
    try {
      const id = submodelId || this.rootSubmodelId;
      const result = await this.putSubmodel(id, submodelData);
      toast.success('Configuration saved to AAS successfully!');
      return result;
    } catch (error) {
      toast.error(`Failed to save configuration: ${error.message}`);
      throw error;
    }
  }

  // ========================================
  // Planar Table Parameters Operations
  // ========================================

  /**
   * Planar Table AAS and Parameters submodel IDs
   * globalAssetId from registry: base64-encoded UUID format
   */
  get planarTableAssetId() {
    // Correct globalAssetId from BaSyx registry (base64-encoded UUID)
    return 'https://smartproductionlab.aau.dk/assets/ZTM1NTAzNzQtMDZkNi00N2Q4LWI1YTktMGNhMmY0MDEyNTk4';
  }

  get planarTableParametersSubmodelId() {
    return 'https://smartproductionlab.aau.dk/submodels/instances/planarTableAAS/Parameters';
  }

  /**
   * Get planar table motor configuration from Parameters submodel
   * @returns {Promise<Object>} Motor config with velocity/acceleration limits
   */
  async getPlanarTableMotorConfig() {
    try {
      const parametersSubmodel = await this.getSubmodel(this.planarTableParametersSubmodelId);
      return this.extractMotorConfigFromParameters(parametersSubmodel);
    } catch (error) {
      console.error('Failed to get planar table motor config:', error);
      // Return default config if submodel doesn't exist or is empty
      return {
        maxSpeedX: '5.0',
        maxSpeedY: '5.0',
        maxSpeedRz: '10.0',
        maxAccelX: '2.0',
        maxAccelY: '2.0',
        maxAccelRz: '5.0'
      };
    }
  }

  /**
   * Save planar table motor configuration to Parameters submodel
   * @param {Object} motorConfig - Motor configuration with velocity/acceleration limits
   * @returns {Promise<Object>} The updated submodel
   */
  async putPlanarTableMotorConfig(motorConfig) {
    try {
      // Create the Parameters submodel with velocity and acceleration limits
      const parametersSubmodel = this.createParametersSubmodel(motorConfig);
      const result = await this.putSubmodel(this.planarTableParametersSubmodelId, parametersSubmodel);
      toast.success('Motor configuration saved to planarTable AAS!');
      return result;
    } catch (error) {
      toast.error(`Failed to save motor configuration: ${error.message}`);
      throw error;
    }
  }

  /**
   * Extract motor config from a Parameters submodel
   */
  extractMotorConfigFromParameters(parametersSubmodel) {
    const submodelElements = parametersSubmodel?.submodelElements || [];
    
    // Find Velocity and Acceleration collections
    const velocityCollection = submodelElements.find(
      el => el.idShort === 'Velocity' && 
            (el.modelType === 'SubmodelElementCollection' || el.value)
    );
    
    const accelerationCollection = submodelElements.find(
      el => el.idShort === 'Acceleration' && 
            (el.modelType === 'SubmodelElementCollection' || el.value)
    );
    
    const velocityValues = velocityCollection?.value || [];
    const accelerationValues = accelerationCollection?.value || [];
    
    return {
      maxSpeedX: velocityValues.find(p => p.idShort === 'x')?.value || '5.0',
      maxSpeedY: velocityValues.find(p => p.idShort === 'y')?.value || '5.0',
      maxSpeedRz: velocityValues.find(p => p.idShort === 'Rz')?.value || '10.0',
      maxAccelX: accelerationValues.find(p => p.idShort === 'x')?.value || '2.0',
      maxAccelY: accelerationValues.find(p => p.idShort === 'y')?.value || '2.0',
      maxAccelRz: accelerationValues.find(p => p.idShort === 'Rz')?.value || '5.0'
    };
  }

  /**
   * Create a Parameters submodel with motor config
   */
  createParametersSubmodel(motorConfig) {
    const velocityLimits = this.createVelocityLimits(
      motorConfig.maxSpeedX,
      motorConfig.maxSpeedY,
      motorConfig.maxSpeedRz
    );
    
    const accelerationLimits = this.createAccelerationLimits(
      motorConfig.maxAccelX,
      motorConfig.maxAccelY,
      motorConfig.maxAccelRz
    );
    
    const parametersSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/Parameters/1/0/Submodel')]
    );
    
    return this.createSubmodel(
      this.planarTableParametersSubmodelId,
      'Parameters',
      [velocityLimits, accelerationLimits],
      parametersSemanticId
    );
  }

  // ========================================
  // Product AAS Operations
  // ========================================

  /**
   * AAS Role enumeration values
   */
  static AAS_ROLES = {
    PRODUCT: 'Product',
    PROCESS: 'Process',
    RESOURCE: 'Resource'
  };

  /**
   * Generate product AAS and submodel IDs from order UUID
   * @param {string} orderUuid - The order UUID
   * @param {string} productFamily - The product family (e.g., 'Monoclonal Antibodies', 'Growth Hormones')
   * @param {string} productName - The product name (e.g., 'MIM8', 'HgH')
   */
  getProductAasIds(orderUuid, productFamily = null, productName = null) {
    const baseUrl = 'https://smartproductionlab.aau.dk';
    const sanitizedFamily = productFamily ? productFamily.toLowerCase().replace(/\s+/g, '-') : 'unknown';
    const sanitizedProduct = productName ? productName.replace(/\s+/g, '') : 'unknown';
    // idShort includes AAS suffix, used in submodel paths
    const idShort = `products/${orderUuid}AAS`;
    return {
      aasId: `${baseUrl}/aas/${idShort}`,
      assetId: this.generateGlobalAssetId(orderUuid),
      // AssetType uses ontology URL structure: role/category/specific-type/product
      assetType: `${baseUrl}/product/productFamily/${sanitizedFamily}/${sanitizedProduct}`,
      batchInfoSubmodelId: `${baseUrl}/submodels/instances/${idShort}/BatchInformation`,
      requirementsSubmodelId: `${baseUrl}/submodels/instances/${idShort}/Requirements`,
      billOfMaterialsSubmodelId: `${baseUrl}/submodels/instances/${idShort}/HierarchicalStructures`,
      billOfProcessesSubmodelId: `${baseUrl}/submodels/instances/${idShort}/BillOfProcesses`
    };
  }

  /**
   * Create a complete Product AAS with all submodels
   * @param {Object} batchData - The batch configuration data
   * @returns {Object} Object containing the AAS and all submodels
   */
  createProductAas(batchData) {
    const productFamily = batchData.productFamily || batchData.product;
    const productName = batchData.product;
    const ids = this.getProductAasIds(batchData.Uuid, productFamily, productName);
    
    // Create all submodels
    const batchInfoSubmodel = this.createBatchInformationSubmodel(batchData, ids.batchInfoSubmodelId);
    const requirementsSubmodel = this.createRequirementsSubmodel(batchData, ids.requirementsSubmodelId);
    const billOfMaterialsSubmodel = this.createBillOfMaterialsSubmodel(batchData, ids.billOfMaterialsSubmodelId);
    const billOfProcessesSubmodel = this.createBillOfProcessesSubmodel(batchData, ids.billOfProcessesSubmodelId);
    
    return {
      ids,
      submodels: {
        batchInfo: batchInfoSubmodel,
        requirements: requirementsSubmodel,
        billOfMaterials: billOfMaterialsSubmodel,
        billOfProcesses: billOfProcessesSubmodel
      }
    };
  }

  /**
   * Create BatchInformation submodel
   */
  createBatchInformationSubmodel(batchData, submodelId) {
    const semanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/BatchInformation/1/0')]
    );
    
    const elements = [
      // Product identification
      this.createProperty('ProductName', batchData.product || '', DataTypeDefXsd.String,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/zvei/nameplate/2/0/Nameplate/ProductName')]
        )
      ),
      this.createProperty('ProductFamily', batchData.productFamily || batchData.product || '', DataTypeDefXsd.String,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/zvei/nameplate/2/0/Nameplate/ProductFamily')]
        )
      ),
      // Order information
      this.createProperty('OrderNumber', batchData.Uuid || '', DataTypeDefXsd.String,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/OrderNumber')]
        )
      ),
      this.createProperty('OrderTimestamp', batchData.orderTimestamp || new Date().toISOString(), DataTypeDefXsd.DateTime,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/OrderTimestamp')]
        )
      ),
      // Quantity and packaging
      this.createProperty('Quantity', parseInt(batchData.volume) || 0, DataTypeDefXsd.Int,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/Quantity')]
        )
      ),
      this.createProperty('Packaging', batchData.packaging || '', DataTypeDefXsd.String,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/Packaging')]
        )
      ),
      // Batch status
      this.createProperty('Status', batchData.status || 'Pending', DataTypeDefXsd.String,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/BatchStatus')]
        )
      )
    ];
    
    return this.createSubmodel(submodelId, 'BatchInformation', elements, semanticId);
  }

  /**
   * Create Requirements submodel with production parameters
   */
  createRequirementsSubmodel(batchData, submodelId) {
    const semanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/ProductionRequirements/1/0')]
    );
    
    // Environmental requirements collection
    const environmentalElements = [
      this.createProperty('Temperature', parseFloat(batchData.productionTemperature) || 22.0, DataTypeDefXsd.Float,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/ProductionTemperature')]
        )
      ),
      this.createProperty('TemperatureUnit', '°C', DataTypeDefXsd.String),
      this.createProperty('Humidity', parseFloat(batchData.humidity) || 45.0, DataTypeDefXsd.Float,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/Humidity')]
        )
      ),
      this.createProperty('HumidityUnit', '%RH', DataTypeDefXsd.String)
    ];
    
    const environmentalCollection = this.createSubmodelElementCollection(
      'EnvironmentalRequirements',
      environmentalElements,
      this.createReference(ReferenceTypes.ExternalReference,
        [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/EnvironmentalRequirements')]
      )
    );
    
    // In-Process Control requirements collection
    const ipcElements = [
      this.createProperty('IPCInspection', parseFloat(batchData.ipcInspection) || 0, DataTypeDefXsd.Float,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/IPCInspection')]
        )
      ),
      this.createProperty('IPCInspectionUnit', '%', DataTypeDefXsd.String),
      this.createProperty('IPCWeighing', parseFloat(batchData.ipcWeighing) || 0, DataTypeDefXsd.Float,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/IPCWeighing')]
        )
      ),
      this.createProperty('IPCWeighingUnit', '%', DataTypeDefXsd.String)
    ];
    
    const ipcCollection = this.createSubmodelElementCollection(
      'InProcessControls',
      ipcElements,
      this.createReference(ReferenceTypes.ExternalReference,
        [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/InProcessControls')]
      )
    );
    
    // Quality Control requirements collection
    const qcElements = [
      this.createProperty('QCSamples', parseInt(batchData.qcCount) || 0, DataTypeDefXsd.Int,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/QCSamples')]
        )
      )
    ];
    
    const qcCollection = this.createSubmodelElementCollection(
      'QualityControl',
      qcElements,
      this.createReference(ReferenceTypes.ExternalReference,
        [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/QualityControl')]
      )
    );
    
    const elements = [environmentalCollection, ipcCollection, qcCollection];
    
    return this.createSubmodel(submodelId, 'Requirements', elements, semanticId);
  }

  /**
   * Create BillOfMaterials submodel based on HierarchicalStructures template (IDTA 02011-1-1)
   */
  createBillOfMaterialsSubmodel(batchData, submodelId) {
    // Use official IDTA 02011-1-1 semantic ID for HierarchicalStructures submodel
    const semanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel')]
    );
    
    // Create ArcheType property (note: IDTA uses "ArcheType" spelling)
    const archetypeSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/ArcheType/1/0')]
    );
    const archetypeProperty = this.createProperty('ArcheType', 'OneDown', DataTypeDefXsd.String, archetypeSemanticId);
    
    // Create material entities based on packaging type (as separate entities)
    const materialEntities = this.createMaterialEntities(batchData);
    
    // Create EntryNode for the product (IDTA 02011-1-1)
    const entryNodeSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/EntryNode/1/0')]
    );
    
    const productFamily = batchData.productFamily || batchData.product;
    const productAssetId = this.getProductAasIds(batchData.Uuid, productFamily).assetId;
    
    // Product entity without nested children - relationships define the hierarchy
    const entryNode = this.createEntity(
      'Product',
      EntityType.SelfManagedEntity,
      productAssetId,
      [], // No nested statements - use relationships instead
      entryNodeSemanticId
    );
    
    // Create relationships for bill of materials using flat structure
    const relationships = materialEntities.map(material => {
      return this.createFlatBillOfMaterialsRelationship(
        `Has${material.idShort}`,
        submodelId,
        'Product',
        material.idShort
      );
    });
    
    // All entities are direct children of submodel, relationships define hierarchy
    const elements = [archetypeProperty, entryNode, ...materialEntities, ...relationships];
    
    return this.createSubmodel(submodelId, 'HierarchicalStructures', elements, semanticId, 'BillOfMaterials');
  }

  /**
   * Create material entities based on batch data (IDTA 02011-1-1 Node elements)
   */
  createMaterialEntities(batchData) {
    const materials = [];
    // Use official IDTA 02011-1-1 Node semantic ID
    const nodeSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/Node/1/0')]
    );
    
    // Primary container (cartridge/syringe)
    const containerType = batchData.packaging?.includes('Cartridge') ? 'Cartridge' : 'Syringe';
    const containerVolume = batchData.packaging?.match(/\d+(\.\d+)?mL/)?.[0] || '3mL';
    
    const containerProps = [
      this.createProperty('Type', containerType, DataTypeDefXsd.String),
      this.createProperty('Volume', containerVolume, DataTypeDefXsd.String),
      this.createProperty('Quantity', parseInt(batchData.volume) || 0, DataTypeDefXsd.Int)
    ];
    
    const containerCollection = this.createSubmodelElementCollection('Specifications', containerProps);
    
    materials.push(this.createEntity(
      'PrimaryContainer',
      EntityType.CoManagedEntity,
      null,
      [containerCollection],
      nodeSemanticId
    ));
    
    // Stopper
    const stopperProps = [
      this.createProperty('Type', 'Rubber Stopper', DataTypeDefXsd.String),
      this.createProperty('Quantity', parseInt(batchData.volume) || 0, DataTypeDefXsd.Int)
    ];
    
    const stopperCollection = this.createSubmodelElementCollection('Specifications', stopperProps);
    
    materials.push(this.createEntity(
      'Stopper',
      EntityType.CoManagedEntity,
      null,
      [stopperCollection],
      nodeSemanticId
    ));
    
    // Drug substance (API)
    const apiProps = [
      this.createProperty('Name', batchData.product || 'Unknown', DataTypeDefXsd.String),
      this.createProperty('Type', 'Active Pharmaceutical Ingredient', DataTypeDefXsd.String)
    ];
    
    const apiCollection = this.createSubmodelElementCollection('Specifications', apiProps);
    
    materials.push(this.createEntity(
      'DrugSubstance',
      EntityType.CoManagedEntity,
      null,
      [apiCollection],
      nodeSemanticId
    ));
    
    return materials;
  }

  /**
   * Create relationship for bill of materials using IDTA 02011-1-1 HasPart semantic
   * HasPart: first = parent entity, second = child entity (parent has part child)
   */
  createBillOfMaterialsRelationship(idShort, submodelId, parentId, childId, aasId = null) {
    // AASd-125 compliant: First key is AasIdentifiable (Submodel),
    // subsequent keys are FragmentKeys (Entity)
    // First reference points to the parent entity
    const firstRef = this.createReference(
      ReferenceTypes.ModelReference,
      [
        this.createKey(KeyTypes.Submodel, submodelId),
        this.createKey(KeyTypes.Entity, parentId)
      ]
    );
    
    // Second reference points to the child entity (nested under parent)
    const secondRef = this.createReference(
      ReferenceTypes.ModelReference,
      [
        this.createKey(KeyTypes.Submodel, submodelId),
        this.createKey(KeyTypes.Entity, parentId),
        this.createKey(KeyTypes.Entity, childId)
      ]
    );
    
    // Use official IDTA 02011-1-1 HasPart semantic ID
    const semanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/HasPart/1/0')]
    );
    
    return this.createRelationshipElement(idShort, firstRef, secondRef, semanticId);
  }

  // ========================================
  // Bill of Processes Submodel (IDTA BoP pattern)
  // Structure: BoP(SM) → Processes(SML) → Process(SMC) → Properties & nested SMCs
  // ========================================

  /**
   * Standard semantic IDs from ECLASS and custom definitions
   */
  static BOP_SEMANTIC_IDS = {
    // Submodel
    BILL_OF_PROCESS: 'https://admin-shell.io/idta/BillOfProcess/1/0',
    
    // ECLASS property semantic IDs
    DURATION: '0173-1#02-AAB381#003',           // Duration
    VOLUME: '0173-1#02-AAB713#004',             // Volume
    FLOW_RATE: '0173-1#02-AAK230#002',          // Flow rate
    FORCE: '0173-1#02-AAB930#005',              // Force
    TEMPERATURE: '0173-1#02-AAB048#003',        // Temperature
    HUMIDITY: '0173-1#02-AAB046#003',           // Relative humidity
    ACCURACY: '0173-1#02-AAI836#002',           // Accuracy
    RESOLUTION: '0173-1#02-AAB991#004',         // Resolution
    FREQUENCY: '0173-1#02-AAB942#004',          // Frequency
    STANDARD_COMPLIANCE: '0173-1#02-AAQ325#001', // Standard compliance
    
    // ECLASS unit semantic IDs
    UNIT_MILLILITRE: '0173-1#05-AAA689#002',
    UNIT_CELSIUS: '0173-1#05-AAA567#002',
    UNIT_SECOND: '0173-1#05-AAA153#002',
    
    // Custom capability semantic IDs
    CAPABILITY_LOADING: 'https://smartproductionlab.aau.dk/Capability/Loading',
    CAPABILITY_DISPENSING: 'https://smartproductionlab.aau.dk/Capability/Dispensing',
    CAPABILITY_STOPPERING: 'https://smartproductionlab.aau.dk/Capability/Stoppering',
    CAPABILITY_QC: 'https://smartproductionlab.aau.dk/Capability/QualityControl',
    CAPABILITY_UNLOADING: 'https://smartproductionlab.aau.dk/Capability/Unloading',
    CAPABILITY_WEIGHING: 'https://smartproductionlab.aau.dk/Capability/Weighing',
    CAPABILITY_SCRAPING: 'https://smartproductionlab.aau.dk/Capability/Scraping'
  };

  /**
   * Create Bill of Processes submodel
   * @param {Object} batchData - Batch configuration data
   * @param {string} submodelId - The submodel ID
   * @returns {Object} The BillOfProcesses submodel - Pure JSON, no SDK types
   */
  createBillOfProcessesSubmodel(batchData, submodelId) {
    // Create a simple Bill of Processes submodel using plain JSON
    // This avoids SDK enum serialization issues
    const fillVolume = this.extractFillVolume(batchData);
    
    // ECLASS and standard semantic IDs for physical quantities
    const SEM = {
      // Physical quantities (ECLASS)
      FORCE: '0173-1#02-AAB930#005',
      ACCURACY: '0173-1#02-AAI836#002',
      VOLUME: '0173-1#02-AAB713#004',
      FLOW_RATE: '0173-1#02-AAK230#002',
      TEMPERATURE: '0173-1#02-AAB048#003',
      SPEED: '0173-1#02-AAB966#004',
      RESOLUTION: '0173-1#02-AAB991#004',
      TIME: '0173-1#02-AAB381#003',
      FREQUENCY: '0173-1#02-AAK299#003',
      LENGTH: '0173-1#02-AAB001#006',
      // Abstract Process types (semantic ID for Process SMC)
      PROC_LOADING: 'https://smartproductionlab.aau.dk/Process/Loading',
      PROC_DISPENSING: 'https://smartproductionlab.aau.dk/Process/Dispensing',
      PROC_STOPPERING: 'https://smartproductionlab.aau.dk/Process/Stoppering',
      PROC_INSPECTION: 'https://smartproductionlab.aau.dk/Process/Inspection',
      PROC_UNLOADING: 'https://smartproductionlab.aau.dk/Process/Unloading',
      // Capabilities (linked inside Process SMC)
      CAP_LOADING: 'https://smartproductionlab.aau.dk/Capability/Loading',
      CAP_DISPENSING: 'https://smartproductionlab.aau.dk/Capability/Dispensing',
      CAP_STOPPERING: 'https://smartproductionlab.aau.dk/Capability/Stoppering',
      CAP_QC: 'https://smartproductionlab.aau.dk/Capability/QualityControl',
      CAP_UNLOADING: 'https://smartproductionlab.aau.dk/Capability/Unloading',
      // Container semantic IDs
      PROCESSES_LIST: 'https://smartproductionlab.aau.dk/Processes',
      PROCESS: 'https://smartproductionlab.aau.dk/Process'
    };

    // UNECE unit codes for proper unit representation
    const UNIT = {
      NEWTON: 'N',           // Force
      MILLIMETER: 'mm',      // Length
      MILLILITER: 'mL',      // Volume (MLT)
      ML_PER_SEC: 'mL/s',    // Flow rate
      CELSIUS: '°C',         // Temperature (CEL)
      MM_PER_SEC: 'mm/s',    // Speed
      MEGAPIXEL: 'MP',       // Resolution
      MILLISECOND: 'ms',     // Time
      SECOND: 's',           // Time (SEC)
      PERCENT: '%'           // Percentage (P1)
    };

    return {
      modelType: 'Submodel',
      id: submodelId,
      idShort: 'BillOfProcesses',
      kind: 'Instance',
      semanticId: {
        type: 'ExternalReference',
        keys: [{ type: 'GlobalReference', value: 'https://admin-shell.io/idta/BillOfProcess/1/0' }]
      },
      submodelElements: [
        {
          modelType: 'SubmodelElementList',
          idShort: 'Processes',
          orderRelevant: true,
          semanticId: {
            type: 'ExternalReference',
            keys: [{ type: 'GlobalReference', value: SEM.PROCESSES_LIST }]
          },
          semanticIdListElement: {
            type: 'ExternalReference',
            keys: [{ type: 'GlobalReference', value: SEM.PROCESS }]
          },
          typeValueListElement: 'SubmodelElementCollection',
          value: [
            // Process 1: Loading
            this.createProcessSMC('Loading', SEM.PROC_LOADING, SEM.CAP_LOADING, 5.0, 
              'Load empty primary container onto production shuttle', {
              parameters: [
                { name: 'GripForce', value: '10', unit: UNIT.NEWTON, type: 'xs:double', semanticId: SEM.FORCE }
              ],
              requirements: [
                { 
                  name: 'PositionAccuracy', 
                  value: '0.5', 
                  unit: UNIT.MILLIMETER, 
                  type: 'xs:double', 
                  semanticId: SEM.ACCURACY,
                  assessment: { method: 'sensor', sensor: 'EncoderFeedback', standard: 'ISO 230-2' }
                }
              ]
            }),
            // Process 2: Dispensing
            this.createProcessSMC('Dispensing', SEM.PROC_DISPENSING, SEM.CAP_DISPENSING, 8.0, 
              `Dispense ${fillVolume}mL pharmaceutical product into container`, {
              parameters: [
                { name: 'FillVolume', value: String(fillVolume), unit: UNIT.MILLILITER, type: 'xs:double', semanticId: SEM.VOLUME },
                { name: 'FlowRate', value: '1.0', unit: UNIT.ML_PER_SEC, type: 'xs:double', semanticId: SEM.FLOW_RATE },
                { name: 'Temperature', value: '20', unit: UNIT.CELSIUS, type: 'xs:double', semanticId: SEM.TEMPERATURE }
              ],
              requirements: [
                { 
                  name: 'VolumeAccuracy', 
                  value: '0.05', 
                  unit: UNIT.MILLILITER, 
                  type: 'xs:double', 
                  semanticId: SEM.ACCURACY,
                  assessment: { method: 'sensor', sensor: 'GravimetricBalance', standard: 'USP <1251>' }
                },
                { 
                  name: 'Sterility', 
                  value: 'compliant', 
                  type: 'xs:string',
                  assessment: { method: 'guideline', standard: 'ISO 13408-1', verification: 'EnvironmentalMonitoring' }
                }
              ]
            }),
            // Process 3: Stoppering
            this.createProcessSMC('Stoppering', SEM.PROC_STOPPERING, SEM.CAP_STOPPERING, 3.0, 
              'Insert elastomeric stopper to seal primary container', {
              parameters: [
                { name: 'InsertionForce', value: '50', unit: UNIT.NEWTON, type: 'xs:double', semanticId: SEM.FORCE },
                { name: 'InsertionSpeed', value: '10', unit: UNIT.MM_PER_SEC, type: 'xs:double', semanticId: SEM.SPEED }
              ],
              requirements: [
                { 
                  name: 'SealIntegrity', 
                  value: 'pass', 
                  type: 'xs:string',
                  assessment: { method: 'inspection', inspection: 'ContainerClosureIntegrity', standard: 'USP <1207>' }
                },
                { 
                  name: 'InsertionForceMax', 
                  value: '80', 
                  unit: UNIT.NEWTON, 
                  type: 'xs:double', 
                  semanticId: SEM.FORCE,
                  assessment: { method: 'sensor', sensor: 'ForceSensor', tolerance: '±10N' }
                }
              ]
            }),
            // Process 4: Inspection
            this.createProcessSMC('Inspection', SEM.PROC_INSPECTION, SEM.CAP_QC, 2.0, 
              'Automated visual inspection of filled and stoppered container', {
              parameters: [
                { name: 'CameraResolution', value: '5', unit: UNIT.MEGAPIXEL, type: 'xs:double', semanticId: SEM.RESOLUTION },
                { name: 'ExposureTime', value: '10', unit: UNIT.MILLISECOND, type: 'xs:double', semanticId: SEM.TIME },
                { name: 'FrameRate', value: '30', unit: 'fps', type: 'xs:int', semanticId: SEM.FREQUENCY }
              ],
              requirements: [
                { 
                  name: 'DefectDetectionSize', 
                  value: '0.1', 
                  unit: UNIT.MILLIMETER, 
                  type: 'xs:double', 
                  semanticId: SEM.LENGTH,
                  assessment: { method: 'inspection', inspection: 'MachineVision', standard: 'ISO 21570' }
                },
                { 
                  name: 'PassRate', 
                  value: '99.5', 
                  unit: UNIT.PERCENT, 
                  type: 'xs:double',
                  assessment: { method: 'statistical', verification: 'SPC', confidence: '95%' }
                },
                { 
                  name: 'ParticulateMatter', 
                  value: 'compliant', 
                  type: 'xs:string',
                  assessment: { method: 'guideline', standard: 'USP <788>', verification: 'VisualInspection' }
                }
              ]
            }),
            // Process 5: Unloading
            this.createProcessSMC('Unloading', SEM.PROC_UNLOADING, SEM.CAP_UNLOADING, 4.0, 
              'Transfer finished product from shuttle to output conveyor', {
              parameters: [
                { name: 'GripForce', value: '8', unit: UNIT.NEWTON, type: 'xs:double', semanticId: SEM.FORCE }
              ],
              requirements: [
                { 
                  name: 'PlacementAccuracy', 
                  value: '1.0', 
                  unit: UNIT.MILLIMETER, 
                  type: 'xs:double', 
                  semanticId: SEM.ACCURACY,
                  assessment: { method: 'sensor', sensor: 'VisionSystem', standard: 'ISO 9283' }
                }
              ]
            })
          ]
        }
      ]
    };
  }

  /**
   * Create a Process SMC with semantic IDs and assessment criteria
   * @param {string} name - Process name (idShort)
   * @param {string} processSemanticId - Semantic ID for the abstract process type
   * @param {string} capabilitySemanticId - Semantic ID for the required capability
   * @param {number} duration - Estimated duration in seconds
   * @param {string} description - Process description
   * @param {Object} options - Parameters and requirements with semantic IDs
   */
  createProcessSMC(name, processSemanticId, capabilitySemanticId, duration, description, options = {}) {
    const elements = [
      {
        modelType: 'Property',
        idShort: 'Description',
        valueType: 'xs:string',
        value: description
      },
      {
        modelType: 'Property',
        idShort: 'EstimatedDuration',
        valueType: 'xs:double',
        value: String(duration),
        semanticId: {
          type: 'ExternalReference',
          keys: [{ type: 'GlobalReference', value: '0173-1#02-AAB381#003' }]
        },
        qualifiers: [{ type: 'Unit', valueType: 'xs:string', value: 's' }]
      },
      {
        modelType: 'ReferenceElement',
        idShort: 'RequiredCapability',
        value: {
          type: 'ExternalReference',
          keys: [{ type: 'GlobalReference', value: capabilitySemanticId }]
        }
      }
    ];

    // Add Parameters SMC if provided
    if (options.parameters && options.parameters.length > 0) {
      elements.push({
        modelType: 'SubmodelElementCollection',
        idShort: 'Parameters',
        value: options.parameters.map(p => this.createParameterProperty(p))
      });
    }

    // Add Requirements SMC if provided
    if (options.requirements && options.requirements.length > 0) {
      elements.push({
        modelType: 'SubmodelElementCollection',
        idShort: 'Requirements',
        value: options.requirements.map(r => this.createRequirementSMC(r))
      });
    }

    return {
      modelType: 'SubmodelElementCollection',
      idShort: name,
      semanticId: {
        type: 'ExternalReference',
        keys: [{ type: 'GlobalReference', value: processSemanticId }]
      },
      value: elements
    };
  }

  /**
   * Create a Parameter Property with semantic ID and unit
   */
  createParameterProperty(param) {
    const prop = {
      modelType: 'Property',
      idShort: param.name,
      valueType: param.type,
      value: param.value
    };

    if (param.semanticId) {
      prop.semanticId = {
        type: 'ExternalReference',
        keys: [{ type: 'GlobalReference', value: param.semanticId }]
      };
    }

    if (param.unit) {
      prop.qualifiers = [{ type: 'Unit', valueType: 'xs:string', value: param.unit }];
    }

    return prop;
  }

  /**
   * Create a Requirement SMC with value, assessment criteria, and semantic ID
   * Assessment can include: method, sensor, inspection, standard, verification, tolerance
   */
  createRequirementSMC(req) {
    const elements = [
      {
        modelType: 'Property',
        idShort: 'Value',
        valueType: req.type,
        value: req.value,
        ...(req.unit ? { qualifiers: [{ type: 'Unit', valueType: 'xs:string', value: req.unit }] } : {}),
        ...(req.semanticId ? {
          semanticId: {
            type: 'ExternalReference',
            keys: [{ type: 'GlobalReference', value: req.semanticId }]
          }
        } : {})
      }
    ];

    // Add assessment criteria if provided
    if (req.assessment) {
      const assessmentElements = [];
      
      // Assessment method (sensor, inspection, guideline, statistical)
      if (req.assessment.method) {
        assessmentElements.push({
          modelType: 'Property',
          idShort: 'Method',
          valueType: 'xs:string',
          value: req.assessment.method
        });
      }

      // Sensor name for sensor-based assessment
      if (req.assessment.sensor) {
        assessmentElements.push({
          modelType: 'Property',
          idShort: 'Sensor',
          valueType: 'xs:string',
          value: req.assessment.sensor
        });
      }

      // Inspection type for inspection-based assessment
      if (req.assessment.inspection) {
        assessmentElements.push({
          modelType: 'Property',
          idShort: 'InspectionType',
          valueType: 'xs:string',
          value: req.assessment.inspection
        });
      }

      // Standard reference (ISO, USP, etc.)
      if (req.assessment.standard) {
        assessmentElements.push({
          modelType: 'Property',
          idShort: 'Standard',
          valueType: 'xs:string',
          value: req.assessment.standard
        });
      }

      // Verification method
      if (req.assessment.verification) {
        assessmentElements.push({
          modelType: 'Property',
          idShort: 'Verification',
          valueType: 'xs:string',
          value: req.assessment.verification
        });
      }

      // Tolerance specification
      if (req.assessment.tolerance) {
        assessmentElements.push({
          modelType: 'Property',
          idShort: 'Tolerance',
          valueType: 'xs:string',
          value: req.assessment.tolerance
        });
      }

      // Confidence level for statistical methods
      if (req.assessment.confidence) {
        assessmentElements.push({
          modelType: 'Property',
          idShort: 'Confidence',
          valueType: 'xs:string',
          value: req.assessment.confidence
        });
      }

      elements.push({
        modelType: 'SubmodelElementCollection',
        idShort: 'Assessment',
        value: assessmentElements
      });
    }

    return {
      modelType: 'SubmodelElementCollection',
      idShort: req.name,
      ...(req.semanticId ? {
        semanticId: {
          type: 'ExternalReference',
          keys: [{ type: 'GlobalReference', value: req.semanticId }]
        }
      } : {}),
      value: elements
    };
  }

  /**
   * Extract fill volume from packaging string
   * @param {Object} batchData - Batch data with packaging info
   * @returns {number} Fill volume in mL
   */
  extractFillVolume(batchData) {
    const packaging = batchData.packaging || '';
    const match = packaging.match(/(\d+(?:\.\d+)?)\s*mL/i);
    return match ? parseFloat(match[1]) : 3.0; // Default to 3mL
  }

  /**
   * Create a Process SubmodelElementCollection
   * @param {Object} processConfig - Process configuration
   * @returns {Object} Process SMC
   */
  createProcessElement(processConfig) {
    const elements = [];

    // Capability reference (semantic ID)
    const capabilitySemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, processConfig.semanticId)]
    );

    // Description property
    elements.push(this.createProperty(
      'Description',
      processConfig.description,
      DataTypeDefXsd.String,
      this.createReference(ReferenceTypes.ExternalReference,
        [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/aas/3/0/Description')]
      )
    ));

    // Sequence number property
    elements.push(this.createProperty(
      'SequenceNumber',
      processConfig.sequenceNumber,
      DataTypeDefXsd.Int,
      this.createReference(ReferenceTypes.ExternalReference,
        [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/BillOfProcess/1/0/SequenceNumber')]
      )
    ));

    // Estimated duration with unit qualifier
    if (processConfig.estimatedDuration) {
      const durationProp = this.createPropertyWithUnit(
        'EstimatedDuration',
        processConfig.estimatedDuration.value,
        DataTypeDefXsd.Double,
        processConfig.estimatedDuration.unit,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, AasService.BOP_SEMANTIC_IDS.DURATION)]
        )
      );
      elements.push(durationProp);
    }

    // Parameters SMC (optional)
    if (processConfig.parameters && processConfig.parameters.length > 0) {
      const paramElements = processConfig.parameters.map(param => this.createParameterElement(param));
      const paramsSMC = this.createSubmodelElementCollection(
        'Parameters',
        paramElements,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/BillOfProcess/1/0/Parameters')]
        )
      );
      elements.push(paramsSMC);
    }

    // Requirements SMC (optional)
    if (processConfig.requirements && processConfig.requirements.length > 0) {
      const reqElements = processConfig.requirements.map(req => this.createRequirementElement(req));
      const reqsSMC = this.createSubmodelElementCollection(
        'Requirements',
        reqElements,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/BillOfProcess/1/0/Requirements')]
        )
      );
      elements.push(reqsSMC);
    }

    // Create the Process SMC with semantic ID referencing capability
    return this.createSubmodelElementCollection(
      processConfig.idShort,
      elements,
      capabilitySemanticId
    );
  }

  /**
   * Create a Parameter SubmodelElementCollection
   * @param {Object} paramConfig - Parameter configuration
   * @returns {Object} Parameter SMC
   */
  createParameterElement(paramConfig) {
    const elements = [];
    const paramSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, paramConfig.semanticId)]
    );

    // Description
    elements.push(this.createProperty(
      'Description',
      paramConfig.description,
      DataTypeDefXsd.String
    ));

    // Value with appropriate type
    const valueType = this.xsdStringToDataType(paramConfig.valueType || 'xs:double');
    elements.push(this.createPropertyWithUnit(
      'Value',
      paramConfig.value,
      valueType,
      paramConfig.unit,
      paramSemanticId
    ));

    return this.createSubmodelElementCollection(
      paramConfig.idShort,
      elements,
      paramSemanticId
    );
  }

  /**
   * Create a Requirement SubmodelElementCollection
   * Supports both simple value requirements and tolerance-based requirements
   * @param {Object} reqConfig - Requirement configuration
   * @returns {Object} Requirement SMC
   */
  createRequirementElement(reqConfig) {
    const elements = [];
    const reqSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, reqConfig.semanticId)]
    );

    // Description
    elements.push(this.createProperty(
      'Description',
      reqConfig.description,
      DataTypeDefXsd.String
    ));

    // For tolerance-based requirements
    if (reqConfig.nominalValue !== undefined) {
      const valueType = this.xsdStringToDataType(reqConfig.valueType || 'xs:double');
      
      elements.push(this.createPropertyWithUnit(
        'NominalValue',
        reqConfig.nominalValue,
        valueType,
        reqConfig.unit,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, '0173-1#02-AAM955#002')] // ECLASS: Nominal value
        )
      ));

      elements.push(this.createPropertyWithUnit(
        'Tolerance',
        reqConfig.tolerance,
        valueType,
        reqConfig.unit,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, '0173-1#02-AAI023#002')] // ECLASS: Tolerance
        )
      ));

      elements.push(this.createProperty(
        'ToleranceType',
        reqConfig.toleranceType || 'absolute',
        DataTypeDefXsd.String,
        this.createReference(ReferenceTypes.ExternalReference,
          [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/BillOfProcess/1/0/ToleranceType')]
        )
      ));
    }
    // For simple value requirements (e.g., compliance standards)
    else if (reqConfig.value !== undefined) {
      const valueType = this.xsdStringToDataType(reqConfig.valueType || 'xs:string');
      elements.push(this.createProperty(
        'Value',
        reqConfig.value,
        valueType,
        reqSemanticId
      ));

      if (reqConfig.complianceType) {
        elements.push(this.createProperty(
          'ComplianceType',
          reqConfig.complianceType,
          DataTypeDefXsd.String,
          this.createReference(ReferenceTypes.ExternalReference,
            [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/BillOfProcess/1/0/ComplianceType')]
          )
        ));
      }
    }

    return this.createSubmodelElementCollection(
      reqConfig.idShort,
      elements,
      reqSemanticId
    );
  }

  /**
   * Create a Property with Unit qualifier
   * @param {string} idShort - Property ID
   * @param {any} value - Property value
   * @param {DataTypeDefXsd} valueType - XSD data type
   * @param {string} unit - Unit string
   * @param {Object} semanticId - Semantic ID reference
   * @returns {Object} Property with unit qualifier
   */
  createPropertyWithUnit(idShort, value, valueType, unit, semanticId = null) {
    const prop = this.createProperty(idShort, value, valueType, semanticId);
    
    // Add unit qualifier
    if (unit) {
      prop.qualifiers = [
        {
          type: 'Unit',
          valueType: 'xs:string',
          value: unit,
          semanticId: this.createReference(ReferenceTypes.ExternalReference,
            [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/aas/3/0/Qualifier/Unit')]
          )
        }
      ];
    }
    
    return prop;
  }

  /**
   * Convert XSD type string to DataTypeDefXsd enum
   * @param {string} xsdString - XSD type string (e.g., 'xs:double')
   * @returns {DataTypeDefXsd} Enum value
   */
  xsdStringToDataType(xsdString) {
    const mapping = {
      'xs:string': DataTypeDefXsd.String,
      'xs:double': DataTypeDefXsd.Double,
      'xs:float': DataTypeDefXsd.Float,
      'xs:int': DataTypeDefXsd.Int,
      'xs:integer': DataTypeDefXsd.Int,
      'xs:boolean': DataTypeDefXsd.Boolean,
      'xs:dateTime': DataTypeDefXsd.DateTime,
      'xs:long': DataTypeDefXsd.Long
    };
    return mapping[xsdString] || DataTypeDefXsd.String;
  }

  /**
   * Save a complete Product AAS to the server
   * @param {Object} batchData - The batch configuration data
   * @returns {Promise<Object>} The created AAS information
   */
  async saveProductAas(batchData) {
    try {
      const productAas = this.createProductAas(batchData);
      const { ids, submodels } = productAas;
      
      // Save each submodel to the repository (create or update)
      await this.saveOrUpdateSubmodel(ids.batchInfoSubmodelId, submodels.batchInfo);
      await this.saveOrUpdateSubmodel(ids.requirementsSubmodelId, submodels.requirements);
      await this.saveOrUpdateSubmodel(ids.billOfMaterialsSubmodelId, submodels.billOfMaterials);
      await this.saveOrUpdateSubmodel(ids.billOfProcessesSubmodelId, submodels.billOfProcesses);
      
      // Create the AAS shell with submodel references
      const aasShell = this.createProductAasShell(batchData, ids);
      await this.saveOrUpdateAasShell(ids.aasId, aasShell);
      
      toast.success(`Product AAS saved for order ${batchData.product}`);
      
      return {
        success: true,
        ids,
        message: `Product AAS created with ID: ${ids.aasId}`
      };
    } catch (error) {
      console.error('Failed to save Product AAS:', error);
      toast.error(`Failed to save Product AAS: ${error.message}`);
      throw error;
    }
  }

  /**
   * Create an AAS shell for a product with submodel references
   */
  createProductAasShell(batchData, ids) {
    const productName = batchData.product || 'Product';
    const idShort = `${productName.replace(/\s+/g, '')}AAS`;
    
    // Create asset information with assetType using ontology URL structure
    // AssetType format: https://smartproductionlab.aau.dk/{role}/{category}/{specific-type}
    // Example: https://smartproductionlab.aau.dk/product/productFamily/growth-hormones
    // Constructor: (assetKind, globalAssetId, specificAssetIds, assetType, defaultThumbnail)
    const assetInfo = new AssetInformation(
      AssetKind.Instance,
      ids.assetId,  // globalAssetId
      null, // specificAssetIds - not used, all info is in assetType
      ids.assetType  // assetType - ontology URL encoding role/category/type
    );
    
    // Create submodel references
    const submodelRefs = [
      this.createReference(
        ReferenceTypes.ModelReference,
        [this.createKey(KeyTypes.Submodel, ids.batchInfoSubmodelId)]
      ),
      this.createReference(
        ReferenceTypes.ModelReference,
        [this.createKey(KeyTypes.Submodel, ids.requirementsSubmodelId)]
      ),
      this.createReference(
        ReferenceTypes.ModelReference,
        [this.createKey(KeyTypes.Submodel, ids.billOfMaterialsSubmodelId)]
      ),
      this.createReference(
        ReferenceTypes.ModelReference,
        [this.createKey(KeyTypes.Submodel, ids.billOfProcessesSubmodelId)]
      )
    ];
    
    // Create the AAS shell
    const aasShell = new AssetAdministrationShell(
      ids.aasId,
      assetInfo,
      null, // extensions
      null, // category
      idShort, // idShort
      null, // displayName
      null, // description
      null, // administration
      null, // embeddedDataSpecifications
      null, // derivedFrom
      submodelRefs // submodels
    );
    
    return aasShell;
  }

  /**
   * Save or update an AAS shell - checks existence first to avoid conflicts
   * Also registers/updates the descriptor in the registry
   */
  async saveOrUpdateAasShell(aasId, aasShell) {
    let aasExists = false;
    
    // Check if AAS exists by listing (avoids 404 console error)
    try {
      const listResult = await this.aasRepositoryClient.getAllAssetAdministrationShells({
        configuration: this.repositoryConfig
      });

      if (listResult.success && listResult.data?.result) {
        aasExists = listResult.data.result.some(aas => aas.id === aasId);
      } else {
        const existsResult = await this.aasRepositoryClient.getAssetAdministrationShellById({
            configuration: this.repositoryConfig,
            aasIdentifier: aasId
        });
        aasExists = existsResult.success === true;
      }
    } catch (checkError) {
      aasExists = false;
    }
    
    if (aasExists) {
      // Update existing AAS
      console.log(`Updating existing AAS: ${aasId}`);
      const result = await this.aasRepositoryClient.putAssetAdministrationShellById({
        configuration: this.repositoryConfig,
        aasIdentifier: aasId,
        assetAdministrationShell: aasShell
      });
      
      if (!result.success) {
        throw new Error(result.error?.message || 'Failed to update AAS');
      }
      
      return result.data || aasShell;
    }
    
    // Create new AAS
    console.log(`Creating new AAS: ${aasId}`);
    console.log('AAS Shell payload:', JSON.stringify(aasShell, null, 2));
    const result = await this.aasRepositoryClient.postAssetAdministrationShell({
      configuration: this.repositoryConfig,
      assetAdministrationShell: aasShell
    });
    
    if (result.success) {
      console.log(`Successfully created AAS: ${aasId}`);
      
      // Register in registry
      await this.registerAasDescriptor(aasId, aasShell);
      
      return result.data || aasShell;
    }
    
    console.error('Failed to create AAS. Full result:', result);
    throw new Error(result.error?.message || result.error?.details || JSON.stringify(result.error) || 'Failed to create AAS');
  }

  /**
   * Create an AAS descriptor from an AAS shell for registry registration
   * @param {Object} aasShell - The AAS shell object
   * @param {Array} submodelIds - Array of submodel IDs to include as submodel descriptors
   * @returns {AssetAdministrationShellDescriptor} The descriptor object
   */
  createDescriptorFromAas(aasShell, submodelIds = []) {
    const encodedId = this.base64UrlEncode(aasShell.id);
    const endpoint = this.createEndpoint('AAS-3.0', `${this.repositoryUrl}/shells/${encodedId}`);
    
    // Create submodel descriptors if submodel IDs are provided
    const submodelDescriptors = submodelIds.map(id => this.createSubmodelDescriptor(id));
    
    return new AssetAdministrationShellDescriptor(
      aasShell.id,
      aasShell.displayName ?? null,
      aasShell.description ?? null,
      aasShell.extensions ?? null,
      aasShell.administration ?? null,
      aasShell.idShort ?? null,
      aasShell.assetInformation?.assetKind ?? null,
      aasShell.assetInformation?.assetType ?? null,
      aasShell.assetInformation?.globalAssetId ?? null,
      aasShell.assetInformation?.specificAssetIds ?? null,
      submodelDescriptors.length > 0 ? submodelDescriptors : null,
      [endpoint]
    );
  }

  /**
   * Register an AAS descriptor in the registry (for new AAS only)
   * @param {string} aasId - The AAS identifier
   * @param {Object} aasShell - The AAS shell object
   * @param {Array} submodelIds - Optional array of submodel IDs
   */
  async registerAasDescriptor(aasId, aasShell, submodelIds = []) {
    try {
      // Extract submodel IDs from the shell's submodel references if not provided
      if (submodelIds.length === 0 && aasShell.submodels) {
        submodelIds = aasShell.submodels.map(ref => {
          // Get the submodel ID from the reference keys
          const submodelKey = ref.keys?.find(k => k.type === 'Submodel');
          return submodelKey?.value;
        }).filter(Boolean);
      }
      
      const descriptor = this.createDescriptorFromAas(aasShell, submodelIds);
      
      // Check if descriptor exists in registry
      let descriptorExists = false;
      try {
        const existsResult = await this.registryClient.getAssetAdministrationShellDescriptorById({
          configuration: this.registryConfig,
          aasIdentifier: aasId
        });
        descriptorExists = existsResult.success === true;
      } catch (checkError) {
        descriptorExists = false;
      }
      
      if (descriptorExists) {
        // Descriptor already exists, skip registration
        console.log(`Registry descriptor already exists for: ${aasId}`);
        return;
      }
      
      // Create new descriptor
      console.log(`Registering new AAS descriptor: ${aasId}`);
      const result = await this.registryClient.postAssetAdministrationShellDescriptor({
        configuration: this.registryConfig,
        assetAdministrationShellDescriptor: descriptor
      });
      
      if (!result.success) {
        console.warn(`Failed to register AAS descriptor: ${result.error?.message}`);
        return;
      }
      
      console.log(`Successfully registered AAS descriptor: ${aasId}`);
      
      // Register submodel descriptors
      if (submodelIds.length > 0) {
        await this.registerSubmodelDescriptors(aasId, submodelIds);
      }
    } catch (error) {
      // Don't fail the whole operation if registry registration fails
      console.warn(`Registry registration warning for ${aasId}:`, error.message);
    }
  }

  /**
   * Generate product AAS IDs based on product name (for active production)
   * Creates IDs like "MIM8AAS" for the actively produced product
   * @param {string} productName - The product name
   * @param {string} productFamily - The product family (e.g., 'Monoclonal Antibodies', 'Growth Hormones')
   * @param {string} batchUuid - The batch UUID for unique asset identification
   */
  getActiveProductAasIds(productName, productFamily = null, batchUuid = null) {
    const baseUrl = 'https://smartproductionlab.aau.dk';
    const sanitizedName = productName.replace(/\s+/g, '');
    const sanitizedFamily = productFamily ? productFamily.toLowerCase().replace(/\s+/g, '-') : 'unknown';
    // Use batch UUID for unique asset ID, or generate a new UUID if not provided
    const assetId = batchUuid 
      ? this.generateGlobalAssetId(batchUuid) 
      : this.generateGlobalAssetId(crypto.randomUUID());
    // idShort includes AAS suffix, used in submodel paths
    const idShort = `${sanitizedName}AAS`;
    return {
      aasId: `${baseUrl}/aas/${idShort}`,
      assetId,
      // AssetType uses ontology URL structure: role/category/specific-type/product
      assetType: `${baseUrl}/product/productFamily/${sanitizedFamily}/${sanitizedName}`,
      batchInfoSubmodelId: `${baseUrl}/submodels/instances/${idShort}/BatchInformation`,
      requirementsSubmodelId: `${baseUrl}/submodels/instances/${idShort}/Requirements`,
      billOfMaterialsSubmodelId: `${baseUrl}/submodels/instances/${idShort}/HierarchicalStructures`,
      billOfProcessesSubmodelId: `${baseUrl}/submodels/instances/${idShort}/BillOfProcesses`
    };
  }

  /**
   * Post the active product AAS when batch moves to top of queue
   * Uses product name for AAS ID (e.g., MIM8AAS)
   * @param {Object} batchData - The batch at the top of the queue
   * @returns {Promise<Object>} The created AAS information
   */
  async postActiveProductAas(batchData) {
    try {
      const productName = batchData.product;
      if (!productName) {
        throw new Error('Product name is required');
      }
      
      const productFamily = batchData.productFamily || productName;
      const batchUuid = batchData.Uuid;
      const ids = this.getActiveProductAasIds(productName, productFamily, batchUuid);
      
      // Create submodels with the active product IDs
      const batchInfoSubmodel = this.createBatchInformationSubmodel(batchData, ids.batchInfoSubmodelId);
      const requirementsSubmodel = this.createRequirementsSubmodel(batchData, ids.requirementsSubmodelId);
      const billOfMaterialsSubmodel = this.createActiveBillOfMaterialsSubmodel(batchData, ids);
      const billOfProcessesSubmodel = this.createBillOfProcessesSubmodel(batchData, ids.billOfProcessesSubmodelId);
      
      // Save each submodel to the repository (create or update)
      await this.saveOrUpdateSubmodel(ids.batchInfoSubmodelId, batchInfoSubmodel);
      await this.saveOrUpdateSubmodel(ids.requirementsSubmodelId, requirementsSubmodel);
      await this.saveOrUpdateSubmodel(ids.billOfMaterialsSubmodelId, billOfMaterialsSubmodel);
      await this.saveOrUpdateSubmodel(ids.billOfProcessesSubmodelId, billOfProcessesSubmodel);
      
      // Create the AAS shell with submodel references
      const aasShell = this.createProductAasShell(batchData, ids);
      await this.saveOrUpdateAasShell(ids.aasId, aasShell);
      
      toast.success(`Active Product AAS posted: ${productName}AAS`);
      
      return {
        success: true,
        ids,
        aasName: `${productName}AAS`,
        message: `Active Product AAS posted with ID: ${ids.aasId}`
      };
    } catch (error) {
      console.error('Failed to post active Product AAS:', error);
      toast.error(`Failed to post active Product AAS: ${error.message}`);
      throw error;
    }
  }

  /**
   * Create BillOfMaterials submodel for active product (IDTA 02011-1-1)
   */
  createActiveBillOfMaterialsSubmodel(batchData, ids) {
    const submodelId = ids.billOfMaterialsSubmodelId;
    
    // Use official IDTA 02011-1-1 semantic ID for HierarchicalStructures submodel
    const semanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel')]
    );
    
    // Create ArcheType property (IDTA uses "ArcheType" spelling)
    const archetypeSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/ArcheType/1/0')]
    );
    const archetypeProperty = this.createProperty('ArcheType', 'OneDown', DataTypeDefXsd.String, archetypeSemanticId);
    
    // Create material entities based on packaging type (as separate entities, not nested)
    const materialEntities = this.createMaterialEntities(batchData);
    
    // Create EntryNode for the product (IDTA 02011-1-1) - without nested materials
    const entryNodeSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/EntryNode/1/0')]
    );
    
    // Product entity without nested children - relationships define the hierarchy
    const entryNode = this.createEntity(
      'Product',
      EntityType.SelfManagedEntity,
      ids.assetId,
      [], // No nested statements - use relationships instead
      entryNodeSemanticId
    );
    
    // Create relationships for bill of materials (HasPart naming convention)
    // In flat structure, both parent and child are direct submodel elements
    const relationships = materialEntities.map(material => {
      return this.createFlatBillOfMaterialsRelationship(
        `Has${material.idShort}`,
        submodelId,
        'Product',
        material.idShort
      );
    });
    
    // All entities are direct children of submodel, relationships define hierarchy
    const elements = [archetypeProperty, entryNode, ...materialEntities, ...relationships];
    
    return this.createSubmodel(submodelId, 'HierarchicalStructures', elements, semanticId, 'BillOfMaterials');
  }

  /**
   * Create relationship for flat bill of materials structure
   * Both parent and child are direct submodel elements, referenced by idPath
   */
  createFlatBillOfMaterialsRelationship(idShort, submodelId, parentIdShort, childIdShort) {
    // First reference points to the parent entity
    const firstRef = this.createReference(
      ReferenceTypes.ModelReference,
      [
        this.createKey(KeyTypes.Submodel, submodelId),
        this.createKey(KeyTypes.Entity, parentIdShort)
      ]
    );
    
    // Second reference points to the child entity (sibling in submodel)
    const secondRef = this.createReference(
      ReferenceTypes.ModelReference,
      [
        this.createKey(KeyTypes.Submodel, submodelId),
        this.createKey(KeyTypes.Entity, childIdShort)
      ]
    );
    
    // Use official IDTA 02011-1-1 HasPart semantic ID
    const semanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/HasPart/1/0')]
    );
    
    return this.createRelationshipElement(idShort, firstRef, secondRef, semanticId);
  }

  /**
   * Get a Product AAS by order UUID
   * @param {string} orderUuid - The order UUID
   * @returns {Promise<Object>} The product AAS data
   */
  async getProductAas(orderUuid) {
    try {
      const ids = this.getProductAasIds(orderUuid);
      
      const [batchInfo, requirements, billOfMaterials] = await Promise.all([
        this.getSubmodel(ids.batchInfoSubmodelId).catch(() => null),
        this.getSubmodel(ids.requirementsSubmodelId).catch(() => null),
        this.getSubmodel(ids.billOfMaterialsSubmodelId).catch(() => null)
      ]);
      
      return {
        ids,
        submodels: {
          batchInfo,
          requirements,
          billOfMaterials
        }
      };
    } catch (error) {
      console.error(`Failed to get Product AAS for ${orderUuid}:`, error);
      throw error;
    }
  }

  /**
   * Delete a Product AAS by order UUID
   * @param {string} orderUuid - The order UUID
   * @returns {Promise<boolean>} True if successful
   */
  async deleteProductAas(orderUuid) {
    try {
      const ids = this.getProductAasIds(orderUuid);
      
      await Promise.all([
        this.deleteSubmodel(ids.batchInfoSubmodelId).catch(() => false),
        this.deleteSubmodel(ids.requirementsSubmodelId).catch(() => false),
        this.deleteSubmodel(ids.billOfMaterialsSubmodelId).catch(() => false)
      ]);
      
      toast.success(`Product AAS deleted for order ${orderUuid}`);
      return true;
    } catch (error) {
      console.error(`Failed to delete Product AAS for ${orderUuid}:`, error);
      toast.error(`Failed to delete Product AAS: ${error.message}`);
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
  createReferenceElement(idShort, reference, semanticId = null, supplementalSemanticIds = null) {
    return new ReferenceElement(
      null,  // extensions
      null,  // category
      idShort,
      null,  // displayName
      null,  // description
      semanticId,
      supplementalSemanticIds,
      null,  // qualifiers
      null,  // embeddedDataSpecifications
      reference
    );
  }

  /**
   * Create an Entity using SDK types
   */
  createEntity(idShort, entityType, globalAssetId, statements, semanticId = null, specificAssetId = null) {
    // Pass null instead of empty arrays for statements (AAS server requirement)
    const statementsToUse = (statements && statements.length > 0) ? statements : null;
    
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
      statementsToUse,
      globalAssetId,
      specificAssetId ? [specificAssetId] : null   // specificAssetIds
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
   * @param {string} id - The submodel ID
   * @param {string} idShort - The short identifier
   * @param {Array} elements - The submodel elements
   * @param {Object} semanticId - Optional semantic ID reference
   * @param {string|Array} displayName - Optional display name (string or LangStringSet array)
   */
  createSubmodel(id, idShort, elements, semanticId = null, displayName = null) {
    // Convert string displayName to LangStringSet format if needed
    let displayNameSet = null;
    if (displayName) {
      if (typeof displayName === 'string') {
        displayNameSet = [{ language: 'en', text: displayName }];
      } else {
        displayNameSet = displayName;
      }
    }
    
    return new Submodel(
      id,
      null,  // extensions
      null,  // category
      idShort,
      displayNameSet,  // displayName
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
   * Create a Velocity limits SubmodelElementCollection
   * Contains max speed limits for x, y, and Rz axes
   */
  createVelocityLimits(maxSpeedX, maxSpeedY, maxSpeedRz) {
    const velocitySemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/VelocityLimits')]
    );
    
    const velocityProperties = [
      this.createProperty('x', parseFloat(maxSpeedX) || 0, DataTypeDefXsd.Float),
      this.createProperty('y', parseFloat(maxSpeedY) || 0, DataTypeDefXsd.Float),
      this.createProperty('Rz', parseFloat(maxSpeedRz) || 0, DataTypeDefXsd.Float)
    ];
    
    return this.createSubmodelElementCollection('Velocity', velocityProperties, velocitySemanticId);
  }

  /**
   * Create an Acceleration limits SubmodelElementCollection
   * Contains max acceleration limits for x, y, and Rz axes
   */
  createAccelerationLimits(maxAccelX, maxAccelY, maxAccelRz) {
    const accelerationSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://smartproductionlab.aau.dk/semantics/AccelerationLimits')]
    );
    
    const accelerationProperties = [
      this.createProperty('x', parseFloat(maxAccelX) || 0, DataTypeDefXsd.Float),
      this.createProperty('y', parseFloat(maxAccelY) || 0, DataTypeDefXsd.Float),
      this.createProperty('Rz', parseFloat(maxAccelRz) || 0, DataTypeDefXsd.Float)
    ];
    
    return this.createSubmodelElementCollection('Acceleration', accelerationProperties, accelerationSemanticId);
  }

  /**
   * Create an Entity node for a station
   */
  createEntityNode(idShort, globalAssetId, x, y, yaw = 0, instanceSubmodelId = null, instanceAasId = null) {
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
    
    // Add SameAs reference if instanceSubmodelId is provided (IDTA 02011-1-1)
    if (instanceSubmodelId) {
      const sameAsSemanticId = this.createReference(
        ReferenceTypes.ExternalReference,
        [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/SameAs/1/0')]
      );

      const entryNodeSemanticId = this.createReference(
        ReferenceTypes.ExternalReference,
        [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/EntryNode/1/0')]
      );
      
      // AASd-125 compliant: First key is AasIdentifiable (Submodel),
      // subsequent keys are FragmentKeys (Entity)
      const sameAsKeys = [
        this.createKey(KeyTypes.Submodel, instanceSubmodelId),
        this.createKey(KeyTypes.Entity, 'EntryNode')
      ];

      const sameAsReference = this.createReference(
        ReferenceTypes.ModelReference,
        sameAsKeys
      );
      
      const sameAsElement = this.createReferenceElement(
        'SameAs',
        sameAsReference,
        sameAsSemanticId,
        [entryNodeSemanticId]
      );
      statements.push(sameAsElement);
    }
    
    // Use official IDTA 02011-1-1 Node semantic ID
    const nodeSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/Node/1/0')]
    );
    
    // Logic to distinguish between SelfManaged and CoManaged
    if (instanceSubmodelId) {
      // SelfManaged: Use AAS ID in globalAssetId field
      return this.createEntity(idShort, EntityType.SelfManagedEntity, globalAssetId, statements, nodeSemanticId);
    } else {
      // CoManaged: Use SpecificAssetId instead of globalAssetId
      const specificAssetId = new SpecificAssetId('specificAssetId', globalAssetId);
      return this.createEntity(idShort, EntityType.CoManagedEntity, null, statements, nodeSemanticId, specificAssetId);
    }
  }

  /**
   * Create a RelationshipElement for parent-child relationship
   */
  createRelationshipElementForHierarchy(idShort, parentNodeId, childNodeId) {
    const submodelId = this.rootSubmodelId;
    
    // AASd-125 compliant: First key is AasIdentifiable (Submodel),
    // subsequent keys are FragmentKeys (Entity)
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
    
    // Use official IDTA 02011-1-1 HasPart semantic ID (parent HasPart child)
    const semanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/HasPart/1/0')]
    );
    
    return this.createRelationshipElement(idShort, firstRef, secondRef, semanticId);
  }

  async transformLayoutDataToHierarchicalStructures(layoutData) {
    const submodelId = this.rootSubmodelId;
    const rootAssetId = 'https://smartproductionlab.aau.dk/assets/MWQ2ODY5ZDEtZTQ3Yy00NWU4LTlmYTAtNTI3YjVlMDk4MWFi';
    
    // Build globalAssetId lookup from registry shell descriptors
    const assetIdLookup = await this.buildGlobalAssetIdLookup();
    
    // Create the PlanarTable entity as a default child (always included)
    const planarTableEntity = this.createEntityNode(
      'PlanarTable',
      this.planarTableAssetId,
      0, // x position (center of table)
      0, // y position (center of table)
      0, // yaw
      this.planarTableHierarchicalStructuresId,
      this.planarTableAasId
    );
    
    // Build child entities from stations
    const childEntities = layoutData.Stations.map(station => {
      const instanceName = station['Instance Name'];
      const assetType = station['AssetType'];
      const genericName = this.getGenericName(assetType, instanceName);
      
      // Lookup globalAssetId from registry: first try explicit AssetId, then AasId lookup, then idShort lookup
      const instanceAasId = station['AasId'] || null;
      let globalAssetId = station['AssetId'];
      
      if (!globalAssetId && instanceAasId) {
        // Try to find globalAssetId by AAS ID from registry
        globalAssetId = assetIdLookup.byId[instanceAasId];
      }
      if (!globalAssetId) {
        // Try to find globalAssetId by idShort (station name) from registry
        globalAssetId = assetIdLookup.byIdShort[genericName] || 
                        assetIdLookup.byIdShort[`${genericName}AAS`];
      }
      if (!globalAssetId) {
        // Final fallback: generate a new UUID-based asset ID for consistency
        console.warn(`No globalAssetId found in registry for station ${genericName}, generating new UUID`);
        globalAssetId = this.generateGlobalAssetId(crypto.randomUUID());
      }
      
      const instanceSubmodelId = station['SubmodelId'];
      
      const approachPos = station["Approach Position"] || [0, 0, 0];
      const xMM = Array.isArray(approachPos) ? approachPos[0] : 0;
      const yMM = Array.isArray(approachPos) ? approachPos[1] : 0;
      const yaw = Array.isArray(approachPos) ? approachPos[2] : 0;
      
      return this.createEntityNode(genericName, globalAssetId, xMM, yMM, yaw, instanceSubmodelId, instanceAasId);
    });
    
    // Add planarTable as the first child entity (always included by default)
    const allChildEntities = [planarTableEntity, ...childEntities];
    
    // Build relationships - include planarTable relationship first
    const planarTableRelationship = this.createRelationshipElementForHierarchy('HasPlanarTable', 'EntryNode', 'PlanarTable');
    
    const stationRelationships = layoutData.Stations.map(station => {
      const genericName = this.getGenericName(station['AssetType'], station['Instance Name']);
      return this.createRelationshipElementForHierarchy(`Has${genericName}`, 'EntryNode', genericName);
    });
    
    const relationships = [planarTableRelationship, ...stationRelationships];
    
    // Create ArcheType property (IDTA 02011-1-1 uses "ArcheType" spelling)
    const archetypeSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/ArcheType/1/0')]
    );
    const archetypeProperty = this.createProperty('ArcheType', 'OneDown', DataTypeDefXsd.String, archetypeSemanticId);
    
    // Create EntryNode entity (IDTA 02011-1-1)
    const entryNodeSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/EntryNode/1/0')]
    );
    const entryNode = this.createEntity('EntryNode', EntityType.SelfManagedEntity, rootAssetId, allChildEntities, entryNodeSemanticId);
    
    // Create the Submodel with official IDTA 02011-1-1 semantic ID
    const submodelSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel')]
    );
    
    const submodelElements = [archetypeProperty, entryNode, ...relationships];
    
    return this.createSubmodel(submodelId, 'HierarchicalStructures', submodelElements, submodelSemanticId, 'BillOfMaterials');
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
          const aasId = sameAsRef?.value?.keys?.find(k => k.type === 'AssetAdministrationShell')?.value || null;
          
          // Get asset ID (either globalAssetId or from specificAssetId)
          let assetId = entity.globalAssetId;
          const specificAssetIdList = entity.specificAssetIds || entity.specificAssetId;
          if (!assetId && specificAssetIdList) {
             if (Array.isArray(specificAssetIdList) && specificAssetIdList.length > 0) {
                 assetId = specificAssetIdList[0].value;
             } else if (specificAssetIdList.value) {
                 assetId = specificAssetIdList.value;
             }
          }
          
          // Match with module catalog
          const module = moduleCatalog.find(m => m.aasId === assetId);
          
          return {
            Name: entity.idShort,
            'Instance Name': module?.name || entity.idShort,
            StationId: index,
            AasId: aasId || assetId,
            AssetType: module?.assetType || entity.idShort,
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
