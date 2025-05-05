import React, { useState } from 'react';
import '../styles/Settings.css';

export default function Settings() {
  // Use state to manage form values
  const [settings, setSettings] = useState({
    mqttBrokerUrl: "mqtt://broker.example.com:1883",
    autoSaveInterval: 5,
    theme: "Light"
  });

  // Handle input changes
  const handleChange = (e) => {
    const { name, value } = e.target;
    setSettings({
      ...settings,
      [name]: value
    });
  };

  // Handle form submission
  const handleSubmit = (e) => {
    e.preventDefault();
    console.log('Settings saved:', settings);
    // Here you would typically save to localStorage or send to a server
    alert('Settings saved successfully!');
  };

  return (
    <div className="settings-page">
      <h1>Settings</h1>
      <form className="settings-content" onSubmit={handleSubmit}>
        <div className="settings-section">
          <h3>System Configuration</h3>
          <div className="setting-item">
            <label htmlFor="mqttBrokerUrl">MQTT Broker URL</label>
            <input 
              type="text" 
              id="mqttBrokerUrl"
              name="mqttBrokerUrl"
              value={settings.mqttBrokerUrl} 
              onChange={handleChange}
            />
          </div>
          <div className="setting-item">
            <label htmlFor="autoSaveInterval">Auto-save Interval (minutes)</label>
            <input 
              type="number" 
              id="autoSaveInterval"
              name="autoSaveInterval"
              value={settings.autoSaveInterval} 
              onChange={handleChange}
              min="1" 
              max="60" 
            />
          </div>
        </div>
        <div className="settings-section">
          <h3>User Preferences</h3>
          <div className="setting-item">
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
        
        <div className="settings-actions">
          <button type="submit" className="save-button">Save Settings</button>
        </div>
      </form>
    </div>
  );
}