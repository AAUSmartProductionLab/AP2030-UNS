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
import { FaTrashAlt } from 'react-icons/fa'; // Install this package if needed
import { ToastContainer, toast } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';

// Import components
import { Task } from "../components/Task/Task";
import { DroppableArea } from "../components/DroppableArea/DroppableArea";
import { NodeSidebar } from "../components/NodeSidebar/NodeSidebar";
import { ConfigPanel } from "../components/ConfigPanel/ConfigPanel";

// Import services
import mqttService from '../services/MqttService';
import MappingService from '../services/MappingService';

export default function PlanarMotorConfigurator() {
  // Available node categories and nodes
  const [mqttConnected, setMqttConnected] = useState(false);
  const nodeCategories = [
    {
      id: "filling-modules",
      name: "Filling Modules",
      nodes: [
        { 
          id: "ima-filling", 
          title: "IMA Filling System", 
          color: "#1E7D74", 
          abstractId: "Filling" 
        },
        { 
          id: "syntegon-filling", 
          title: "Syntegon Filling System", 
          color: "#30A399", 
          abstractId: "Filling" 
        },
        { 
          id: "optima-filling", 
          title: "Optima Filling System", 
          color: "#136058", 
          abstractId: "Filling" 
        }
      ]
    },
    {
      id: "stoppering-modules",
      name: "Stoppering Modules",
      nodes: [
        { 
          id: "ima-stoppering", 
          title: "IMA Stoppering System", 
          color: "#0087CD", 
          abstractId: "Stoppering" 
        },
        { 
          id: "syntegon-stoppering", 
          title: "Syntegon Stoppering System", 
          color: "#00A0F0", 
          abstractId: "Stoppering" 
        },
        { 
          id: "optima-stoppering", 
          title: "Optima Stoppering System", 
          color: "#006CA3", 
          abstractId: "Stoppering" 
        }
      ]
    },
    {
      id: "capping-modules",
      name: "Capping Modules",
      nodes: [
        { 
          id: "ima-capping", 
          title: "IMA Capping System", 
          color: "#9B4DCA", 
          abstractId: "Capping" 
        },
        { 
          id: "syntegon-capping", 
          title: "Syntegon Capping System", 
          color: "#B07EDE", 
          abstractId: "Capping" 
        },
        { 
          id: "optima-capping", 
          title: "Optima Capping System", 
          color: "#7939A0", 
          abstractId: "Capping" 
        }
      ]
    },
    {
      id: "loading-modules",
      name: "Loading Modules",
      nodes: [
        { 
          id: "ima-loading", 
          title: "IMA Loading System", 
          color: "#FF8097", 
          abstractId: "Load" 
        },
        { 
          id: "syntegon-loading", 
          title: "Syntegon Loading System", 
          color: "#FF9EB0", 
          abstractId: "Load" 
        },
        { 
          id: "optima-loading", 
          title: "Optima Loading System", 
          color: "#FF6080", 
          abstractId: "Load" 
        }
      ]
    },
    {
      id: "unloading-modules",
      name: "Unloading Modules",
      nodes: [
        { 
          id: "ima-unloading", 
          title: "IMA Unloading System", 
          color: "#F39C12", 
          abstractId: "Unload" 
        },
        { 
          id: "syntegon-unloading", 
          title: "Syntegon Unloading System", 
          color: "#FFB142", 
          abstractId: "Unload" 
        },
        { 
          id: "optima-unloading", 
          title: "Optima Unloading System", 
          color: "#E67E22", 
          abstractId: "Unload" 
        }
      ]
    },
    {
      id: "sensors",
      name: "Sensors",
      nodes: [
        { 
          id: "omron-camera", 
          title: "Omron Camera", 
          color: "#2ECC71", 
          abstractId: "Camera" 
        },
        { 
          id: "omron-linetracker", 
          title: "Omron LineTracker", 
          color: "#27AE60", 
          abstractId: "LineTracker" 
        },
        { 
          id: "quality-sensor", 
          title: "Quality Control Sensor", 
          color: "#1BBC9B", 
          abstractId: "QualitySensor" 
        },
        { 
          id: "weight-sensor", 
          title: "Weight Verification", 
          color: "#16A085", 
          abstractId: "WeightSensor" 
        }
      ]
    }
  ];

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
    console.log("Updated configuration:", newConfig);
  };

  useEffect(() => {
    // Register for connection status updates only
    const unsubscribeConnection = mqttService.onConnectionChange(setMqttConnected);
    
    return () => {
      unsubscribeConnection();
    };
  }, []);

  useEffect(() => {
    const updateMousePosition = (e) => {
      setCursorPosition({ x: e.clientX, y: e.clientY });
    };
    
    window.addEventListener('mousemove', updateMousePosition);
    
    return () => {
      window.removeEventListener('mousemove', updateMousePosition);
    };
  }, []);

  const centerOnCursorModifier = ({ transform }) => {
    // Just return the transform as is - let CSS handle the centering
    return transform;
  };

  const [draggingNodeRect, setDraggingNodeRect] = useState(null);
  
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

  const handleSubmit = (showNotification = true) => {
    const layoutData = prepareLayoutData();
    const success = mqttService.publishLayout(layoutData);
    
    if (showNotification) {
      if (success) {
        toast.success("Stations published successfully!", { autoClose: 3000 });
      } else {
        toast.error("Failed to publish stations", { autoClose: 5000 });
      }
    }
    
    return success;
  };
  
  // Replace the handleSubmitLowest function
  const handleSubmitLowest = () => {
    const success = mqttService.publishLimits(motorConfig);
    
    if (success) {
      toast.success("Limits published successfully!", { autoClose: 3000 });
    } else {
      toast.error("Failed to publish limits", { autoClose: 5000 });
    }
    
    return success;
  };
  
  // Replace the handlePublishConfig function
  const handlePublishConfig = () => {
    // Call both publish functions but suppress their individual notifications
    const stationsSuccess = handleSubmit(false);
    const limitsSuccess = mqttService.publishLimits(motorConfig);
    
    // Show a single consolidated notification based on results
    if (stationsSuccess && limitsSuccess) {
      toast.success("Complete configuration published successfully!", { autoClose: 3000 });
    } else if (!stationsSuccess && !limitsSuccess) {
      toast.error("Failed to publish configuration", { autoClose: 5000 });
    } else if (!stationsSuccess) {
      toast.warning("Published limits but failed to publish stations", { autoClose: 4000 });
    } else {
      toast.warning("Published stations but failed to publish limits", { autoClose: 4000 });
    }
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
    
    // Get dimensions from the DOM directly for more accuracy
    const activeElement = document.querySelector(`[data-id="${active.id}"]`);
    
    if (activeElement) {
      const rect = activeElement.getBoundingClientRect();
      console.log("Capturing actual DOM node dimensions:", rect.width, "x", rect.height);
      setDraggingNodeRect({
        width: rect.width,
        height: rect.height
      });
    } else if (active.rect && active.rect.current && active.rect.current.initialized) {
      console.log("Capturing DnD Kit rect dimensions:", active.rect.current.width, "x", active.rect.current.height);
      setDraggingNodeRect({
        width: active.rect.current.width,
        height: active.rect.current.height
      });
    } else {
      // Fallback to approximate dimensions based on node type
      const dimensions = isSidebarNode ? 
        { width: 200, height: 80 } : 
        { width: 100, height: 100 };
      console.log("Using default dimensions:", dimensions.width, "x", dimensions.height);
      setDraggingNodeRect(dimensions);
    }
    
    // Reset deletion zone when starting drag
    setActiveDeletionZone(null);
  };

  const handleSetDefaultStations = () => {
    // Default layout with specific module areas as requested
    const defaultStations = [
      // Module Area 1: IMA Filling System (container3)
      { 
        id: `placed-default-1-${Date.now()}`, 
        title: "IMA Filling System", 
        container: "container3",
        color: "#1E7D74",
        sourceNode: "ima-filling",
        abstractId: "Filling" 
      },
      // Module Area 2: IMA Stoppering System (container4)
      { 
        id: `placed-default-2-${Date.now()}`, 
        title: "IMA Stoppering System", 
        container: "container4",
        color: "#0087CD",
        sourceNode: "ima-stoppering",
        abstractId: "Stoppering" 
      },
      // Module Area 8: Omron Camera (container19)
      { 
        id: `placed-default-3-${Date.now()}`, 
        title: "Omron Camera", 
        container: "container18",
        color: "#2ECC71",
        sourceNode: "omron-camera",
        abstractId: "Camera" 
      },
      // Module Area 9: IMA Loading System (container23)
      { 
        id: `placed-default-4-${Date.now()}`, 
        title: "IMA Loading System", 
        container: "container19",
        color: "#FF8097",
        sourceNode: "ima-loading",
        abstractId: "Load" 
      },
      // Module Area 10: IMA Unloading System (container25)
      { 
        id: `placed-default-5-${Date.now()}`, 
        title: "IMA Unloading System", 
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
    console.log("DragMove triggered");
    
    // First safely get the active element
    const { active } = event;
    
    // Safety check - if no active element, exit
    if (!active || !active.id) {
      console.log("No active element");
      setActiveDeletionZone(null);
      return;
    }
    
    // Only check for deletion zones when dragging a placed node (not from sidebar)
    const isPlacedNode = placedNodes.some(node => node.id === active.id);
    if (!isPlacedNode) {
      console.log("Not a placed node, skipping");
      setActiveDeletionZone(null);
      return;
    }
    
    // Use the tracked cursor position instead of trying to get it from the event
    const pointerX = cursorPosition.x;
    console.log(`Using tracked cursor position: ${pointerX}`);
    
    // Get grid container wrapper dimensions
    const wrapperElement = document.querySelector('.grid-container-wrapper');
    if (!wrapperElement) {
      console.error("Couldn't find grid-container-wrapper element");
      return;
    }
    
    const wrapperRect = wrapperElement.getBoundingClientRect();
    
    // Calculate deletion zone width - increased width
    const zoneWidth = 300; // Increased from 200
    
    // Get the actual X position relative to the wrapper
    const relativeX = pointerX - wrapperRect.left;
    
    console.log(`RelativeX: ${relativeX}, ZoneWidth: ${zoneWidth}`);
    
    // Check if pointer is in left deletion zone
    if (relativeX < zoneWidth) {
      console.log("IN LEFT ZONE");
      setActiveDeletionZone('left');
    }
    // Not in any deletion zone
    else {
      if (activeDeletionZone !== null) {
        console.log("NOT IN ZONE");
      }
      setActiveDeletionZone(null);
    }
  } catch (error) {
    console.error("Error in handleDragMove:", error);
  }
};
  // Updated drag end function to handle deletion
  const handleDragEnd = (event) => {
    const { active, over } = event;
    
    console.log(`Drag ended. Active: ${active?.id}, Zone: ${activeDeletionZone}`);
    
    // Check if we were dragging a placed node and were in the deletion zone
    if (activeDeletionZone === 'left' && active && placedNodes.some(node => node.id === active.id)) {
      console.log(`Attempting to delete node ${active.id} from left zone`);
      
      // Use the tracked cursor position for final check
      const pointerX = cursorPosition.x;
      const wrapperElement = document.querySelector('.grid-container-wrapper');
      
      if (wrapperElement) {
        const wrapperRect = wrapperElement.getBoundingClientRect();
        const relativeX = pointerX - wrapperRect.left;
        const zoneWidth = 300; // Match the increased width
        
        // Log final position info for debugging
        console.log(`Final position: x=${pointerX}, relativeX=${relativeX}`);
        console.log(`Left zone: 0-${zoneWidth}`);
        
        // Verify we're in the expected zone at the end of the drag
        const inLeftZone = relativeX < zoneWidth;
        
        console.log(`In left zone: ${inLeftZone}`);
        
        // Only delete if we're actually in the zone
        if (inLeftZone) {
          // Remove the node
          console.log("Deleting node now!");
          setPlacedNodes(nodes => nodes.filter(node => node.id !== active.id));
        } else {
          console.log("Not in deletion zone at end of drag, not deleting");
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
      
      console.log(`Creating new node ${newId} with isNew=true`);
      
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
          isNew: true // Add isNew flag to trigger animation
        }
      ]);
      
      // Remove the isNew flag after animation is complete
      setTimeout(() => {
        console.log(`Setting isNew=false for node ${newId}`);
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
        console.log(`Moving node ${movedNodeId} with isNew=true`);
        
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
          console.log(`Setting isNew=false for node ${movedNodeId}`);
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


  const prepareLayoutData = () => {
    // Create the Stations array
    const stationsArray = placedNodes.map(node => {
      const containerName = getContainerName(node.container);
      const stationId = MappingService.nameToId(containerName);
      const positions = MappingService.getPositions(stationId);
      
      // Find the source node to get the abstractId if not directly on placed node
      const sourceNode = node.abstractId ? 
        null : 
        allNodes.find(n => n.id === node.sourceNode);
      
      const abstractId = node.abstractId || 
        (sourceNode ? sourceNode.abstractId : "Unknown");
      
      return {
        Name: abstractId, // Use the abstractId as the Name
        StationId: stationId,
        "Approach Position": positions.approach,
        "Process Position": positions.process,
      };
    });
    
    // Return the properly formatted object
    return {
      Stations: stationsArray
    };
  };


  return (
    <div className="planar-motor-page">
      <h1>Planar Motor Configurator</h1>
      
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
            onSubmit={handleSubmit}
            onSubmitLowest={handleSubmitLowest}
            onPublishConfig={handlePublishConfig}
            onSetDefaultStations={handleSetDefaultStations}
            config={motorConfig} // Pass the current config to use for display
          />
        </div>
               
        {/* DragOverlay remains unchanged */}
        <DragOverlay 
          dropAnimation={null}
          modifiers={[centerOnCursorModifier]}
        >
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