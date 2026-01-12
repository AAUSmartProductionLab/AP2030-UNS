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
   * Update/put a submodel by ID (generic)
   * @param {string} submodelId - The submodel identifier
   * @param {Object} submodelData - The submodel data (SDK Submodel object or JSON)
   * @returns {Promise<Object>} The updated submodel data
   */
  async putSubmodel(submodelId, submodelData) {
    try {
      const result = await this.submodelClient.putSubmodelById({
        configuration: this.repositoryConfig,
        submodelIdentifier: submodelId,
        submodel: submodelData
      });
      
      if (result.success) {
        return result.data || submodelData;
      }
      
      throw new Error(result.error?.message || 'Failed to update submodel');
    } catch (error) {
      console.error(`Failed to update submodel ${submodelId}:`, error);
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
      const result = await this.submodelClient.postSubmodel({
        configuration: this.repositoryConfig,
        submodel: submodelData
      });
      
      if (result.success) {
        return result.data || submodelData;
      }
      
      throw new Error(result.error?.message || 'Failed to create submodel');
    } catch (error) {
      console.error('Failed to create submodel:', error);
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
    
    // First check if submodel exists
    try {
      const existsResult = await this.submodelClient.getSubmodelById({
        configuration: this.repositoryConfig,
        submodelIdentifier: submodelId
      });
      
      submodelExists = existsResult.success === true;
    } catch (checkError) {
      // Submodel doesn't exist (404 error), will create it
      submodelExists = false;
    }
    
    if (submodelExists) {
      // Submodel exists, update it
      console.log(`Updating existing submodel: ${submodelId}`);
      const result = await this.putSubmodel(submodelId, submodelData);
      return result;
    }
    
    // Create new submodel
    console.log(`Creating new submodel: ${submodelId}`);
    try {
      const result = await this.submodelClient.postSubmodel({
        configuration: this.repositoryConfig,
        submodel: submodelData
      });
      
      if (result.success) {
        console.log(`Successfully created submodel: ${submodelId}`);
        return result.data || submodelData;
      }
      
      throw new Error(result.error?.message || 'Failed to create submodel');
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
   */
  get planarTableAssetId() {
    return 'https://smartproductionlab.aau.dk/assets/planarTable';
  }

  get planarTableParametersSubmodelId() {
    return 'https://smartproductionlab.aau.dk/submodels/instances/planarTable/Parameters';
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
    return {
      aasId: `${baseUrl}/aas/products/${orderUuid}`,
      assetId: this.generateGlobalAssetId(orderUuid),
      // AssetType uses ontology URL structure: role/category/specific-type/product
      assetType: `${baseUrl}/product/productFamily/${sanitizedFamily}/${sanitizedProduct}`,
      batchInfoSubmodelId: `${baseUrl}/submodels/products/${orderUuid}/BatchInformation`,
      requirementsSubmodelId: `${baseUrl}/submodels/products/${orderUuid}/Requirements`,
      billOfMaterialsSubmodelId: `${baseUrl}/submodels/products/${orderUuid}/BillOfMaterials`
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
    
    return {
      ids,
      submodels: {
        batchInfo: batchInfoSubmodel,
        requirements: requirementsSubmodel,
        billOfMaterials: billOfMaterialsSubmodel
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
    
    // Create material entities based on packaging type
    const materialEntities = this.createMaterialEntities(batchData);
    
    // Create EntryNode for the product (IDTA 02011-1-1)
    const entryNodeSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/EntryNode/1/0')]
    );
    
    const productFamily = batchData.productFamily || batchData.product;
    const productAssetId = this.getProductAasIds(batchData.Uuid, productFamily).assetId;
    const entryNode = this.createEntity(
      'Product',
      EntityType.SelfManagedEntity,
      productAssetId,
      materialEntities,
      entryNodeSemanticId
    );
    
    // Create relationships for bill of materials (HasPart naming convention)
    const relationships = materialEntities.map(material => {
      return this.createBillOfMaterialsRelationship(
        `Has${material.idShort}`,
        submodelId,
        'Product',
        material.idShort
      );
    });
    
    const elements = [archetypeProperty, entryNode, ...relationships];
    
    return this.createSubmodel(submodelId, 'BillOfMaterials', elements, semanticId);
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
      `https://smartproductionlab.aau.dk/assets/materials/${containerType.toLowerCase()}`,
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
      'https://smartproductionlab.aau.dk/assets/materials/stopper',
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
      `https://smartproductionlab.aau.dk/assets/materials/${(batchData.product || 'unknown').toLowerCase()}`,
      [apiCollection],
      nodeSemanticId
    ));
    
    return materials;
  }

  /**
   * Create relationship for bill of materials using IDTA 02011-1-1 HasPart semantic
   * HasPart: first = parent entity, second = child entity (parent has part child)
   */
  createBillOfMaterialsRelationship(idShort, submodelId, parentId, childId) {
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
    
    // Check if AAS exists
    try {
      const existsResult = await this.aasRepositoryClient.getAssetAdministrationShellById({
        configuration: this.repositoryConfig,
        aasIdentifier: aasId
      });
      aasExists = existsResult.success === true;
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
    // Use batch UUID for unique asset ID, or generate placeholder if not provided
    const assetId = batchUuid ? this.generateGlobalAssetId(batchUuid) : `${baseUrl}/assets/${sanitizedName.toLowerCase()}`;
    return {
      aasId: `${baseUrl}/aas/${sanitizedName}AAS`,
      assetId,
      // AssetType uses ontology URL structure: role/category/specific-type/product
      assetType: `${baseUrl}/product/productFamily/${sanitizedFamily}/${sanitizedName}`,
      batchInfoSubmodelId: `${baseUrl}/submodels/instances/${sanitizedName}/BatchInformation`,
      requirementsSubmodelId: `${baseUrl}/submodels/instances/${sanitizedName}/Requirements`,
      billOfMaterialsSubmodelId: `${baseUrl}/submodels/instances/${sanitizedName}/BillOfMaterials`
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
      
      // Save each submodel to the repository (create or update)
      await this.saveOrUpdateSubmodel(ids.batchInfoSubmodelId, batchInfoSubmodel);
      await this.saveOrUpdateSubmodel(ids.requirementsSubmodelId, requirementsSubmodel);
      await this.saveOrUpdateSubmodel(ids.billOfMaterialsSubmodelId, billOfMaterialsSubmodel);
      
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
    
    // Create material entities based on packaging type
    const materialEntities = this.createMaterialEntities(batchData);
    
    // Create EntryNode for the product (IDTA 02011-1-1)
    const entryNodeSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/EntryNode/1/0')]
    );
    
    const entryNode = this.createEntity(
      'Product',
      EntityType.SelfManagedEntity,
      ids.assetId,
      materialEntities,
      entryNodeSemanticId
    );
    
    // Create relationships for bill of materials (HasPart naming convention)
    const relationships = materialEntities.map(material => {
      return this.createBillOfMaterialsRelationship(
        `Has${material.idShort}`,
        submodelId,
        'Product',
        material.idShort
      );
    });
    
    const elements = [archetypeProperty, entryNode, ...relationships];
    
    return this.createSubmodel(submodelId, 'BillOfMaterials', elements, semanticId);
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
    
    // Add SameAs reference if instanceSubmodelId is provided (IDTA 02011-1-1)
    if (instanceSubmodelId) {
      const sameAsSemanticId = this.createReference(
        ReferenceTypes.ExternalReference,
        [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/SameAs/1/0')]
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
    
    // Use official IDTA 02011-1-1 Node semantic ID
    const nodeSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/Node/1/0')]
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
    
    // Use official IDTA 02011-1-1 HasPart semantic ID (parent HasPart child)
    const semanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/HasPart/1/0')]
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
    const entryNode = this.createEntity('EntryNode', EntityType.SelfManagedEntity, rootAssetId, childEntities, entryNodeSemanticId);
    
    // Create the Submodel with official IDTA 02011-1-1 semantic ID
    const submodelSemanticId = this.createReference(
      ReferenceTypes.ExternalReference,
      [this.createKey(KeyTypes.GlobalReference, 'https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel')]
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
