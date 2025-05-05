import React from 'react';
import { Link } from 'react-router-dom';
import '../styles/Homepage.css';

export default function Homepage() {
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
        <a href="http://192.168.0.104:8080/v2/" target="_blank" rel="noopener noreferrer" className="service-card with-bg-image external">
          <img src="/hivemq.png" alt="" className="card-image-bg" />
          <div className="card-content">
            <div className="card-icon"></div>
            <h2>HiveMQ Dashboard</h2>
            <p>Monitor and manage MQTT connections</p>
          </div>
          <div className="external-indicator">External Link</div>
        </a>
        
        {/* Grafana */}
        <a href="http://192.168.0.104:3000" target="_blank" rel="noopener noreferrer" className="service-card with-bg-image external">
          <img src="/grafana.png" alt="" className="card-image-bg" />
          <div className="card-content">
            <div className="card-icon"></div>
            <h2>Grafana</h2>
            <p>View system metrics and performance data</p>
          </div>
          <div className="external-indicator">External Link</div>
        </a>
        {/* MQTT Explorer */}
        <a href="http://192.168.0.104:4000" target="_blank" rel="noopener noreferrer" className="service-card with-bg-image external">
          <img src="/mqttexp.png" alt="" className="card-image-bg" />
          <div className="card-content">
            <div className="card-icon"></div>
            <h2>MQTT Explorer</h2>
            <p>Browse and interact with MQTT topics and messages</p>
          </div>
          <div className="external-indicator">External Link</div>
        </a>

        {/* Groot */}
        <a href="http://192.168.0.104:6080" target="_blank" rel="noopener noreferrer" className="service-card with-bg-image external">
          <img src="/groot.png" alt="" className="card-image-bg" />
          <div className="card-content">
            <div className="card-icon"></div>
            <h2>Groot</h2>
            <p>View and manage system components</p>
          </div>
          <div className="external-indicator">External Link</div>
        </a>
        {/* Portainer */}
        <a href="http://192.168.0.104:9000" target="_blank" rel="noopener noreferrer" className="service-card with-bg-image external">
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
            <span className="status-value connected">Connected</span>
          </div>
          <div className="status-item">
            <span className="status-label">Active Batches:</span>
            <span className="status-value">2</span>
          </div>
          <div className="status-item">
            <span className="status-label">System Uptime:</span>
            <span className="status-value">3d 14h 22m</span>
          </div>
        </div>
      </div>
    </div>
  );
}