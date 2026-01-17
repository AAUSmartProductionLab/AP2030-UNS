import React, { useState, useEffect } from 'react';
import '../styles/Settings.css';
import mqttService from '../services/MqttService';

export default function Settings() {
  // Default values - use window.location.hostname to auto-detect server
  const defaultSettings = {
    mqttBrokerHost: window.location.hostname || "localhost",
    mqttBrokerPort: "8000",
    clientId: "configurator-" + Math.random().toString(16).substring(2, 8),
    autoSaveInterval: 5,
    theme: "Light"
  };

  // Load settings from localStorage or use defaults
  const [settings, setSettings] = useState(() => {
    const savedSettings = localStorage.getItem('appSettings');
    // Start with a copy of default settings
    let effectiveSettings = { ...defaultSettings };

    if (savedSettings) {
      const parsedFromStorage = JSON.parse(savedSettings);
      // Merge stored settings onto defaults. Stored settings take precedence.
      effectiveSettings = { ...effectiveSettings, ...parsedFromStorage };

      // Clean up any legacy mqttBrokerUrl if host and port are now the source of truth
      if (effectiveSettings.mqttBrokerHost && effectiveSettings.mqttBrokerPort) {
        delete effectiveSettings.mqttBrokerUrl;
      }
    }
    
    // Ensure clientId always has a value, even if loaded settings were incomplete
    if (!effectiveSettings.clientId) {
        effectiveSettings.clientId = "configurator-" + Math.random().toString(16).substring(2, 8);
    }
    return effectiveSettings;
  });
  
  // Track section collapse states
  const [sectionsCollapsed, setSectionsCollapsed] = useState({
    connection: false,
    preferences: true
  });

  // Toggle section collapse
  const toggleSection = (section) => {
    setSectionsCollapsed({
      ...sectionsCollapsed,
      [section]: !sectionsCollapsed[section]
    });
  };

  // Handle input changes
  const handleChange = (e) => {
    const { name, value } = e.target;
    setSettings(prevSettings => ({ // Use functional update for safety
      ...prevSettings,
      [name]: value
    }));
  };

  // Handle form submission
  const handleSubmit = (e) => {
    e.preventDefault();
    
    const settingsToSave = {
      mqttBrokerHost: settings.mqttBrokerHost,
      mqttBrokerPort: settings.mqttBrokerPort,
      clientId: settings.clientId,
      autoSaveInterval: settings.autoSaveInterval,
      theme: settings.theme
    };
  
    localStorage.setItem('appSettings', JSON.stringify(settingsToSave));
    
    mqttService.disconnect(); 
    setTimeout(() => {
      mqttService.connect(); 
      // Dispatch a custom event to notify other parts of the app
      window.dispatchEvent(new CustomEvent('appSettingsChanged'));
      console.log('Dispatched appSettingsChanged event');
    }, 500); 
    
    console.log('Settings saved to localStorage:', settingsToSave);
    setSettings(settingsToSave); 
    alert('Settings saved successfully! MQTT connection will be reestablished.');
  };

  return (
    <div className="settings-page">
      <h1>Settings</h1>
      <form onSubmit={handleSubmit}>
        {/* Connection Section */}
        <div className="settings-section">
          <div className="section-header" onClick={() => toggleSection('connection')}>
            <h2>Connection</h2>
            <span className={`collapse-indicator ${sectionsCollapsed.connection ? 'collapsed' : ''}`}>▼</span>
          </div>
          
          {!sectionsCollapsed.connection && (
            <div className="section-content">
              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="mqttBrokerHost">Host</label>
                  <input 
                    type="text" 
                    id="mqttBrokerHost"
                    name="mqttBrokerHost"
                    value={settings.mqttBrokerHost} 
                    onChange={handleChange}
                    placeholder="e.g., 192.168.0.104"
                  />
                </div>
                
                <div className="form-group">
                  <label htmlFor="mqttBrokerPort">Port</label>
                  <input 
                    type="text" 
                    id="mqttBrokerPort"
                    name="mqttBrokerPort"
                    value={settings.mqttBrokerPort} 
                    onChange={handleChange}
                    placeholder="e.g., 8000"
                  />
                </div>
                
                <div className="form-group wide">
                  <label htmlFor="clientId">Client ID</label>
                  <input 
                    type="text" 
                    id="clientId"
                    name="clientId"
                    value={settings.clientId} 
                    onChange={handleChange}
                    placeholder="e.g., configurator-client"
                  />
                </div>
              </div>
            </div>
          )}
        </div>
        
        {/* User Preferences Section */}
        <div className="settings-section">
          <div className="section-header" onClick={() => toggleSection('preferences')}>
            <h2>User Preferences</h2>
            <span className={`collapse-indicator ${sectionsCollapsed.preferences ? 'collapsed' : ''}`}>▼</span>
          </div>
          
          {!sectionsCollapsed.preferences && (
            <div className="section-content">
              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="autoSaveInterval">Auto-save Interval</label>
                  <input 
                    type="number" 
                    id="autoSaveInterval"
                    name="autoSaveInterval"
                    value={settings.autoSaveInterval} 
                    onChange={handleChange}
                    min="1" 
                    max="60" 
                    placeholder="Minutes"
                  />
                </div>
                
                <div className="form-group">
                  <label htmlFor="theme">Theme</label>
                  <select 
                    id="theme"
                    name="theme"
                    value={settings.theme} 
                    onChange={handleChange}
                  >
                    <option value="Light">Light</option>
                    <option value="Dark">Dark</option>
                    <option value="System Default">System Default</option>
                  </select>
                </div>
              </div>
            </div>
          )}
        </div>
        
        <div className="form-actions">
          <button type="submit" className="save-button">Connect</button>
        </div>
      </form>
    </div>
  );
}