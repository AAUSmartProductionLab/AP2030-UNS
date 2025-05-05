class MappingService {
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
     * Get the approach position for a container
     * @param {number|string} containerIdOrName - Container ID or name
     * @returns {Array} [x, y, Rz] position array for approach
     */
    static getApproachPosition(containerIdOrName) {
      const id = typeof containerIdOrName === 'string' 
        ? this.nameToId(containerIdOrName) 
        : containerIdOrName;
      
      if (this.positionMap[id]?.approach) {
        return this.positionMap[id].approach;
      }
      
      console.warn(`No approach position found for container ${containerIdOrName}`);
      return [0, 0, 0]; // Default position
    }
    
    /**
     * Get the process position for a container
     * @param {number|string} containerIdOrName - Container ID or name
     * @returns {Array} [x, y, Rz] position array for process
     */
    static getProcessPosition(containerIdOrName) {
      const id = typeof containerIdOrName === 'string' 
        ? this.nameToId(containerIdOrName) 
        : containerIdOrName;
      
      if (this.positionMap[id]?.process) {
        return this.positionMap[id].process;
      }
      
      console.warn(`No process position found for container ${containerIdOrName}`);
      return [0, 0, 0]; // Default position
    }
    
    /**
     * Get both approach and process positions
     * @param {number|string} containerIdOrName - Container ID or name
     * @returns {Object} Object with approach and process positions
     */
    static getPositions(containerIdOrName) {
      const id = typeof containerIdOrName === 'string' 
        ? this.nameToId(containerIdOrName) 
        : containerIdOrName;
      
      return {
        approach: this.getApproachPosition(id),
        process: this.getProcessPosition(id)
      };
    }
    
    /**
     * Get the primary position (backwards compatibility)
     * @param {number|string} containerIdOrName - Container ID or name
     * @returns {Array} [x, y, Rz] position array (approach position)
     */
    static getPosition(containerIdOrName) {
      return this.getApproachPosition(containerIdOrName);
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
      
      // Updated positionMap with approach and process positions
      // Origin at bottom-left corner, X limit 960mm, Y limit 720mm
      static positionMap = {
        0: {
          approach: [120, 600, 0],    // Approach from flyway 0 (center)
          process: [120, 660, 0]      // Process is 60mm towards the module area
        },
        1: {
          approach: [360, 600, 0],    // Approach from flyway 1
          process: [360, 660, 0]
        },
        2: {
          approach: [600, 600, 0],    // Approach from flyway 2
          process: [600, 660, 0]
        },
        3: {
          approach: [840, 600, 0],    // Approach from new flyway column
          process: [840, 660, 0]
        },
        
        // Left edge - orientation 90 (east facing)
        4: {
          approach: [120, 600, 90],   // Approach from flyway 3
          process: [60, 600, 90]      // Process is 60mm to the left
        },
        6: {
          approach: [120, 360, 90],   // Approach from flyway 6
          process: [60, 360, 90]
        },
        9: {
            approach: [120, 240, 90],
            process: [60, 240, 90]
        },

        // Right edge - orientation 270 (west facing)
        5: {
            approach: [600, 840, 270],  // Approach from right flyway
            process: [600, 900, 270]    // Process is 60mm to the right
        },
        8: {
            approach: [360, 840, 270],  // Approach from right flyway
            process: [360, 900, 270]    // Process is 60mm to the right
        },
        10: {
            approach: [120, 840, 270],  // Approach from right flyway
            process: [120, 900, 270]    // Process is 60mm to the right
        },
        // Middle EM square
        7: {
          approach: [360, 360, 270],
          process: [420, 360, 270]    // Matches example data
        },

        // Bottom row - orientation 180 (north facing)
        11: {
          approach: [120, 120, 270],
          process: [120, 60, 270]
        },
        12: {
            approach: [360, 120, 270],
            process: [360, 60, 270]
        },
        13: {
            approach: [600, 120, 270],
            process: [600, 60, 270]
        },
        14: {
            approach: [840, 120, 270],
            process: [840, 60, 270]
        },
        };
    }
  
  export default MappingService;