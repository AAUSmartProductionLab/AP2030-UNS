import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { usePlanarMotorContext } from '../contexts/PlanarMotorContext';
import { unstable_batchedUpdates } from 'react-dom';
import mqttService from '../services/MqttService';
import systemControlService, { SystemControlService } from '../services/SystemControlService';
import "../styles/XbotTracker.css";

// Memoized Xbot Component for better performance
const XbotComponent = React.memo(({ xbot, isSelected, onSelect, xbotStates, FLYWAY_SIZE, XBOT_SIZE, totalHeight }) => {
  const xbotStateDetails = xbotStates[xbot.currentState];
  
  return (
    <div 
      className={`xbot-container ${isSelected ? 'selected' : ''}`}
      style={{
        width: XBOT_SIZE,
        height: XBOT_SIZE,
        left: FLYWAY_SIZE + xbot.x - XBOT_SIZE / 2,
        top: FLYWAY_SIZE + (totalHeight - xbot.y) - XBOT_SIZE / 2,
        position: 'absolute',
        cursor: 'pointer',
      }}
      onClick={() => onSelect(xbot.id)}
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
}, (prevProps, nextProps) => {
  // Custom comparison for better performance
  const prev = prevProps.xbot;
  const next = nextProps.xbot;
  
  return (
    prev.id === next.id &&
    prev.x === next.x &&
    prev.y === next.y &&
    prev.yaw === next.yaw &&
    prev.currentState === next.currentState &&
    prevProps.isSelected === nextProps.isSelected
  );
});

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

  // Batching state for MQTT updates
  const [pendingUpdates, setPendingUpdates] = useState({});
  const updateTimeoutRef = useRef(null);
  const lastUpdateTime = useRef({});

  // Optimized batching function
  const batchXbotUpdate = useCallback((xbotId, updates) => {
    setPendingUpdates(prev => ({
      ...prev,
      [xbotId]: { ...prev[xbotId], ...updates }
    }));

    // Clear existing timeout
    if (updateTimeoutRef.current) {
      clearTimeout(updateTimeoutRef.current);
    }

    // Batch updates every 16ms (60 FPS)
    updateTimeoutRef.current = setTimeout(() => {
      unstable_batchedUpdates(() => {
        setPendingUpdates(currentPending => {
          if (Object.keys(currentPending).length === 0) return {};
          
          setXbots(prevXbots => {
            const newXbots = prevXbots.map(xbot => {
              const updates = currentPending[xbot.id];
              return updates ? { ...xbot, ...updates } : xbot;
            });
            return newXbots;
          });
          
          return {}; // Clear pending updates
        });
      });
    }, 16);
  }, []);

  // Define Xbot states (used for UI mapping)
  const xbotStates = useMemo(() => ({
    "idle": { color: "#FFD700", label: "Idle" },
    "stopped": { color: "#FF4D4D", label: "Stopped" },
    "executing": { color: "#3478F6", label: "Executing" },
    "execute": { color: "#3478F6", label: "Execute" },
    "complete": { color: "#4CD964", label: "Complete" },
    "resetting": { color: "#FF9500", label: "Resetting" },
    "error": { color: "#FF3B30", label: "Error" },
    "waiting": { color: "#8E8E93", label: "Waiting" },
    "starting": { color: "#5AC8FA", label: "Starting" },
    "stopping": { color: "#FFBF00", label: "Stopping" }
  }), []);
  
  // Define Station states (also used for system states like BT Controller and Planar)
  const stationDisplayStates = useMemo(() => ({
    "idle": { color: "#FFD700", label: "Idle" },
    "stopped": { color: "#FF4D4D", label: "Stopped" },
    "executing": { color: "#3478F6", label: "Executing" },
    "execute": { color: "#3478F6", label: "Execute" },
    "complete": { color: "#4CD964", label: "Complete" },
    "completing": { color: "#32CD32", label: "Completing" },
    "resetting": { color: "#FF9500", label: "Resetting" },
    "error": { color: "#FF3B30", label: "Error" },
    "waiting": { color: "#8E8E93", label: "Waiting" },
    "starting": { color: "#5AC8FA", label: "Starting" },
    "stopping": { color: "#FFBF00", label: "Stopping" },
    // Additional PackML states
    "holding": { color: "#9B59B6", label: "Holding" },
    "held": { color: "#8E44AD", label: "Held" },
    "unholding": { color: "#A569BD", label: "Unholding" },
    "suspending": { color: "#E67E22", label: "Suspending" },
    "suspended": { color: "#D35400", label: "Suspended" },
    "unsuspending": { color: "#F39C12", label: "Unsuspending" },
    "aborting": { color: "#C0392B", label: "Aborting" },
    "aborted": { color: "#922B21", label: "Aborted" },
    "clearing": { color: "#1ABC9C", label: "Clearing" }
  }), []);

  // Default state for Xbots before MQTT update
  const getXbotDefaultState = useCallback((xbotId) => {
    const states = Object.keys(xbotStates);
    return states[0]; 
  }, [xbotStates]);

  const getStationId = useCallback((position, index) => {
    const idMap = {
      "top-0": 0, "top-1": 1, "top-2": 2, "top-3": 3,
      "right-0": 5, "right-1": 8, "right-2": 10,
      "bottom-3": 14, "bottom-2": 13, "bottom-1": 12, "bottom-0": 11,
      "left-2": 9, "left-1": 6, "left-0": 4,
      "middle-0": 7,
    };
    return idMap[`${position}-${index}`];
  }, []);
  
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
  const [systemState, setSystemState] = useState(systemControlService.getState());
  const [btControllerState, setBtControllerState] = useState(null);
  const [planarSystemState, setPlanarSystemState] = useState(null);
  const [isBtSuspended, setIsBtSuspended] = useState(false);
  const [isPlanarHolding, setIsPlanarHolding] = useState(false);
  const [isSystemHeld, setIsSystemHeld] = useState(false);
  const [isSystemSuspended, setIsSystemSuspended] = useState(false);

  // Add new state for Planar button states
  const [planarButtonStates, setPlanarButtonStates] = useState({
    Clear: true,
    Reset: true,
    Start: true,
    Stop: true,
    Hold: true,
    UnHold: true
  });

  const [btButtonStates, setBtButtonStates] = useState({
    Reset: true,
    Start: true,
    Stop: true,
    Suspend: true,
    Unsuspend: true
  });

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

  // Subscribe to SystemControlService state changes
  useEffect(() => {
    const unsubscribe = systemControlService.onStateChange((state, results) => {
      setSystemState(state);
      // Sync toggle states based on actual system state
      if (state === 'Held' || state === 'Holding') {
        setIsSystemHeld(true);
      } else if (state === 'Execute' || state === 'Unholding') {
        setIsSystemHeld(false);
      }
      if (state === 'Suspended' || state === 'Suspending') {
        setIsSystemSuspended(true);
      } else if (state === 'Execute' || state === 'Unsuspending') {
        setIsSystemSuspended(false);
      }
    });
    return () => unsubscribe();
  }, []);

  // MQTT Subscription for BT Controller State
  useEffect(() => {
    if (!mqttConnected) return;
    const topic = "NN/Nybrovej/InnoLab/bt_controller/DATA/State";
    const unsubscribe = mqttService.onMessage(topic, (message) => {
      try {
        const data = typeof message === 'string' ? JSON.parse(message) : message;
        const stateKey = data.State?.toLowerCase();
        if (stateKey && stationDisplayStates[stateKey]) {
          //There is probably a cleaner way of doing this and ideally it should also be based on answers from the bt to the commands TODO improve
          if (stateKey == "stopped"){
            setBtButtonStates({
              Reset: true,
              Start: false,
              Stop: false,
              Suspend: false,
              UnSuspend: false
            });
          }
          else if(stateKey == "resetting")
          {
            setBtButtonStates({
              Reset: false,
              Start: false,
              Stop: true,
              Suspend: false,
              UnSuspend: false
            });
          }
          else if(stateKey == "idle")
          {
            setBtButtonStates({
              Reset: false,
              Start: true,
              Stop: true,
              Suspend: false,
              UnSuspend: false
            });
          }
          else if(stateKey == "starting")
          {
            setBtButtonStates({
              Reset: false,
              Start: false,
              Stop: true,
              Suspend: false,
              UnSuspend: false
            });

          }
          else if(stateKey == "executing")
          {
            setBtButtonStates({
              Reset: false,
              Start: false,
              Stop: true,
              Suspend: true,
              UnSuspend: false
            });
          }
          else if(stateKey == "completing")
          {
            setBtButtonStates({
              Reset: false,
              Start: false,
              Stop: true,
              Suspend: false,
              UnSuspend: false
            });
          }
          else if(stateKey == "complete")
          {
            setBtButtonStates({
              Reset: true,
              Start: false,
              Stop: true,
              Suspend: false,
              UnSuspend: false
            });
          }
          else if(stateKey == "suspending")
          {
            setBtButtonStates({
              Reset: false,
              Start: false,
              Stop: true,
              Suspend: false,
              UnSuspend: false
            });
          }
          else if(stateKey == "suspended")
          {
            setBtButtonStates({
              Reset: false,
              Start: false,
              Stop: true,
              Suspend: false,
              UnSuspend: true
            });
          }
          else if(stateKey == "unsuspending")
          {
            setBtButtonStates({
              Reset: false,
              Start: false,
              Stop: true,
              Suspend: false,
              UnSuspend: false
            });
          }
          else if(stateKey == "stopping")
          {
            setBtButtonStates({
              Reset: true,
              Start: false,
              Stop: false,
              Suspend: false,
              UnSuspend: false
            });
          }
        setBtControllerState(stateKey);
        } else {
          console.warn(`BTControllerState: Received unknown state "${data.State}" from topic ${topic}`);
          setBtControllerState(data.State || 'unknown'); 
        }
      } catch (error) {
        console.error(`Error processing BT Controller State message from topic ${topic}:`, error, "Raw message:", message);
        setBtControllerState('error');
      }
    });
    return () => unsubscribe();
  }, [mqttConnected, stationDisplayStates]);

  // MQTT Subscription for Planar System State
  useEffect(() => {
    if (!mqttConnected) return;
    const topic = "NN/Nybrovej/InnoLab/Planar/DATA/State";
    const unsubscribe = mqttService.onMessage(topic, (message) => {
      try {
        const data = typeof message === 'string' ? JSON.parse(message) : message;
        const stateKey = data.State?.toLowerCase();
        if (stateKey && stationDisplayStates[stateKey]) {
          setPlanarSystemState(stateKey);
        } else {
          console.warn(`PlanarSystemState: Received unknown state "${data.State}" from topic ${topic}`);
          setPlanarSystemState(data.State || 'unknown');
        }
      } catch (error) {
        console.error(`Error processing Planar System State message from topic ${topic}:`, error, "Raw message:", message);
        setPlanarSystemState('error');
      }
    });
    return () => unsubscribe();
  }, [mqttConnected, stationDisplayStates]);

  // MQTT Subscription for Planar Button States
  useEffect(() => {
    if (!mqttConnected) return;
    const topic = "NN/Nybrovej/InnoLab/Planar/DATA/ButtonStates";
    const unsubscribe = mqttService.onMessage(topic, (message) => {
      try {
        const data = typeof message === 'string' ? JSON.parse(message) : message;
        if (data.States) {
          setPlanarButtonStates(data.States);
          console.log('Planar Button States updated:', data.States);
        } else {
          console.warn(`PlanarButtonStates: Received message without States from topic ${topic}:`, data);
        }
      } catch (error) {
        console.error(`Error processing Planar Button States message from topic ${topic}:`, error, "Raw message:", message);
      }
    });
    return () => unsubscribe();
  }, [mqttConnected]);

  const xbotIdSignature = useMemo(() => {
    return xbots.map(x => x.id).sort((a, b) => a - b).join(',');
  }, [xbots]); 

  // Optimized MQTT Subscriptions for Xbot Poses and States
  useEffect(() => {
    if (!mqttConnected) return;

    const allUnsubscribes = [];

    xbotsRef.current.forEach(xbotSubConfig => {
      const xbotMqttId = `Xbot${xbotSubConfig.id}`;
      
      // Pose updates with throttling
      const poseTopic = `NN/Nybrovej/InnoLab/Planar/${xbotMqttId}/DATA/Pose`;
      const unsubscribePose = mqttService.onMessage(poseTopic, (message) => {
        try {
          const now = Date.now();
          const lastUpdate = lastUpdateTime.current[xbotSubConfig.id] || 0;
          
          // Throttle pose updates to max 30 FPS per Xbot
          if (now - lastUpdate < 33) return;
          lastUpdateTime.current[xbotSubConfig.id] = now;

          const poseData = typeof message === 'string' ? JSON.parse(message) : message;
          
          // Use batched update instead of immediate setState
          batchXbotUpdate(xbotSubConfig.id, {
            targetX: poseData.X !== undefined ? parseFloat(poseData.X) * 1000 : undefined,
            targetY: poseData.Y !== undefined ? parseFloat(poseData.Y) * 1000 : undefined,
            targetYaw: poseData.Rz !== undefined ? parseFloat(poseData.Rz) : undefined
          });
        } catch (error) {
          console.error(`XbotTracker: Error processing pose message for Xbot ID ${xbotSubConfig.id}:`, error);
        }
      });
      allUnsubscribes.push(unsubscribePose);

      // State updates (these can be immediate as they're less frequent)
      const stateTopic = `NN/Nybrovej/InnoLab/Planar/${xbotMqttId}/DATA/State`;
      const unsubscribeState = mqttService.onMessage(stateTopic, (message) => {
        try {
          const stateData = typeof message === 'string' ? JSON.parse(message) : message;
          const newStateKey = stateData.State?.toLowerCase();
          
          if (newStateKey && xbotStates[newStateKey]) {
            batchXbotUpdate(xbotSubConfig.id, { currentState: newStateKey });
          }
        } catch (error) {
          console.error(`XbotTracker: Error processing state message for Xbot ID ${xbotSubConfig.id}:`, error);
        }
      });
      allUnsubscribes.push(unsubscribeState);
    });

    return () => {
      allUnsubscribes.forEach(unsubscribe => unsubscribe());
      if (updateTimeoutRef.current) {
        clearTimeout(updateTimeoutRef.current);
      }
    };
  }, [xbotIdSignature, mqttConnected, batchXbotUpdate, xbotStates]);

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
  }, [placedNodes, GRID_COLS, GRID_ROWS]);

  // MQTT Subscriptions for Station States
  useEffect(() => {
    if (!mqttConnected || !configuredStations || configuredStations.length === 0) {
      return;
    }
    const stationUnsubscribes = [];
    configuredStations.forEach(station => {
      if (!station.abstractId) {
        console.warn(`StationTracker: Station ${station.id} (Pos: ${station.position}-${station.index}) is missing abstractId, cannot subscribe to state topic.`);
        return;
      }
      const stationTypeForTopic = station.abstractId.charAt(0).toUpperCase() + station.abstractId.slice(1).toLowerCase();
      const topic = `NN/Nybrovej/InnoLab/${stationTypeForTopic}/DATA/State`;
      const stationNumericId = getStationId(station.position, station.index);
      
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
      stationUnsubscribes.forEach(unsubscribe => unsubscribe());
    };
  }, [configuredStations, mqttConnected, getStationId, stationDisplayStates]);

  // Optimized Animation Loop Effect
  useEffect(() => {
    let isActive = true;
    let lastFrameTime = 0;
    const targetFPS = 60;
    const frameInterval = 1000 / targetFPS;

    const animate = (currentTime) => {
      if (!isActive) return;
      
      // Throttle to target FPS
      if (currentTime - lastFrameTime < frameInterval) {
        animationFrameId.current = requestAnimationFrame(animate);
        return;
      }
      lastFrameTime = currentTime;

      let needsAnotherFrame = false;
      const currentBotsSnapshot = xbotsRef.current;
      
      // Only update bots that actually need animation
      const botsNeedingAnimation = currentBotsSnapshot.filter(bot => 
        Math.abs(bot.targetX - bot.x) > SNAP_THRESHOLD || 
        Math.abs(bot.targetY - bot.y) > SNAP_THRESHOLD ||
        Math.abs(bot.targetYaw - bot.yaw) > SNAP_THRESHOLD
      );
      
      if (botsNeedingAnimation.length === 0) {
        animationFrameId.current = null;
        return;
      }

      // Batch all animation updates
      const newAnimatedBots = currentBotsSnapshot.map(bot => {
        if (!botsNeedingAnimation.includes(bot)) return bot;
        
        const newBot = { ...bot };
        let hasChanged = false;

        // X position
        if (Math.abs(bot.targetX - bot.x) > SNAP_THRESHOLD) {
          newBot.x = bot.x + (bot.targetX - bot.x) * LERP_FACTOR;
          hasChanged = true;
        } else if (bot.x !== bot.targetX) {
          newBot.x = bot.targetX;
          hasChanged = true;
        }

        // Y position
        if (Math.abs(bot.targetY - bot.y) > SNAP_THRESHOLD) {
          newBot.y = bot.y + (bot.targetY - bot.y) * LERP_FACTOR;
          hasChanged = true;
        } else if (bot.y !== bot.targetY) {
          newBot.y = bot.targetY;
          hasChanged = true;
        }

        // Yaw rotation
        let yawDiff = bot.targetYaw - bot.yaw;
        if (Math.abs(yawDiff) > 180) { 
          yawDiff = yawDiff > 0 ? yawDiff - 360 : yawDiff + 360; 
        }
        if (Math.abs(yawDiff) > SNAP_THRESHOLD) { 
          newBot.yaw = bot.yaw + yawDiff * LERP_FACTOR;
          hasChanged = true;
        } else if (bot.yaw !== bot.targetYaw) { 
          newBot.yaw = bot.targetYaw;
          hasChanged = true;
        }
        newBot.yaw = (newBot.yaw % 360 + 360) % 360;

        if (hasChanged) needsAnotherFrame = true;
        return newBot;
      });

      // Only update state if something actually changed
      if (needsAnotherFrame) {
        setXbots(newAnimatedBots);
        animationFrameId.current = requestAnimationFrame(animate);
      } else {
        animationFrameId.current = null;
      }
    };

    // Start animation only when needed
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
  }, [xbots, LERP_FACTOR, SNAP_THRESHOLD]);

  // Behavior Tree Control Handlers - using unified state commands
  const handleBtStartSystem = useCallback(() => {
    mqttService.publishStateCommand(SystemControlService.SUBSYSTEMS.BT_CONTROLLER, 'Start');
  }, []);
  const handleBtStopSystem = useCallback(() => {
    mqttService.publishStateCommand(SystemControlService.SUBSYSTEMS.BT_CONTROLLER, 'Stop');
  }, []);
  const handleBtResetSystem = useCallback(() => {
    mqttService.publishStateCommand(SystemControlService.SUBSYSTEMS.BT_CONTROLLER, 'Reset');
  }, []);
  const handleBtToggleSuspendSystem = useCallback(() => {
    if (isBtSuspended) {
      mqttService.publishStateCommand(SystemControlService.SUBSYSTEMS.BT_CONTROLLER, 'Unsuspend');
    } else {
      mqttService.publishStateCommand(SystemControlService.SUBSYSTEMS.BT_CONTROLLER, 'Suspend');
    }
    setIsBtSuspended(!isBtSuspended);
  }, [isBtSuspended]);

  // Planar Control Handlers - using unified state commands
  const handlePlanarStartSystem = useCallback(() => {
    mqttService.publishStateCommand(SystemControlService.SUBSYSTEMS.PLANAR, 'Start');
  }, []);

  const handlePlanarStopSystem = useCallback(() => {
    mqttService.publishStateCommand(SystemControlService.SUBSYSTEMS.PLANAR, 'Stop');
  }, []);

  const handlePlanarClearSystem = useCallback(() => {
    mqttService.publishStateCommand(SystemControlService.SUBSYSTEMS.PLANAR, 'Clear');
  }, []);

  const handlePlanarResetSystem = useCallback(() => {
    mqttService.publishStateCommand(SystemControlService.SUBSYSTEMS.PLANAR, 'Reset');
  }, []);

  const handlePlanarToggleHoldSystem = useCallback(() => {
    if (isPlanarHolding) {
      mqttService.publishStateCommand(SystemControlService.SUBSYSTEMS.PLANAR, 'Unhold');
    } else {
      mqttService.publishStateCommand(SystemControlService.SUBSYSTEMS.PLANAR, 'Hold');
    }
    setIsPlanarHolding(!isPlanarHolding);
  }, [isPlanarHolding]);

  const handleAddXbot = useCallback(() => {
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
  }, [xbots, FLYWAY_SIZE, totalWidth, totalHeight, XBOT_SIZE, getXbotDefaultState]);
  
  const handleRemoveXbot = useCallback(() => {
    if (xbots.length <= 1) return;
    const filteredXbots = xbots.filter(xbot => xbot.id !== selectedXbot);
    setXbots(filteredXbots);
    if (filteredXbots.length > 0) {
      setSelectedXbot(filteredXbots[0].id);
    } else {
      setSelectedXbot(null);
    }
  }, [xbots, selectedXbot]);
  
  const renderGridCells = useCallback(() => {
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
  }, [GRID_ROWS, GRID_COLS, FLYWAY_SIZE]);

  const renderStations = useCallback(() => {
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
  }, [configuredStations, stationLiveStates, stationDisplayStates, getStationId, FLYWAY_SIZE, GRID_ROWS, GRID_COLS]);

  const selectedXbotData = useMemo(() => 
    xbots.find(xbot => xbot.id === selectedXbot) || (xbots.length > 0 ? xbots[0] : null),
    [xbots, selectedXbot]
  );

  const renderSystemState = useCallback((stateKey, label) => {
    if (!stateKey && stateKey !== null) return <div className="system-state-item">{label}: Loading...</div>;
    if (stateKey === null) return <div className="system-state-item">{label}: Not Available</div>;
    
    const displayInfo = stationDisplayStates[stateKey.toLowerCase()] || { label: stateKey, color: '#888'};
    return (
      <div className="system-state-item">
        {label}: <span style={{ color: displayInfo.color, fontWeight: 'bold', border: `1px solid ${displayInfo.color}`, padding: '2px 5px', borderRadius: '4px', backgroundColor: `${displayInfo.color}20` }}>{displayInfo.label}</span>
      </div>
    );
  }, [stationDisplayStates]);

  const renderOverallSystemState = useCallback((stateKey, label) => {
    // PackML state colors matching stationDisplayStates
    const stateColors = {
      // Stable states
      'Stopped': '#FF4D4D',
      'Idle': '#FFD700',
      'Execute': '#3478F6',
      'Complete': '#4CD964',
      'Held': '#8E8E93',
      'Suspended': '#FFBF00',
      'Aborted': '#FF3B30',
      // Transitioning states
      'Starting': '#5AC8FA',
      'Stopping': '#FFBF00',
      'Resetting': '#FF9500',
      'Holding': '#8E8E93',
      'Unholding': '#5AC8FA',
      'Suspending': '#FFBF00',
      'Unsuspending': '#5AC8FA',
      'Completing': '#4CD964',
      'Aborting': '#FF3B30',
      'Clearing': '#3478F6',
    };
    
    const displayLabel = stateKey || 'Stopped';
    const displayColor = stateColors[stateKey] || '#888';
    
    return (
      <div className="system-state-item">
        {label}: <span style={{ color: displayColor, fontWeight: 'bold', border: `1px solid ${displayColor}`, padding: '2px 5px', borderRadius: '4px', backgroundColor: `${displayColor}20` }}>{displayLabel}</span>
      </div>
    );
  }, []);

  return (
    <div className="xbot-tracker-page">
      <div className="system-state-display-container">
        {renderOverallSystemState(systemState, "System")}
        {renderSystemState(btControllerState, "BT Controller")}
        {renderSystemState(planarSystemState, "Planar System")}
      </div>
      <h1>Production Live View & Control</h1>
      {!mqttConnected && <p style={{color: 'red', textAlign: 'center', fontWeight: 'bold'}}>MQTT Disconnected - Data may not be live.</p>}
      
      <div className="main-layout-container">
        <div className="control-sidebar">
          <div className="control-section">
            <h3>System Controls</h3>
            <button 
              className="control-button start-button" 
              onClick={() => systemControlService.startSystem()}
              disabled={!mqttConnected}
            >
              Start
            </button>
            <button 
              className="control-button stop-button" 
              onClick={() => systemControlService.stopSystem()}
              disabled={!mqttConnected}
            >
              Stop
            </button>
            <button 
              className="control-button reset-button-system" 
              onClick={() => systemControlService.resetSystem()}
              disabled={!mqttConnected}
            >
              Reset
            </button>
            <button 
              className={`control-button hold-button ${isSystemHeld ? 'unhold-active' : 'hold-active'}`}
              onClick={() => {
                if (isSystemHeld) {
                  systemControlService.unholdSystem();
                } else {
                  systemControlService.holdSystem();
                }
                setIsSystemHeld(!isSystemHeld);
              }}
              disabled={!mqttConnected}
            >
              {isSystemHeld ? 'Unhold' : 'Hold'}
            </button>
            <button 
              className={`control-button suspend-button ${isSystemSuspended ? 'unsuspend-active' : 'suspend-active'}`}
              onClick={() => {
                if (isSystemSuspended) {
                  systemControlService.unsuspendSystem();
                } else {
                  systemControlService.suspendSystem();
                }
                setIsSystemSuspended(!isSystemSuspended);
              }}
              disabled={!mqttConnected}
            >
              {isSystemSuspended ? 'Unsuspend' : 'Suspend'}
            </button>
            <button 
              className="control-button abort-button" 
              onClick={() => systemControlService.abortSystem()}
              disabled={!mqttConnected}
            >
              Abort
            </button>
          </div>
          
          <div className="control-section">
            <h3>Behavior Tree Controls</h3>
            <button 
              className="control-button start-button" 
              onClick={handleBtStartSystem}
              disabled={!btButtonStates.Start}
            >
                Start
            </button>
            <button 
              className="control-button stop-button" 
              onClick={handleBtStopSystem}
              disabled={!btButtonStates.Stop}
              >
              Stop
            </button>
            <button 
              className="control-button reset-button-system" 
              onClick={handleBtResetSystem}
              disabled={!btButtonStates.Reset}
            >
              Reset
            </button>
            <button 
              className={`control-button suspend-button ${isBtSuspended ? 'unsuspend-active' : 'suspend-active'}`} 
              onClick={handleBtToggleSuspendSystem}
              disabled={isBtSuspended ? !btButtonStates.Unsuspend : !btButtonStates.Suspend}
            >
              {isBtSuspended ? 'Unsuspend' : 'Suspend'}
            </button>
          </div>

          <div className="control-section">
            <h3>Planar Controls</h3>
            <button 
              className="control-button start-button" 
              onClick={handlePlanarStartSystem}
              disabled={!planarButtonStates.Start}
            >
              Start
            </button>
            <button 
              className="control-button stop-button" 
              onClick={handlePlanarStopSystem}
              disabled={!planarButtonStates.Stop}
            >
              Stop
            </button>
            <button 
              className="control-button reset-button-system" 
              onClick={handlePlanarResetSystem}
              disabled={!planarButtonStates.Reset}
            >
              Reset
            </button>
            <button 
              className="control-button reset-button-system" 
              onClick={handlePlanarClearSystem}
              disabled={!planarButtonStates.Clear}
            >
              Clear
            </button>
            <button 
              className={`control-button hold-button ${isPlanarHolding ? 'unhold-active' : 'hold-active'}`} 
              onClick={handlePlanarToggleHoldSystem}
              disabled={isPlanarHolding ? !planarButtonStates.UnHold : !planarButtonStates.Hold}
            >
              {isPlanarHolding ? 'Unsuspend' : 'Suspend'}
            </button>
          </div>
        </div>
        
        <div className="tracker-main-area">
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
              {xbots.map(xbot => (
                <XbotComponent
                  key={xbot.id}
                  xbot={xbot}
                  isSelected={xbot.id === selectedXbot}
                  onSelect={setSelectedXbot}
                  xbotStates={xbotStates}
                  FLYWAY_SIZE={FLYWAY_SIZE}
                  XBOT_SIZE={XBOT_SIZE}
                  totalHeight={totalHeight}
                />
              ))}
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
                        { id: 2, x: 600, y: totalHeight - 600, yaw: 270, color: "#00A0AF" },
                        { id: 3, x: 840, y: totalHeight - 600, yaw: 270, color: "#00A0AF" },
                    ];
                    const defaultXbotsWithDetails = defaultXbotsRaw.map(bot => ({
                        ...bot,
                        targetX: bot.x, targetY: bot.y, targetYaw: bot.yaw,
                        currentState: getXbotDefaultState(bot.id)
                    }));
                    setXbots(defaultXbotsWithDetails);
                    setSelectedXbot(defaultXbotsWithDetails.length > 0 ? defaultXbotsWithDetails[0].id : null);
                    setStationLiveStates({}); 
                    setBtControllerState(null);
                    setPlanarSystemState(null);
                    setIsBtSuspended(false);
                    setIsPlanarHolding(false);
                    setBtButtonStates({
                      Reset: true,
                      Start: true,
                      Stop: true,
                      Suspend: true,
                      Unsuspend: true
                    })
                    setPlanarButtonStates({
                      Clear: true,
                      Reset: true,
                      Start: true,
                      Stop: true,
                      Hold: true,
                      UnHold: true
                    });
                  }}
                >
                  Reset Xbots & View
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default XbotTracker;