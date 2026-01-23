import { useState, useEffect } from "react";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  rectIntersection,
  DragOverlay
} from "@dnd-kit/core";
import { FaTrashAlt } from 'react-icons/fa';
import { toast } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';

// Import components
import { Task } from "../components/Task/Task";
import { DroppableArea } from "../components/DroppableArea/DroppableArea";
import { NodeSidebar } from "../components/NodeSidebar/NodeSidebar";
import { ConfigPanel } from "../components/ConfigPanel/ConfigPanel";

// Import services
import aasService from '../services/AasService';
import MappingService from '../services/MappingService';

export default function PlanarMotorConfigurator() {
  // Available node categories and nodes
  const [moduleCatalog, setModuleCatalog] = useState([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [nodeCategories, setNodeCategories] = useState([]);

  // Flatten all nodes for easy lookup
  const allNodes = nodeCategories.flatMap(category => category.nodes);

  // Placed nodes in the grid
  const [activeId, setActiveId] = useState(null);
  const [activeDeletionZone, setActiveDeletionZone] = useState(null); // 'left', 'right', or null
  const [cursorPosition, setCursorPosition] = useState({ x: 0, y: 0 });
  // Create a 6x5 grid of containers (30 total)
  const containers = Array.from({ length: 30 }, (_, i) => `container${i + 1}`);

  const [placedNodes, setPlacedNodes] = useState(() => {
    try {
      const savedNodes = localStorage.getItem('planarMotorNodes');
      return savedNodes ? JSON.parse(savedNodes) : [];
    } catch (error) {
      console.error('Error loading nodes from localStorage:', error);
      return [];
    }
  });

  // Default config values
  const defaultConfig = {
    maxSpeedX: "5.0",
    maxSpeedY: "5.0",
    maxSpeedRz: "10.0",
    maxAccelX: "2.0",
    maxAccelY: "2.0",
    maxAccelRz: "5.0"
  };

  // Initialize motorConfig with values from localStorage if available
  const [motorConfig, setMotorConfig] = useState(() => {
    try {
      const savedConfig = localStorage.getItem('planarMotorConfig');
      return savedConfig ? JSON.parse(savedConfig) : defaultConfig;
    } catch (error) {
      console.error('Error loading config from localStorage:', error);
      return defaultConfig;
    }
  });

  // Save to localStorage whenever placedNodes changes
  useEffect(() => {
    try {
      localStorage.setItem('planarMotorNodes', JSON.stringify(placedNodes));
    } catch (error) {
      console.error('Error saving nodes to localStorage:', error);
      // Optionally show a toast notification here
    }
  }, [placedNodes]);

  // Load module catalog from AAS on startup
  useEffect(() => {
    const loadModuleCatalog = async () => {
      try {
        setCatalogLoading(true);
        
        // Build flat module list
        const modules = await aasService.buildModuleCatalog();
        setModuleCatalog(modules);
        
        // Build categorized catalog for sidebar
        const categories = aasService.buildCategorizedCatalog(modules);
        setNodeCategories(categories);
        
        toast.success(`Loaded ${modules.length} modules from AAS`);
      } catch (error) {
        console.error('Failed to load module catalog:', error);
        toast.warning('Using static module catalog - AAS not available');
        // Keep nodeCategories as empty array - no fallback to static data
        setNodeCategories([]);
      } finally {
        setCatalogLoading(false);
      }
    };
    
    loadModuleCatalog();
  }, []);

  // Save to localStorage whenever motorConfig changes
  useEffect(() => {
    try {
      localStorage.setItem('planarMotorConfig', JSON.stringify(motorConfig));
    } catch (error) {
      console.error('Error saving config to localStorage:', error);
      // Optionally show a toast notification here
    }
  }, [motorConfig]);
  
  // Handler for config changes
  const handleConfigChange = (newConfig) => {
    setMotorConfig(newConfig);
  };

  useEffect(() => {
    const updateMousePosition = (e) => {
      setCursorPosition({ x: e.clientX, y: e.clientY });
    };
    
    window.addEventListener('mousemove', updateMousePosition);
    
    return () => {
      window.removeEventListener('mousemove', updateMousePosition);
    };
  }, []);

  // Function to check if container is a corner (to be replaced with static squares)
  const isCornerPosition = (containerId) => {
    const id = parseInt(containerId.replace('container', ''));
    return id === 1 || id === 6 || id === 25 || id === 30;
  };

  // Function to check if container is the special Flyway 6 position that should be white
  const isSpecialFlyway = (containerId) => {
    return containerId === "container16";
  };

  // Function to determine if a container is in the middle black section
  const isBlackContainer = (containerId) => {
    if (isSpecialFlyway(containerId)) {
      return false;
    }
    
    const id = parseInt(containerId.replace('container', ''));
    
    // Calculate row and column (0-indexed)
    const row = Math.floor((id - 1) / 6);
    const col = (id - 1) % 6;
    
    // Check if in middle 4x3 section (rows 1,2,3 and columns 1,2,3,4)
    return row >= 1 && row <= 3 && col >= 1 && col <= 4;
  };

  // Function to get the appropriate name for a container
  const getContainerName = (containerId) => {
    // Special case for the Flyway 6 position which should be a Module Area
    if (isSpecialFlyway(containerId)) {
      return "Module Area 7";
    }
    
    const id = parseInt(containerId.replace('container', ''));
    const row = Math.floor((id - 1) / 6);
    const col = (id - 1) % 6;
    
    // Regular black containers (flyways)
    if (isBlackContainer(containerId)) {
      // For black containers - Flyway 0, Flyway 1, etc.
      // Calculate the index within the 4x3 black grid
      const blackRow = row - 1; // Black grid starts at row 1
      const blackCol = col - 1; // Black grid starts at col 1
      const flyWayIndex = blackRow * 4 + blackCol;
      return `Flyway ${flyWayIndex}`;
    } else {
      // For white containers - Module Area 0, Module Area 1, etc.
      // We need to count white cells sequentially
      let moduleAreaIndex = 0;
      
      for (let i = 1; i < id; i++) {
        const r = Math.floor((i - 1) / 6);
        const c = (i - 1) % 6;
        
        // Skip corner positions
        if (isCornerPosition(`container${i}`)) {
          continue;
        }
        
        // Count as module area if it's not black or it's the special flyway
        if (!(r >= 1 && r <= 3 && c >= 1 && c <= 4) || isSpecialFlyway(`container${i}`)) {
          moduleAreaIndex++;
        }
      }
      
      return `Module Area ${moduleAreaIndex}`;
    }
  };

  // Handler to delete a single node
  const handleDeleteNode = (nodeId) => {
    setPlacedNodes(prev => prev.filter(node => node.id !== nodeId));
  };
  
  // Also update the clear functions
  const handleClearStations = () => {
    if (window.confirm("Are you sure you want to clear all components from the grid?")) {
      setPlacedNodes([]);
      toast.info("All components cleared", { autoClose: 2000 });
    }
  };
  
  const handleClearLimits = () => {
    if (window.confirm("Are you sure you want to reset all speed and acceleration limits?")) {
      const defaultConfig = {
        maxSpeedX: "5.0",
        maxSpeedY: "5.0",
        maxSpeedRz: "10.0",
        maxAccelX: "2.0",
        maxAccelY: "2.0",
        maxAccelRz: "5.0"
      };
      
      setMotorConfig(defaultConfig);
      handleConfigChange(defaultConfig);
      toast.info("Speed and acceleration limits reset", { autoClose: 2000 });
    }
  };
  
  const handleClearAll = () => {
    if (window.confirm("Are you sure you want to clear ALL components and reset ALL limits?")) {
      setPlacedNodes([]);
      
      const defaultConfig = {
        maxSpeedX: "5.0",
        maxSpeedY: "5.0",
        maxSpeedRz: "10.0",
        maxAccelX: "2.0",
        maxAccelY: "2.0",
        maxAccelRz: "5.0"
      };
      
      setMotorConfig(defaultConfig);
      handleConfigChange(defaultConfig);
      toast.info("All configuration cleared", { autoClose: 2000 });
    }
  };

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor)
  );

  // Function to handle drag start
  const handleDragStart = (event) => {
    const { active } = event;
    setActiveId(active.id);
    
    // Find whether it's a sidebar node or placed node
    const isSidebarNode = allNodes.some(node => node.id === active.id);
    
    // Reset deletion zone when starting drag
    setActiveDeletionZone(null);
  };

  const handleSetDefaultStations = () => {
    // Default layout with specific module areas as requested
    const defaultStations = [
      // Module Area 1: IMA Filling System (container3)
      { 
        id: `placed-default-1-${Date.now()}`, 
        title: "imaFillingSystem", 
        container: "container3",
        color: "#1E7D74",
        sourceNode: "ima-filling",
        abstractId: "Filling" 
      },
      // Module Area 2: IMA Stoppering System (container4)
      { 
        id: `placed-default-2-${Date.now()}`, 
        title: "imaStopperingSystem", 
        container: "container4",
        color: "#0087CD",
        sourceNode: "ima-stoppering",
        abstractId: "Stoppering" 
      },
      // Module Area 8: Omron Camera (container19)
      { 
        id: `placed-default-3-${Date.now()}`, 
        title: "omronCamera", 
        container: "container18",
        color: "#2ECC71",
        sourceNode: "omron-camera",
        abstractId: "Camera" 
      },
      // Module Area 9: IMA Loading System (container23)
      { 
        id: `placed-default-4-${Date.now()}`, 
        title: "imaLoadingSystem", 
        container: "container19",
        color: "#FF8097",
        sourceNode: "ima-loading",
        abstractId: "Load" 
      },
      // Module Area 10: IMA Unloading System (container25)
      { 
        id: `placed-default-5-${Date.now()}`, 
        title: "imaUnloadingSystem", 
        container: "container24",
        color: "#F39C12",
        sourceNode: "ima-unloading",
        abstractId: "Unload" 
      }
    ];
    
    if (window.confirm("This will replace your current layout with the default stations. Continue?")) {
      setPlacedNodes(defaultStations);
      toast.info("Default layout set successfully", { autoClose: 2000 });
    }
  };

 // Updated handleDragMove function with better error handling
 const handleDragMove = (event) => {
  try {
    // First safely get the active element
    const { active } = event;
    
    // Safety check - if no active element, exit
    if (!active || !active.id) {
      setActiveDeletionZone(null);
      return;
    }
    
    // Only check for deletion zones when dragging a placed node (not from sidebar)
    const isPlacedNode = placedNodes.some(node => node.id === active.id);
    if (!isPlacedNode) {
      setActiveDeletionZone(null);
      return;
    }
    
    // Use the tracked cursor position instead of trying to get it from the event
    const pointerX = cursorPosition.x;
    
    // Get grid container wrapper dimensions
    const wrapperElement = document.querySelector('.grid-container-wrapper');
    if (!wrapperElement) {
      return;
    }
    
    const wrapperRect = wrapperElement.getBoundingClientRect();
    
    // Calculate deletion zone width - increased width
    const zoneWidth = 300;
    
    // Get the actual X position relative to the wrapper
    const relativeX = pointerX - wrapperRect.left;
    
    // Check if pointer is in left deletion zone
    if (relativeX < zoneWidth) {
      setActiveDeletionZone('left');
    }
    // Not in any deletion zone
    else {
      setActiveDeletionZone(null);
    }
  } catch (error) {
    console.error("Error in handleDragMove:", error);
  }
};
  // Updated drag end function to handle deletion
  const handleDragEnd = (event) => {
    const { active, over } = event;
    
    // Check if we were dragging a placed node and were in the deletion zone
    if (activeDeletionZone === 'left' && active && placedNodes.some(node => node.id === active.id)) {
      // Use the tracked cursor position for final check
      const pointerX = cursorPosition.x;
      const wrapperElement = document.querySelector('.grid-container-wrapper');
      
      if (wrapperElement) {
        const wrapperRect = wrapperElement.getBoundingClientRect();
        const relativeX = pointerX - wrapperRect.left;
        const zoneWidth = 300;
        
        const inLeftZone = relativeX < zoneWidth;
        
        if (inLeftZone) {
          setPlacedNodes(nodes => nodes.filter(node => node.id !== active.id));
        }
      }
      
      // Reset states
      setActiveDeletionZone(null);
      setActiveId(null);
      return; // Don't continue with normal drop processing
    }
    
    // Reset states
    setActiveDeletionZone(null);
    setActiveId(null);
    
    // Continue with normal drop processing
    if (!over) return;
    
    // Rest of the existing handleDragEnd code...
    const draggedNode = allNodes.find(node => node.id === active.id);
    
    
    if (draggedNode) {
      // This is a node from the sidebar - create a copy
      
      // Check if target container already has a node
      const containerHasNode = placedNodes.some(node => node.container === over.id);
      
      if (containerHasNode) {
        // If container already has a node, don't allow the drop
        return;
      }
      
      // Create a new unique ID for the placed node
      const newId = `placed-${Date.now()}`;
      
      // Add a new placed node with isNew flag for animation
      setPlacedNodes(nodes => [
        ...nodes, 
        { 
          id: newId, 
          title: draggedNode.title, 
          container: over.id,
          color: draggedNode.color,
          sourceNode: draggedNode.id,
          abstractId: draggedNode.abstractId,
          capabilities: draggedNode.capabilities,
          // Store full node data for display
          aasId: draggedNode.aasId,
          assetId: draggedNode.assetId,
          assetKind: draggedNode.assetKind,
          assetType: draggedNode.assetType,
          submodelId: draggedNode.submodelId,
          isNew: true // Add isNew flag to trigger animation
        }
      ]);
      
      // Remove the isNew flag after animation is complete
      setTimeout(() => {
        setPlacedNodes(nodes => 
          nodes.map(node => 
            node.id === newId ? { ...node, isNew: false } : node
          )
        );
      }, 10000); // Longer than animation duration
    } else {
      // This is moving an existing placed node
      const movedNode = placedNodes.find(node => node.id === active.id);
      
      if (movedNode && over.id !== movedNode.container) {
        // Check if target container already has a node
        const containerHasNode = placedNodes.some(node => 
          node.id !== movedNode.id && node.container === over.id
        );
        
        if (containerHasNode) {
          // If container already has a node, don't allow the drop
          return;
        }
        
        const movedNodeId = movedNode.id;
        
        // Move the node to the new container with isNew flag for animation
        setPlacedNodes(nodes => 
          nodes.map(node => 
            node.id === movedNodeId
              ? { ...node, container: over.id, isNew: true } 
              : node
          )
        );
        
        // Remove the isNew flag after animation is complete
        setTimeout(() => {
          setPlacedNodes(nodes => 
            nodes.map(node => 
              node.id === movedNodeId ? { ...node, isNew: false } : node
            )
          );
        }, 10000); // Longer than animation duration
      }
    }
  };

  const findNodesInContainer = (containerId) => {
    return placedNodes.filter(node => node.container === containerId);
  };

  // Find the currently active node
  const activeNodeTemplate = allNodes.find(node => node.id === activeId);
  const activePlacedNode = placedNodes.find(node => node.id === activeId);
  const activeNode = activeNodeTemplate || activePlacedNode;
  const isActiveSidebarNode = !!activeNodeTemplate;


  // Handler for saving configuration to AAS
  const handleSaveToAas = async () => {
    try {
      const layoutData = prepareLayoutData();
      
      // Save station layout to HierarchicalStructures submodel
      // Fetches globalAssetIds from registry to ensure consistency with existing AAS descriptors
      const hierarchicalStructures = await aasService.transformLayoutDataToHierarchicalStructures(layoutData);
      await aasService.putHierarchicalStructures(hierarchicalStructures);
      
      // Save motor config to planarTable Parameters submodel
      await aasService.putPlanarTableMotorConfig(motorConfig);
      
      toast.success('Configuration published to AAS successfully!');
    } catch (error) {
      console.error('Failed to publish configuration:', error);
      toast.error(`Failed to publish configuration: ${error.message}`);
    }
  };

  // Handler for loading configuration from AAS
  const handleLoadFromAas = async () => {
    try {
      // Load station layout from HierarchicalStructures
      const hierarchicalStructures = await aasService.getHierarchicalStructures();
      const layoutData = aasService.transformHierarchicalStructuresToLayoutData(
        hierarchicalStructures,
        moduleCatalog
      );
      
      // Load motor config from planarTable Parameters submodel
      const loadedMotorConfig = await aasService.getPlanarTableMotorConfig();
      if (loadedMotorConfig) {
        setMotorConfig(loadedMotorConfig);
        handleConfigChange(loadedMotorConfig);
      }
      
      // Convert layout data back to placed nodes format
      const loadedNodes = layoutData.Stations
        .filter(station => station.StationId !== -1) // Exclude fixed infrastructure
        .map((station, index) => {
          // Find matching node template from allNodes
          const matchingNode = allNodes.find(n => 
            n.abstractId === station.Name || 
            n.abstractId === station.AssetType ||
            n.assetType === station.AssetType ||
            n.title === station['Instance Name']
          );
          
          // Find appropriate container based on position
          const containerIndex = MappingService.idToName(station.StationId);
          
          return {
            id: `placed-${Date.now()}-${index}`,
            sourceNode: matchingNode?.id || station['Instance Name'],
            container: `container${containerIndex}`,
            title: station['Instance Name'],
            color: matchingNode?.color || '#888888',
            abstractId: station.AssetType || station.Name,
            assetType: station.AssetType || station.Name,
            capabilities: station.Capabilities,
            aasId: station.AasId,
            submodelId: station.SubmodelId
          };
        });
      
      setPlacedNodes(loadedNodes);
      toast.success('Configuration loaded from AAS successfully!');
    } catch (error) {
      console.error('Failed to load from AAS:', error);
      toast.error(`Failed to load configuration: ${error.message}`);
    }
  };

  const prepareLayoutData = () => {
    // Create the Stations array from placed nodes ONLY
    const stationsArray = placedNodes.map((node) => {
      const containerName = getContainerName(node.container);
      const stationId = MappingService.nameToId(containerName);
      const positions = MappingService.getPositions(stationId);
      
      // Use the node title as the instance name
      const instanceName = node.title || "Unknown System";
      
      return {
        "Instance Name": instanceName,
        "Approach Position": positions.approach,
        "Process Position": positions.process,
        "AssetId": node.assetId,
        "AasId": node.aasId,
        "SubmodelId": node.submodelId,
        "AssetType": node.assetType
      };
    });
    
    return {
      Stations: stationsArray
    };
  };


  return (
    <div className="planar-motor-page">
      <div className="page-header">
        <h1>Planar Motor Configurator</h1>
        {catalogLoading && <span className="loading-indicator">Loading modules...</span>}
      </div>
      
      <DndContext
        sensors={sensors}
        collisionDetection={rectIntersection}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onDragMove={handleDragMove}
      >
        <div className="configurator-content">
          <NodeSidebar categories={nodeCategories} />
          
          <div className="configurator-main">
            <div className="grid-container-wrapper">
              {/* Left deletion zone - now wider */}
              <div 
                className={`deletion-zone left ${activeDeletionZone === 'left' ? 'active' : ''}`}
                style={{ opacity: activeDeletionZone === 'left' ? 1 : 0.5 }}
              >
                <FaTrashAlt className="delete-icon" />
              </div>
              
              <div className="grid-container">
                {/* Static corner elements */}
                <div className="static-corner"></div>
                <div className="static-corner"></div>
                <div className="static-corner"></div>
                <div className="static-corner"></div>
                
                {/* Droppable areas */}
                {containers
                  .filter(containerId => !isCornerPosition(containerId))
                  .map(containerId => (
                    <DroppableArea 
                      key={containerId} 
                      id={containerId} 
                      isBlack={isBlackContainer(containerId)}
                      name={getContainerName(containerId)}
                    >
                      {findNodesInContainer(containerId)
                        .filter(node => node.id !== activeId)
                        .map(node => (
                          <Task 
                            key={node.id} 
                            id={node.id} 
                            title={node.title} 
                            color={node.color}
                            inSidebar={false}
                            onDelete={handleDeleteNode}
                            nodeData={{
                              assetId: node.assetId,
                              aasId: node.aasId,
                              assetKind: node.assetKind,
                              assetType: node.assetType
                            }}
                          />
                        ))
                      }
                    </DroppableArea>
                  ))
                }
              </div>
            </div>
          </div>
          <ConfigPanel 
            onChange={handleConfigChange} 
            onClearStations={handleClearStations}
            onClearLimits={handleClearLimits}
            onClearAll={handleClearAll}
            onSetDefaultStations={handleSetDefaultStations}
            onPublishConfig={handleSaveToAas}
            publishDisabled={catalogLoading || placedNodes.length === 0}
            config={motorConfig}
          />
        </div>
               
        <DragOverlay dropAnimation={null}>
          {activeId && activeNode ? (
            <div className="drag-overlay-container">
              <Task 
                id={activeId} 
                title={activeNode.title} 
                color={activeNode.color}
                inSidebar={isActiveSidebarNode}
                isTemplate={true}
                isDraggingToDelete={activeDeletionZone !== null}
              />
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}