import React, { useState, useEffect, useMemo, useRef } from "react";
import { usePlanarMotorContext } from '../contexts/PlanarMotorContext';
import mqttService from '../services/MqttService'; // Import MQTT service
import "../styles/XbotTracker.css";

const XbotTracker = () => {
  const { placedNodes } = usePlanarMotorContext();
  
  const FLYWAY_SIZE = 240;
  const XBOT_SIZE = 120;
  const GRID_COLS = 4;
  const GRID_ROWS = 3;
  const totalWidth = GRID_COLS * FLYWAY_SIZE;
  const totalHeight = GRID_ROWS * FLYWAY_SIZE;
  const containerWidth = totalWidth + (2 * FLYWAY_SIZE);
  const containerHeight = totalHeight + (2 * FLYWAY_SIZE);

  const LERP_FACTOR = 0.15; 
  const SNAP_THRESHOLD = 0.5;

  // Define Xbot states (used for UI mapping)
  const xbotStates = {
    "idle": { color: "#FFD700", label: "Idle" },
    "stopped": { color: "#FF4D4D", label: "Stopped" },
    "executing": { color: "#3478F6", label: "Executing" }, // Already present, ensure "execute" from MQTT maps to this
    "execute": { color: "#3478F6", label: "Execute" }, // Explicitly adding "execute" if it comes as such
    "complete": { color: "#4CD964", label: "Complete" },
    "resetting": { color: "#FF9500", label: "Resetting" },
    "error": { color: "#FF3B30", label: "Error" },
    "waiting": { color: "#8E8E93", label: "Waiting" },
    "starting": { color: "#5AC8FA", label: "Starting" }, // New
    "stopping": { color: "#FFBF00", label: "Stopping" }  // New
    // Add any other states that might come from MQTT if they differ
  };
  
  // Define Station states (used for UI mapping)
  const stationDisplayStates = {
    "idle": { color: "#FFD700", label: "Idle" },
    "stopped": { color: "#FF4D4D", label: "Stopped" },
    "executing": { color: "#3478F6", label: "Executing" }, // Already present
    "execute": { color: "#3478F6", label: "Execute" }, // Explicitly adding "execute"
    "complete": { color: "#4CD964", label: "Complete" },
    "resetting": { color: "#FF9500", label: "Resetting" },
    "error": { color: "#FF3B30", label: "Error" },
    "waiting": { color: "#8E8E93", label: "Waiting" },
    "starting": { color: "#5AC8FA", label: "Starting" }, // New
    "stopping": { color: "#FFBF00", label: "Stopping" }  // New
  };
  // Default state for Xbots before MQTT update
  const getXbotDefaultState = (xbotId) => {
    const states = Object.keys(xbotStates);
    return states[xbotId % states.length]; 
  };

  const getStationId = (position, index) => {
    const idMap = {
      "top-0": 0, "top-1": 1, "top-2": 2, "top-3": 3,
      "right-0": 5, "right-1": 8, "right-2": 10,
      "bottom-3": 14, "bottom-2": 13, "bottom-1": 12, "bottom-0": 11,
      "left-2": 9, "left-1": 6, "left-0": 4,
      "middle-0": 7,
    };
    return idMap[`${position}-${index}`];
  };
  
  const [xbots, setXbots] = useState(() => {
    try {
      const savedXbots = localStorage.getItem('xbotPositions');
      if (savedXbots) {
        const parsed = JSON.parse(savedXbots);
        return parsed.map(bot => ({
          ...bot,
          targetX: bot.targetX !== undefined ? bot.targetX : bot.x,
          targetY: bot.targetY !== undefined ? bot.targetY : bot.y,
          targetYaw: bot.targetYaw !== undefined ? bot.targetYaw : bot.yaw,
          currentState: bot.currentState || getXbotDefaultState(bot.id) 
        }));
      }
      const initialBots = [
        { id: 1, x: 360, y: totalHeight - 600, yaw: 270, color: "#0033A0" }, 
        { id: 2, x: 600, y: totalHeight - 600, yaw: 270, color: "#00A0AF" }
      ];
      return initialBots.map(bot => ({
        ...bot,
        targetX: bot.x, targetY: bot.y, targetYaw: bot.yaw,
        currentState: getXbotDefaultState(bot.id) 
      }));
    } catch (error) {
      console.error('Error loading xbot positions from localStorage:', error);
      const errorBots = [
        { id: 1, x: 360, y: totalHeight - 600, yaw: 270, color: "#0033A0" },
        { id: 2, x: 600, y: totalHeight - 600, yaw: 270, color: "#00A0AF" }
      ];
      return errorBots.map(bot => ({
        ...bot,
        targetX: bot.x, targetY: bot.y, targetYaw: bot.yaw,
        currentState: getXbotDefaultState(bot.id) 
      }));
    }
  });

  const [selectedXbot, setSelectedXbot] = useState(() => {
    try {
      const savedSelectedId = localStorage.getItem('selectedXbot');
      if (savedSelectedId !== null) {
        const id = parseInt(savedSelectedId, 10);
        return id;
      }
      const initialBotsDirect = [
        { id: 1, x: 360, y: totalHeight - 600, yaw: 270, color: "#0033A0" },
        { id: 2, x: 600, y: totalHeight - 600, yaw: 270, color: "#00A0AF" }
      ];
      return initialBotsDirect.length > 0 ? initialBotsDirect[0].id : null;
    } catch (error) {
      console.error('Error loading selected xbot from localStorage:', error);
      const fallbackInitialXbots = [
        { id: 1, x: 360, y: totalHeight - 600, yaw: 270, color: "#0033A0" },
        { id: 2, x: 600, y: totalHeight - 600, yaw: 270, color: "#00A0AF" }
      ];
      return fallbackInitialXbots.length > 0 ? fallbackInitialXbots[0].id : null;
    }
  });

  const [mqttConnected, setMqttConnected] = useState(mqttService.isConnected);
  const [stationLiveStates, setStationLiveStates] = useState({});
  const animationFrameId = useRef(null);
  const xbotsRef = useRef(xbots); 

  useEffect(() => {
    xbotsRef.current = xbots; 
  }, [xbots]);

  useEffect(() => {
    localStorage.setItem('xbotPositions', JSON.stringify(xbots));
  }, [xbots]);
  
  useEffect(() => {
    if (selectedXbot !== null) {
      localStorage.setItem('selectedXbot', selectedXbot.toString());
    } else {
      localStorage.removeItem('selectedXbot');
    }
  }, [selectedXbot]);

  useEffect(() => {
    const unsubscribeConnection = mqttService.onConnectionChange(setMqttConnected);
    return () => unsubscribeConnection();
  }, []);

  const xbotIdSignature = useMemo(() => {
    return xbots.map(x => x.id).sort((a, b) => a - b).join(',');
  }, [xbots]); 

  // MQTT Subscriptions for Xbot Poses and States
  useEffect(() => {
    if (!mqttConnected) {
      // console.log("XbotTracker: MQTT not connected, skipping Xbot subscriptions.");
      return;
    }
    // console.log(`XbotTracker: (Re)Setting Xbot MQTT subscriptions for ID signature: "${xbotIdSignature}"`);

    const allUnsubscribes = [];

    xbotsRef.current.forEach(xbotSubConfig => {
      const xbotMqttId = `Xbot${xbotSubConfig.id}`;
      
      // Pose Subscription
      const poseTopic = `NN/Nybrovej/InnoLab/Planar/${xbotMqttId}/DATA/Pose`;
      // console.log(`XbotTracker: Subscribing to ${poseTopic} for Xbot ID ${xbotSubConfig.id}`);
      const unsubscribePose = mqttService.onMessage(poseTopic, (message) => {
        try {
          const poseData = typeof message === 'string' ? JSON.parse(message) : message;
          setXbots(prevXbots => 
            prevXbots.map(prevXbot => 
              prevXbot.id === xbotSubConfig.id
              ? { 
                  ...prevXbot, 
                  targetX: poseData.X !== undefined ? parseFloat(poseData.X) * 1000 : prevXbot.targetX,
                  targetY: poseData.Y !== undefined ? parseFloat(poseData.Y) * 1000 : prevXbot.targetY,
                  targetYaw: poseData.Rz !== undefined ? parseFloat(poseData.Rz) : prevXbot.targetYaw
                } 
              : prevXbot
            )
          );
        } catch (error) {
          console.error(`XbotTracker: Error processing pose message for Xbot ID ${xbotSubConfig.id} on topic ${poseTopic}:`, error, "Raw message:", message);
        }
      });
      allUnsubscribes.push(unsubscribePose);

      // State Subscription
      const stateTopic = `NN/Nybrovej/InnoLab/Planar/${xbotMqttId}/DATA/State`;
      // console.log(`XbotTracker: Subscribing to ${stateTopic} for Xbot ID ${xbotSubConfig.id}`);
      const unsubscribeState = mqttService.onMessage(stateTopic, (message) => {
        try {
          const stateData = typeof message === 'string' ? JSON.parse(message) : message;
          const newStateKey = stateData.State?.toLowerCase(); 
          if (newStateKey && xbotStates[newStateKey]) { 
            setXbots(prevXbots =>
              prevXbots.map(prevXbot =>
                prevXbot.id === xbotSubConfig.id
                ? { ...prevXbot, currentState: newStateKey }
                : prevXbot
              )
            );
          } else {
            console.warn(`XbotTracker: Received unknown state "${stateData.State}" for Xbot ID ${xbotSubConfig.id} from topic ${stateTopic}`);
          }
        } catch (error) {
          console.error(`XbotTracker: Error processing state message for Xbot ID ${xbotSubConfig.id} on topic ${stateTopic}:`, error, "Raw message:", message);
        }
      });
      allUnsubscribes.push(unsubscribeState);
    });

    return () => {
      // console.log(`XbotTracker: Cleaning up Xbot MQTT subscriptions for ID signature: "${xbotIdSignature}"`);
      allUnsubscribes.forEach(unsubscribe => unsubscribe());
    };
  }, [xbotIdSignature, mqttConnected]);

  const configuredStations = useMemo(() => {
    if (!placedNodes || !placedNodes.length) return [];
    return placedNodes.map(node => {
      const containerId = parseInt(node.container.replace('container', ''));
      const originalRow = Math.floor((containerId - 1) / 6);
      const originalCol = (containerId - 1) % 6;
      let position, index;
      if (originalRow === 0 && originalCol > 0 && originalCol < 5) { position = "top"; index = originalCol - 1; }
      else if (originalRow === 4 && originalCol > 0 && originalCol < 5) { position = "bottom"; index = originalCol - 1; }
      else if (originalCol === 0 && originalRow > 0 && originalRow < 4) { position = "left"; index = originalRow - 1; }
      else if (originalCol === 5 && originalRow > 0 && originalRow < 4) { position = "right"; index = originalRow - 1; }
      else if (containerId === 16 || (originalRow === 2 && originalCol === 3)) { position = "middle"; index = 0; } 
      else { return null; }
      
      if ((position === "top" || position === "bottom") && (index < 0 || index >= GRID_COLS)) return null;
      if ((position === "left" || position === "right") && (index < 0 || index >= GRID_ROWS)) return null;

      if (position) return { id: node.title, abstractId: node.abstractId, position: position, index: index, color: node.color };
      return null;
    }).filter(Boolean);
  }, [placedNodes]);

  // MQTT Subscriptions for Station States
  useEffect(() => {
    if (!mqttConnected || !configuredStations || configuredStations.length === 0) {
      // if (!mqttConnected) console.log("StationTracker: MQTT not connected, skipping station subscriptions.");
      return;
    }
    // console.log(`StationTracker: (Re)Setting Station MQTT subscriptions. Count: ${configuredStations.length}`);

    const stationUnsubscribes = [];

    configuredStations.forEach(station => {
      if (!station.abstractId) {
        console.warn(`StationTracker: Station ${station.id} (Pos: ${station.position}-${station.index}) is missing abstractId, cannot subscribe to state topic.`);
        return;
      }
      // Correctly capitalize the abstractId for the topic
      const stationTypeForTopic = station.abstractId.charAt(0).toUpperCase() + station.abstractId.slice(1).toLowerCase();
      const topic = `NN/Nybrovej/InnoLab/${stationTypeForTopic}/DATA/State`;
      const stationNumericId = getStationId(station.position, station.index);

      // console.log(`StationTracker: Subscribing to ${topic} for Station ID ${station.id} (Numeric: ${stationNumericId})`);
      
      const unsubscribe = mqttService.onMessage(topic, (message) => {
        try {
          const stateData = typeof message === 'string' ? JSON.parse(message) : message;
          const newStateKey = stateData.State?.toLowerCase();

          if (newStateKey && stationDisplayStates[newStateKey]) { 
            setStationLiveStates(prevStates => ({
              ...prevStates,
              [stationNumericId]: newStateKey,
            }));
          } else {
            console.warn(`StationTracker: Received unknown state "${stateData.State}" for station ${station.id} on topic ${topic}`);
          }
        } catch (error) {
          console.error(`StationTracker: Error processing message for station ${station.id} on topic ${topic}:`, error, "Raw message:", message);
        }
      });
      stationUnsubscribes.push(unsubscribe);
    });

    return () => {
      // console.log("StationTracker: Cleaning up Station MQTT subscriptions.");
      stationUnsubscribes.forEach(unsubscribe => unsubscribe());
    };
  }, [configuredStations, mqttConnected]);


  // Animation Loop Effect
  useEffect(() => {
    let isActive = true;

    const animate = () => {
      if (!isActive) return;

      let needsAnotherFrame = false;
      const currentBotsSnapshot = xbotsRef.current; 

      const newAnimatedBots = currentBotsSnapshot.map(bot => {
        let newX = bot.x;
        let newY = bot.y;
        let newYaw = bot.yaw;
        let botMovedThisFrame = false;

        if (Math.abs(bot.targetX - bot.x) > SNAP_THRESHOLD) {
          newX = bot.x + (bot.targetX - bot.x) * LERP_FACTOR;
          botMovedThisFrame = true;
        } else {
          newX = bot.targetX; 
        }

        if (Math.abs(bot.targetY - bot.y) > SNAP_THRESHOLD) {
          newY = bot.y + (bot.targetY - bot.y) * LERP_FACTOR;
          botMovedThisFrame = true;
        } else {
          newY = bot.targetY; 
        }
        
        let yawDiff = bot.targetYaw - bot.yaw;
        if (Math.abs(yawDiff) > 180) { 
          yawDiff = yawDiff > 0 ? yawDiff - 360 : yawDiff + 360;
        }
        if (Math.abs(yawDiff) > SNAP_THRESHOLD) { 
            newYaw = bot.yaw + yawDiff * LERP_FACTOR;
            botMovedThisFrame = true;
        } else {
            newYaw = bot.targetYaw; 
        }
        newYaw = (newYaw % 360 + 360) % 360; // Normalize yaw

        if (botMovedThisFrame || newX !== bot.targetX || newY !== bot.targetY || newYaw !== bot.targetYaw) {
          if (Math.abs(bot.targetX - newX) > 0.01 || Math.abs(bot.targetY - newY) > 0.01 || Math.abs(bot.targetYaw - newYaw) > 0.01) {
             needsAnotherFrame = true;
          }
        }
        
        return { ...bot, x: newX, y: newY, yaw: newYaw };
      });

      if (newAnimatedBots.some((b, i) => b.x !== currentBotsSnapshot[i].x || b.y !== currentBotsSnapshot[i].y || b.yaw !== currentBotsSnapshot[i].yaw)) {
        setXbots(newAnimatedBots);
      }

      if (needsAnotherFrame) {
        animationFrameId.current = requestAnimationFrame(animate);
      } else {
        animationFrameId.current = null; 
      }
    };

    const shouldStartAnimation = xbotsRef.current.some(b => 
        Math.abs(b.targetX - b.x) > SNAP_THRESHOLD || 
        Math.abs(b.targetY - b.y) > SNAP_THRESHOLD ||
        Math.abs(b.targetYaw - b.yaw) > SNAP_THRESHOLD
    );

    if (shouldStartAnimation && animationFrameId.current === null) { 
        animationFrameId.current = requestAnimationFrame(animate);
    }
    
    return () => {
      isActive = false;
      if (animationFrameId.current) {
        cancelAnimationFrame(animationFrameId.current);
        animationFrameId.current = null;
      }
    };
  }, [xbots]); 
  
  const handleAddXbot = () => {
    const nextId = xbots.length > 0 ? Math.max(...xbots.map(xbot => xbot.id)) + 1 : 1;
    let newX, newY;
    const holeXMin = 2 * FLYWAY_SIZE;
    const holeXMax = 3 * FLYWAY_SIZE;
    const holeYMin_newSystem = 1 * FLYWAY_SIZE; 
    const holeYMax_newSystem = 2 * FLYWAY_SIZE;

    do {
      newX = Math.random() * (totalWidth - XBOT_SIZE) + XBOT_SIZE / 2; 
      newY = Math.random() * (totalHeight - XBOT_SIZE) + XBOT_SIZE / 2; 
    } while (
      (newX > holeXMin && newX < holeXMax) &&
      (newY > holeYMin_newSystem && newY < holeYMax_newSystem)
    );
    
    const colorsForSelector = ["#0033A0", "#00A0AF", "#FF6B45", "#7C35B1", "#00B388", "#FFB819"];
    const randomColorForSelector = colorsForSelector[Math.floor(Math.random() * colorsForSelector.length)];
    
    const newXbot = { 
        id: nextId, x: newX, y: newY, yaw: 0, 
        color: randomColorForSelector, 
        targetX: newX, targetY: newY, targetYaw: 0,
        currentState: getXbotDefaultState(nextId)
    };
    setXbots(prevXbots => [...prevXbots, newXbot]);
    setSelectedXbot(nextId);
  };
  
  const handleRemoveXbot = () => {
    if (xbots.length <= 1) return;
    const filteredXbots = xbots.filter(xbot => xbot.id !== selectedXbot);
    setXbots(filteredXbots);
    if (filteredXbots.length > 0) {
      setSelectedXbot(filteredXbots[0].id);
    } else {
      setSelectedXbot(null);
    }
  };
  
  const renderGridCells = () => {
    const cells = [];
    for (let row = 0; row < GRID_ROWS; row++) {
      for (let col = 0; col < GRID_COLS; col++) {
        if (col === 2 && row === 1) continue; 
        cells.push(
          <div 
            key={`cell-${col}-${row}`} 
            className="grid-cell"
            style={{ 
              left: col * FLYWAY_SIZE, top: row * FLYWAY_SIZE,
              width: FLYWAY_SIZE, height: FLYWAY_SIZE
            }}
            data-position={`${col+1},${row+1}`}
          />
        );
      }
    }
    return cells;
  };

  const renderStations = () => {
    const stationElements = [];

    configuredStations.forEach(station => {
      const stationNumericId = getStationId(station.position, station.index);
      const currentLiveStateKey = stationLiveStates[stationNumericId];
      const stateInfo = currentLiveStateKey ? stationDisplayStates[currentLiveStateKey] : null; 

      let style = {};
      switch (station.position) {
        case "top": style = { left: FLYWAY_SIZE + station.index * FLYWAY_SIZE, top: 0 }; break;
        case "bottom": style = { left: FLYWAY_SIZE + station.index * FLYWAY_SIZE, top: FLYWAY_SIZE + GRID_ROWS * FLYWAY_SIZE }; break;
        case "left": style = { left: 0, top: FLYWAY_SIZE + station.index * FLYWAY_SIZE }; break;
        case "right": style = { left: FLYWAY_SIZE + GRID_COLS * FLYWAY_SIZE, top: FLYWAY_SIZE + station.index * FLYWAY_SIZE }; break;
        case "middle": style = { left: FLYWAY_SIZE + 2 * FLYWAY_SIZE, top: FLYWAY_SIZE + 1 * FLYWAY_SIZE }; break;
        default: break;
      }

      stationElements.push(
        <div
          key={`station-${station.position}-${station.index}`}
          className="station"
          style={{
            ...style,
            width: FLYWAY_SIZE, height: FLYWAY_SIZE,
            backgroundColor: station.color || "#b8b8b8", 
            borderColor: "#B0B0B0"
          }}
          title={`Station: ${station.id} (Abstract ID: ${station.abstractId})`}
        >
          <div className="station-name">{station.id}</div>
          <div className="station-position">{stationNumericId}</div>
          {stateInfo && (
            <div className="station-state" style={{ backgroundColor: stateInfo.color }}>
              {stateInfo.label}
            </div>
          )}
        </div>
      );
    });
    return stationElements;
  };

  const selectedXbotData = xbots.find(xbot => xbot.id === selectedXbot) || (xbots.length > 0 ? xbots[0] : null);

  return (
    <div className="xbot-tracker-page">
      <h1>Production Live View & Control</h1>
      {!mqttConnected && <p style={{color: 'red', textAlign: 'center', fontWeight: 'bold'}}>MQTT Disconnected - Xbot positions may not be live.</p>}
      <div className="tracker-content">
        <div 
          className="xbot-grid-container"
          style={{ width: containerWidth, height: containerHeight }}
        >
          <div className="grid-actual" style={{
            position: "absolute", left: FLYWAY_SIZE, top: FLYWAY_SIZE,
            width: totalWidth, height: totalHeight
          }}>
            {renderGridCells()}
          </div>
          {renderStations()}
          {xbots.map(xbot => {
            const xbotStateDetails = xbotStates[xbot.currentState];
            return (
              <div 
                key={xbot.id}
                className={`xbot-container ${xbot.id === selectedXbot ? 'selected' : ''}`}
                style={{
                  width: XBOT_SIZE,
                  height: XBOT_SIZE,
                  left: FLYWAY_SIZE + xbot.x - XBOT_SIZE / 2,
                  top: FLYWAY_SIZE + (totalHeight - xbot.y) - XBOT_SIZE / 2,
                  position: 'absolute',
                  cursor: 'pointer',
                }}
                onClick={() => setSelectedXbot(xbot.id)}
                title={`Xbot ${xbot.id}: X=${xbot.x?.toFixed(1)}, Y=${xbot.y?.toFixed(1)}, Yaw=${xbot.yaw?.toFixed(1)}°`}
              >
                <div
                  className="xbot-body" 
                  style={{
                    width: '100%',
                    height: '100%',
                    backgroundColor: '#aaaaaa',
                    border: '4px solid black',
                    borderRadius: '10px',
                    transform: `rotate(${xbot.yaw}deg)`,
                    boxSizing: 'border-box',
                    position: 'relative', 
                    boxShadow: '5px 5px 15px rgba(0, 0, 0, 0.3)', 
                  }}
                >
                  <div style={{
                    position: 'absolute',
                    top: '5px', 
                    left: '5px', 
                    fontSize: '14px', 
                    color: 'black',
                    backgroundColor: 'rgba(255, 255, 255, 0.7)', 
                    padding: '2px 4px',
                    borderRadius: '3px',
                    zIndex: 1, 
                    whiteSpace: 'nowrap',
                  }}>
                    Xbot {xbot.id}
                  </div>
                  {xbotStateDetails && (
                    <div style={{
                      position: 'absolute',
                      bottom: '5px', 
                      left: '5px',   
                      padding: '2px 4px', 
                      backgroundColor: xbotStateDetails.color,
                      color: 'white', 
                      fontSize: '12px', 
                      fontWeight: 'bold',
                      borderRadius: '3px',
                      textAlign: 'center',
                      zIndex: 1, 
                      lineHeight: '1.2',
                      minWidth: '40px', 
                    }}>
                      {xbotStateDetails.label}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        
        <div className="xbot-controls">
          <h2>Xbot Controls</h2>
          <div className="xbot-selector">
            <label>Select Xbot:</label>
            <div className="selector-buttons">
              {xbots.map(xbot => (
                <button 
                  key={xbot.id}
                  className={`select-button ${xbot.id === selectedXbot ? 'active' : ''}`}
                  style={{backgroundColor: xbot.id === selectedXbot ? xbot.color : '#f0f0f0', color: xbot.id === selectedXbot ? 'white' : 'black'}}
                  onClick={() => setSelectedXbot(xbot.id)}
                >
                  Xbot {xbot.id}
                </button>
              ))}
            </div>
            
            <div className="xbot-management-buttons">
              <button className="add-xbot-button" onClick={handleAddXbot}>+ Add Xbot</button>
              <button className="remove-xbot-button" onClick={handleRemoveXbot} disabled={xbots.length <= 1}>- Remove Xbot</button>
            </div>
          </div>
          
          {selectedXbotData && (
            <div className="xbot-current-pose">
              <h3>Selected: Xbot {selectedXbotData.id}</h3>
              <p>X Position: {selectedXbotData.x?.toFixed(2)} mm</p>
              <p>Y Position: {selectedXbotData.y?.toFixed(2)} mm</p>
              <p>Rotation: {selectedXbotData.yaw?.toFixed(2)}°</p>
              {xbotStates[selectedXbotData.currentState] && (
                <p>State: {xbotStates[selectedXbotData.currentState].label}</p>
              )}
            </div>
          )}
          
          <div className="xbot-list">
            <h3>All Xbot Positions</h3>
            {xbots.map(xbot => (
              <div 
                key={xbot.id} 
                className={`xbot-info ${xbot.id === selectedXbot ? 'selected' : ''}`} 
                style={{borderLeftColor: xbot.color}}
                onClick={() => setSelectedXbot(xbot.id)}
              >
                <h3>Xbot {xbot.id}</h3>
                <p>Position: X={xbot.x?.toFixed(1)}mm, Y={xbot.y?.toFixed(1)}mm</p>
                <p>Flyway: Col={Math.ceil(xbot.x/FLYWAY_SIZE)}, Row={Math.ceil(xbot.y/FLYWAY_SIZE)}</p>
                <p>Rotation: {xbot.yaw?.toFixed(1)}°</p>
                {xbotStates[xbot.currentState] && (
                  <p>State: {xbotStates[xbot.currentState].label}</p>
                )}
              </div>
            ))}
          </div>
          
          <div className="reset-controls">
          <button 
              className="reset-button"
              onClick={() => {
                localStorage.removeItem('xbotPositions');
                localStorage.removeItem('selectedXbot');
                const defaultXbotsRaw = [
                    { id: 1, x: 360, y: totalHeight - 600, yaw: 270, color: "#0033A0" },
                    { id: 2, x: 600, y: totalHeight - 600, yaw: 270, color: "#00A0AF" }
                ];
                const defaultXbotsWithDetails = defaultXbotsRaw.map(bot => ({
                    ...bot,
                    targetX: bot.x, targetY: bot.y, targetYaw: bot.yaw,
                    currentState: getXbotDefaultState(bot.id)
                }));
                setXbots(defaultXbotsWithDetails);
                setSelectedXbot(defaultXbotsWithDetails.length > 0 ? defaultXbotsWithDetails[0].id : null);
                setStationLiveStates({}); 
              }}
            >
              Reset to Default
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default XbotTracker;