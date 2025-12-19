import { useState, useEffect } from 'react';
import './ConfigPanel.css';

export const ConfigPanel = ({ 
  onChange, 
  onClearStations, 
  onClearLimits, 
  onClearAll, 
  onSetDefaultStations,
  onPublishConfig,
  publishDisabled,
  config 
}) => {
  const [localConfig, setLocalConfig] = useState({
    maxSpeedX: "5.0",
    maxSpeedY: "5.0",
    maxSpeedRz: "10.0",
    maxAccelX: "2.0",
    maxAccelY: "2.0",
    maxAccelRz: "5.0",
    ...config // Use passed config as initial values if available
  });

  // Update local state when parent config changes
  useEffect(() => {
    if (config) {
      setLocalConfig(prev => ({...prev, ...config}));
    }
  }, [config]);

  // Only allow numbers with optional decimal places
  const handleInputChange = (e) => {
    const { name, value } = e.target;
    
    // Validate: empty or number with optional decimal places
    if (value === "" || /^-?\d*\.?\d*$/.test(value)) {
      const newConfig = { ...localConfig, [name]: value };
      setLocalConfig(newConfig);
      
      // Call parent onChange if provided
      if (onChange) {
        onChange(newConfig);
      }
    }
  };

  return (
    <div className="config-panel">
      <div className="config-header">
        <h2>Configuration</h2>
      </div>
      
      {/* Section 1: Limits */}
      <div className="config-section">
        <h3>Limits</h3>
        
        {/* Max Speed subsection */}
        <div className="subsection">
          <h4>Max Speed</h4>
          <div className="input-group">
            <label htmlFor="maxSpeedX">X-axis (m/s):</label>
            <input
              type="text"
              id="maxSpeedX"
              name="maxSpeedX"
              value={config.maxSpeedX}
              onChange={handleInputChange}
            />
          </div>
          
          <div className="input-group">
            <label htmlFor="maxSpeedY">Y-axis (m/s):</label>
            <input
              type="text"
              id="maxSpeedY"
              name="maxSpeedY"
              value={config.maxSpeedY}
              onChange={handleInputChange}
            />
          </div>
          
          <div className="input-group">
            <label htmlFor="maxSpeedRz">Rz (rad/s):</label>
            <input
              type="text"
              id="maxSpeedRz"
              name="maxSpeedRz"
              value={config.maxSpeedRz}
              onChange={handleInputChange}
            />
          </div>
        </div>
        
        {/* Max Acceleration subsection */}
        <div className="subsection">
          <h4>Max Acceleration</h4>
          <div className="input-group">
            <label htmlFor="maxAccelX">X-axis (m/s²):</label>
            <input
              type="text"
              id="maxAccelX"
              name="maxAccelX"
              value={config.maxAccelX}
              onChange={handleInputChange}
            />
          </div>
          
          <div className="input-group">
            <label htmlFor="maxAccelY">Y-axis (m/s²):</label>
            <input
              type="text"
              id="maxAccelY"
              name="maxAccelY"
              value={config.maxAccelY}
              onChange={handleInputChange}
            />
          </div>
          
          <div className="input-group">
            <label htmlFor="maxAccelRz">Rz (rad/s²):</label>
            <input
              type="text"
              id="maxAccelRz"
              name="maxAccelRz"
              value={config.maxAccelRz}
              onChange={handleInputChange}
            />
          </div>
        </div>
      </div>
      
      {/* Section 2: Reset */}
      <div className="config-section">
        <h3>Reset</h3>
        <div className="buttons-section">
          <button 
            className="config-button clear-stations-button" 
            onClick={onClearStations}
          >
            Clear Stations
          </button>
          
          <button 
            className="config-button clear-limits-button" 
            onClick={onClearLimits}
          >
            Clear Limits
          </button>
          
          <button 
            className="config-button clear-button" 
            onClick={onClearAll}
          >
            Clear All
          </button>
          {onSetDefaultStations && (
            <button 
              className="config-button default-layout-button" 
              onClick={onSetDefaultStations}
            >
              Set Default Layout
            </button>)}
          {onPublishConfig && (
            <button 
              className="config-button publish-config-button" 
              onClick={onPublishConfig}
              disabled={publishDisabled}
            >
              Publish Configuration
            </button>)}
        </div>
      </div>
    </div>
  );
};