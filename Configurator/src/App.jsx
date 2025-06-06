import React, { useState, useEffect } from "react";
import { BrowserRouter as Router, Routes, Route, NavLink, useLocation } from "react-router-dom";
import { PersistentRouter } from "./components/PersistenRouter/PersistentRouter";
import { PlanarMotorProvider } from "./contexts/PlanarMotorContext";
import PlanarMotorConfigurator from "./pages/PlanarMotorConfigurator";
import BatchConfigurator from "./pages/BatchConfigurator";
import Homepage from "./pages/Homepage";
import Settings from "./pages/Settings";
import XbotTracker from "./pages/XbotTracker";
import SOPDashboard from "./pages/SOPDashboard"; // Add this import
import mqttService from "./services/MqttService";
import { ToastContainer, toast } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import "./App.css";

const TitleUpdater = () => {
  const location = useLocation();
  
  useEffect(() => {
    const baseTitle = "AMX-OUT";
    
    switch(location.pathname) {
      case '/':
        document.title = `${baseTitle} | Home`;
        break;
      case '/batches':
        document.title = `${baseTitle} | Production Orders`;
        break;
      case '/planar-motor':
        document.title = `${baseTitle} | Planar Motor`;
        break;
      case '/xbot-tracker':
        document.title = `${baseTitle} | Xbot Tracker`;
        break;
      case '/sop-dashboard': // Add this case
        document.title = `${baseTitle} | SOP Dashboard`;
        break;
      case '/settings':
        document.title = `${baseTitle} | Settings`;
        break;
      default:
        document.title = baseTitle;
    }
  }, [location]);
  
  return null;
};

export default function App() {
  const [globalMqttConnected, setGlobalMqttConnected] = useState(false);

  useEffect(() => {
    mqttService.connect();
    
    const requiredTopics = [
      'NN/Nybrovej/InnoLab/Configuration/CMD/Order/Done',
      'NN/Nybrovej/InnoLab/Configuration/CMD/Order/Acknowledge'
    ];
    
    const unsubscribe = mqttService.onConnectionChange(isConnected => {
      setGlobalMqttConnected(isConnected);
      console.log("App.jsx: MQTT connection status:", isConnected ? "Connected" : "Disconnected");
      
      if (isConnected) {
        requiredTopics.forEach(topic => {
          mqttService.subscribe(topic);
        });
      }
    });
    
    return () => {
      unsubscribe();
    };
  }, []);

  return (
    <Router>
      <TitleUpdater />
      <div className="app-container">
        <div className="navigation-sidebar">
          <div className="nav-header">
            <h2>Novo Nordisk</h2>
          </div>
          <nav className="nav-links">
            <NavLink to="/" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              <i className="nav-icon home-icon"></i>
              <span>Home</span>
            </NavLink>
            <NavLink to="/batches" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              <i className="nav-icon dashboard-icon"></i>
              <span>Production Orders</span>
            </NavLink>
            <NavLink to="/planar-motor" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              <i className="nav-icon config-icon"></i>
              <span>Planar Motor</span>
            </NavLink>
            <NavLink to="/xbot-tracker" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              <i className="nav-icon robot-icon"></i> 
              <span>Production Live View</span>
            </NavLink>
            {/* Add NavLink for SOP Dashboard */}
            <NavLink to="/sop-dashboard" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              <i className="nav-icon checklist-icon"></i>
              <span>SOP Dashboard</span>
            </NavLink>
            <NavLink to="/settings" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              <i className="nav-icon settings-icon"></i>
              <span>Settings</span>
            </NavLink>
          </nav>
          <div className="mqtt-status">
            <span className={`status-indicator ${globalMqttConnected ? 'connected' : 'disconnected'}`}></span>
            MQTT: {globalMqttConnected ? 'Connected' : 'Disconnected'}
          </div>
          <div className="amx-header">
            <h3>AMX-OUT Project</h3>
            <h4>Application Version 0.5</h4>
          </div>
        </div>
        
        <div className="app-content">
        <PlanarMotorProvider> 
            <PersistentRouter>
              <Route path="/" element={<Homepage />} />
              <Route path="/batches" element={<BatchConfigurator />} />
              <Route path="/planar-motor" element={<PlanarMotorConfigurator />} />
              <Route path="/xbot-tracker" element={<XbotTracker />} />
              <Route path="/sop-dashboard" element={<SOPDashboard />} /> {/* Add this route */}
              <Route path="/settings" element={<Settings />} />
            </PersistentRouter>
        </PlanarMotorProvider> 
        </div>
        <ToastContainer
          position="top-right"
          autoClose={3000}
          hideProgressBar={false}
          newestOnTop
          closeOnClick
          rtl={false}
          pauseOnFocusLoss
          draggable
          pauseOnHover
          theme="light"
        />
      </div>
    </Router>
  );
}