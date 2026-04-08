class MappingService {
    /**
     * Module-specific position offsets from the base (center) position
     * Offsets are [deltaX, deltaY] in millimeters
     */
    static moduleOffsets = {
      'DispensingSystem': [-31, 0],
      'StopperingSystem': [-8, 4],
      'QualityControlSystem': [-60,-5],
      // Add more module types as needed
      'default': [0, 0] // No offset for unknown modules
    };
    
    /**
     * Convert a container name to an integer ID
     * @param {string} containerName - e.g. "Module Area 5" or "Flyway 2"
     * @returns {number} integer ID
     */
    static nameToId(containerName) {
      if (!containerName) return -1;
      
      // For Module Areas
      if (containerName.startsWith('Module Area ')) {
        return parseInt(containerName.replace('Module Area ', ''), 10);
      }
      // For Flyways (we'll use 100+ range to differentiate)
      else if (containerName.startsWith('Flyway ')) {
        return 100 + parseInt(containerName.replace('Flyway ', ''), 10);
      }
      
      return -1; // Invalid or unknown name
    }
    
    /**
     * Convert an ID back to a container name
     * @param {number} id - Integer ID
     * @returns {string} Container name
     */
    static idToName(id) {
      if (id >= 0 && id < 100) {
        return `Module Area ${id}`;
      }
      else if (id >= 100 && id < 200) {
        return `Flyway ${id - 100}`;
      }
      return 'Unknown';
    }
    
    /**
     * Get the position offset for a specific module type
     * @param {string} moduleType - The module type (e.g., 'DispensingSystem')
     * @returns {Array} [deltaX, deltaY] offset in millimeters
     */
    static getModuleOffset(moduleType) {
      return this.moduleOffsets[moduleType] || this.moduleOffsets['default'];
    }
    
    /**
     * Get the process position for a container with module-specific offset
     * @param {number|string} containerIdOrName - Container ID or name
     * @param {string} moduleType - The module type (e.g., 'DispensingSystem')
     * @returns {Array} [x, y, Rz] position array for process
     */
    static getProcessPosition(containerIdOrName, moduleType = null) {
      const id = typeof containerIdOrName === 'string' 
        ? this.nameToId(containerIdOrName) 
        : containerIdOrName;
      
      if (this.positionMap[id]) {
        const basePos = this.positionMap[id];
        const offset = moduleType ? this.getModuleOffset(moduleType) : [0, 0];
        
        return [
          basePos[0] + offset[0],
          basePos[1] + offset[1],
          basePos[2]
        ];
      }
      
      console.warn(`No position found for container ${containerIdOrName}`);
      return [0, 0, 0]; // Default position
    }
    
    /**
     * Get the process position with optional module-specific offset
     * @param {number|string} containerIdOrName - Container ID or name
     * @param {string} moduleType - The module type for offset calculation (e.g., 'DispensingSystem')
     * @returns {Array} [x, y, Rz] position array
     */
    static getPositions(containerIdOrName, moduleType = null) {
      return this.getProcessPosition(containerIdOrName, moduleType);
    }
    
    /**
     * Get the primary position (backwards compatibility)
     * @param {number|string} containerIdOrName - Container ID or name
     * @param {string} moduleType - The module type for offset calculation
     * @returns {Array} [x, y, Rz] position array
     */
    static getPosition(containerIdOrName, moduleType = null) {
      return this.getProcessPosition(containerIdOrName, moduleType);
    }
    
    /**
     * Map asset names to their AAS instance names
     * This mapping is used by the behavior tree controller to find assets in the AAS registry
     */
    static assetNameToInstanceMap = {
      'PlanarSystem': 'planarTableAAS',
      'Xbot1': 'planarTableShuttle1AAS',
      'Xbot2': 'planarTableShuttle2AAS',
      'Xbot3': 'planarTableShuttle3AAS'
    };
    
    /**
     * Get the AAS instance name for an asset name
     * @param {string} assetName - The asset name used in the behavior tree
     * @returns {string} The AAS idShort (includes "AAS" suffix, e.g., "planarTableAAS")
     */
    static getInstanceName(assetName) {
      return this.assetNameToInstanceMap[assetName] || assetName;
    }
    
    // Mapping from grid container numbers to logical IDs
    static gridToIdMap = {
        // Top row (Module Areas)
        // Container ID to Module Area ID mapping
        2: 0,
        3: 1,
        4: 2,
        5: 3,
        7: 4,
        11: 5, 
        13: 6,  
        17: 7, 
        19: 8,   
        23: 9,   
        25: 10, 
        29: 11,  
        31: 12,
        32: 13,
        33: 14
      };
      
      // Position map with base positions (centers) - offsets are applied based on module type
      // Origin at bottom-left corner (Module Area 14), Y limit 960mm (long side), X limit 720mm (short side)
      // Format: [x, y, rotation_degrees]
      static positionMap = {
        0: [600, 840, 180],    // Top row - facing south
        1: [600, 600, 180],
        2: [600, 360, 180],
        3: [600, 120, 180],
        
        // Left edge - orientation 270 (west facing)
        4: [600, 840, 270],
        6: [360, 840, 270],
        9: [120, 840, 270],
        
        // Right edge - orientation 90 (east facing)
        5: [600, 120, 90],
        8: [360, 120, 90],
        10: [120, 120, 90],
        
        // Middle EM square
        7: [360, 600, 90],
        
        // Bottom row - orientation 0 (north facing)
        11: [120, 840, 0],
        12: [120, 600, 0],
        13: [120, 360, 0],
        14: [120, 120, 0],
        };
    }
  
  export default MappingService;