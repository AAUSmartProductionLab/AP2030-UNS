import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import '../styles/Homepage.css';
import mqttService from '../services/MqttService';

export default function Homepage() {
  const [mqttConnected, setMqttConnected] = useState(false);
  const [activeBatches, setActiveBatches] = useState(0);
  const [uptime, setUptime] = useState('0h 0m 0s');
  const [serverIp, setServerIp] = useState('192.168.0.104'); 
  
  useEffect(() => {
    const updateServerIpFromStorage = () => {
      const savedSettings = localStorage.getItem('appSettings');
      if (savedSettings) {
        try {
          const settings = JSON.parse(savedSettings);
          if (settings.mqttBrokerHost) {
            setServerIp(settings.mqttBrokerHost);
          } else {
            console.warn("Homepage: mqttBrokerHost not found in parsed appSettings.");
          }
        } catch (error) {
          console.error("Homepage: Failed to parse appSettings from localStorage.", error);
        }
      } else {
        console.warn("Homepage: appSettings not found in localStorage.");
      }
    };
    
    updateServerIpFromStorage(); // Initial call to set IP
    
    // Listener for custom event (more reliable for same-tab updates)
    const handleAppSettingsChanged = () => {
      console.log('Homepage: "appSettingsChanged" custom event received. Updating server IP.');
      updateServerIpFromStorage();
    };
    
    // Listener for 'storage' event (good for cross-tab sync)
    const handleStorageEvent = (e) => {
      if (e.key === 'appSettings') {
        console.log('Homepage: "storage" event for appSettings received. Updating server IP.');
        updateServerIpFromStorage();
      }
    };
    
    window.addEventListener('appSettingsChanged', handleAppSettingsChanged);
    window.addEventListener('storage', handleStorageEvent);
    
    return () => {
      window.removeEventListener('appSettingsChanged', handleAppSettingsChanged);
      window.removeEventListener('storage', handleStorageEvent);
    };
  }, []);

  // Track MQTT connection status
  useEffect(() => {
    const unsubscribe = mqttService.onConnectionChange((isConnected) => {
      setMqttConnected(isConnected);
    });
    
    return () => {
      unsubscribe();
    };
  }, []);
  
  // Update active batches from localStorage
  useEffect(() => {
    const updateActiveBatches = () => {
      const savedQueue = localStorage.getItem('batchQueue');
      if (savedQueue) {
        const queue = JSON.parse(savedQueue);
        // Count batches with 'Running' status or all batches in queue
        const runningBatches = queue.filter(batch => batch.status === 'Running').length;
        const totalBatches = queue.length;
        setActiveBatches(runningBatches || totalBatches);
      } else {
        setActiveBatches(0);
      }
    };

    // Initial update
    updateActiveBatches();
    
    // Setup event listener for storage changes
    const handleStorageChange = (e) => {
      if (e.key === 'batchQueue') {
        updateActiveBatches();
      }
    };
    
    window.addEventListener('storage', handleStorageChange);
    
    // Poll for changes every few seconds (as a backup)
    const intervalId = setInterval(updateActiveBatches, 5000);
    
    return () => {
      window.removeEventListener('storage', handleStorageChange);
      clearInterval(intervalId);
    };
  }, []);
  
  // Calculate system uptime (unchanged)
  useEffect(() => {
    const startTime = new Date();
    
    const updateUptime = () => {
      const now = new Date();
      const diffMs = now - startTime;
      
      // Calculate days, hours, minutes, seconds
      const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
      const hours = Math.floor((diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
      const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((diffMs % (1000 * 60)) / 1000);
      
      // Format the uptime string
      let uptimeStr = '';
      if (days > 0) uptimeStr += `${days}d `;
      uptimeStr += `${hours}h ${minutes}m ${seconds}s`;
      
      setUptime(uptimeStr);
    };
    
    // Update every second
    const timerId = setInterval(updateUptime, 1000);
    
    return () => {
      clearInterval(timerId);
    };
  }, []);

  return (
    <div className="homepage">
      <h1>AMX-OUT Configurator Homepage</h1>
      
      {/* INTERNAL MODULES SECTION */}
      <h2 className="section-title">Configuration Modules</h2>
      <div className="service-cards internal-cards">
        {/* Production Orders */}
        <Link to="/batches" className="service-card with-bg-image">
          <img src="/productionorders.png" alt="" className="card-image-bg" />
          <div className="card-content">
            <div className="card-icon"></div>
            <h2>Production Orders</h2>
            <p>Configure and manage production batches</p>
          </div>
        </Link>
        
        {/* Planar Motor */}
        <Link to="/planar-motor" className="service-card with-bg-image">
          <img src="/planarconfig.png" alt="" className="card-image-bg" />
          <div className="card-content">
            <div className="card-icon"></div>
            <h2>Planar Motor Configurator</h2>
            <p>Configure planar motor layouts and settings</p>
          </div>
        </Link>
        
        {/* Settings */}
        <Link to="/settings" className="service-card with-bg-image">
          <img src="/settings.png" alt="" className="card-image-bg" />
          <div className="card-content">
            <div className="card-icon"></div>
            <h2>Settings</h2>
            <p>Configure application preferences</p>
          </div>
        </Link>
        {/* Router */}
        <a href="http://192.168.0.1" target="_blank" rel="noopener noreferrer" className="service-card with-bg-image external">
            <img src="/router.png" alt="" className="card-image-bg" />
            <div className="card-content">
              <div className="card-icon"></div>
              <h2>Network Router</h2>
              <p>Configure network settings and device management</p>
            </div>
            <div className="external-indicator">External Link</div>
          </a>
      </div>

      {/* EXTERNAL TOOLS SECTION */}
      <h2 className="section-title">External Tools</h2>
      <div className="service-cards external-cards">
        {/* HiveMQ */}
        <a href={`http://${serverIp}:8080/v2/`} target="_blank" rel="noopener noreferrer" className="service-card with-bg-image external">
          <img src="/hivemq.png" alt="" className="card-image-bg" />
          <div className="card-content">
            <div className="card-icon"></div>
            <h2>HiveMQ Dashboard</h2>
            <p>Monitor and manage MQTT connections</p>
          </div>
          <div className="external-indicator">External Link</div>
        </a>
        
        {/* Grafana */}
        <a href={`http://${serverIp}:3000`} target="_blank" rel="noopener noreferrer" className="service-card with-bg-image external">
          <img src="/grafana.png" alt="" className="card-image-bg" />
          <div className="card-content">
            <div className="card-icon"></div>
            <h2>Grafana</h2>
            <p>View system metrics and performance data</p>
          </div>
          <div className="external-indicator">External Link</div>
        </a>
        
        {/* MQTT Explorer */}
        <a href={`http://${serverIp}:4000`} target="_blank" rel="noopener noreferrer" className="service-card with-bg-image external">
          <img src="/mqttexp.png" alt="" className="card-image-bg" />
          <div className="card-content">
            <div className="card-icon"></div>
            <h2>MQTT Explorer</h2>
            <p>Browse and interact with MQTT topics and messages</p>
          </div>
          <div className="external-indicator">External Link</div>
        </a>

        {/* Groot */}
        <a href={`http://${serverIp}:6080/vnc.html?autoconnect=true&reconnect=true&reconnect_delay=1000&resize=remote&quality=9&compression=0&view_only=0`} target="_blank" rel="noopener noreferrer" className="service-card with-bg-image external">
          <img src="/groot.png" alt="" className="card-image-bg" />
          <div className="card-content">
            <div className="card-icon"></div>
            <h2>Groot</h2>
            <p>View and manage system components</p>
          </div>
          <div className="external-indicator">External Link</div>
        </a>
        
        {/* Portainer */}
        <a href={`http://${serverIp}:9000`} target="_blank" rel="noopener noreferrer" className="service-card with-bg-image external">
          <img src="/portainer.png" alt="" className="card-image-bg" />
          <div className="card-content">
            <div className="card-icon"></div>
            <h2>Portainer</h2>
            <p>Manage and monitor Docker containers</p>
          </div>
          <div className="external-indicator">External Link</div>
        </a>
      </div>
      
      <div className="system-status">
        <h3>System Status</h3>
        <div className="status-indicators">
          <div className="status-item">
            <span className="status-label">MQTT Connection:</span>
            <span className={`status-value ${mqttConnected ? 'connected' : 'disconnected'}`}>
              {mqttConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
          <div className="status-item">
            <span className="status-label">Batches in queue:</span>
            <span className="status-value">{activeBatches}</span>
          </div>
          <div className="status-item">
            <span className="status-label">System Uptime:</span>
            <span className="status-value">{uptime}</span>
          </div>
        </div>
      </div>
    </div>
  );
}