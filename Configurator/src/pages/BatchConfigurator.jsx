import React, { useState, useEffect, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid'; 
import { toast } from 'react-toastify';

import '../styles/BatchConfigurator.css';
import { BatchSidebar } from '../components/BatchSidebar/BatchSidebar';
import mqttService from '../services/MqttService';
import aasService from '../services/AasService';


export default function BatchConfigurator() {
  
  // State to track form inputs
  const initialState = {
  "Uuid": uuidv4(),
  "Format": "Cartridge (1mL)",
  "Units": 40000,
  "IPCw": 90,
  "IPCi": 85,
  "QC-samples": 100,
  "TimeStamp": new Date().toISOString(),
  // Extended fields for AAS
  "product": "",
  "productFamily": "",
  "volume": "",
  "primaryPackaging": "",
  "qcCount": "50",
  "ipcWeighing": 75,
  "ipcInspection": 80,
  "productionTemperature": "22.0",
  "humidity": "45.0",
  "selectedRecipe": ""
  };

  // Use the initial state object for useState
  const [batchConfig, setBatchConfig] = useState(initialState);
  const [mqttConnected, setMqttConnected] = useState(false);
  const firstQueueItemRef = useRef(null);

  // Load queue and log data from localStorage on component mount
  const [queue, setQueue] = useState(() => {
    const savedQueue = localStorage.getItem('batchQueue');
    return savedQueue ? JSON.parse(savedQueue) : [
      {
        id: 'batch-1',
        name: 'MIM8 Standard (15L)',
        product: 'MIM8',
        volume: '5000 units',
        packaging: 'Cartridge (3mL)',
        status: 'Pending'
      },
      {
        id: 'batch-2',
        name: 'Concizumb (15L)',
        product: 'Concizumb',
        volume: '5000 units',
        packaging: 'Prefilled Syringe (3mL)',
        status: 'Pending'
      }
    ];//
  });
  
  const [log, setLog] = useState(() => {
    const savedLog = localStorage.getItem('batchLog');
    return savedLog ? JSON.parse(savedLog) : [
      {
        id: 'log-1',
        name: 'MIM8 Medium Batch (20L)',
        product: 'MIM8',
        completedDate: '2025-04-30',
        status: 'Completed'
      },
      {
        id: 'log-2',
        name: 'Sogroya Medium Batch (50L)',
        product: 'Sogroya',
        completedDate: '2025-04-29',
        status: 'Completed'
      }
    ];
  });

  // Save queue to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem('batchQueue', JSON.stringify(queue));
  }, [queue]);

  // Save log to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem('batchLog', JSON.stringify(log));
  }, [log]);

  // Connect to MQTT broker on component mount
  useEffect(() => {
    // Don't establish connection - just register for updates
    const unsubscribeConnection = mqttService.onConnectionChange((connected) => {
      setMqttConnected(connected);
      
      // If we just got a connection status and have queue data, publish the first item
      if (connected && queue && queue.length > 0) {
        firstQueueItemRef.current = queue[0].id;
        mqttService.publishOrders(queue);
      }
    });
    
    // Just register message handlers
    const unsubscribeAcknowledge = mqttService.onMessage(
      'NN/Nybrovej/InnoLab/Configuration/CMD/Order/Acknowledge', 
      (message) => handleOrderAcknowledge(message)
    );
    
    const unsubscribeDone = mqttService.onMessage(
      'NN/Nybrovej/InnoLab/Configuration/CMD/Order/Done', 
      (message) => handleOrderDone(message)
    );
    
    return () => {
      unsubscribeConnection();
      unsubscribeAcknowledge();
      unsubscribeDone();
    };
  }, []);

  // Publish queue changes to MQTT
  useEffect(() => {
    if (mqttConnected && queue && queue.length > 0) {
      const currentFirstItemId = queue[0].id;
      
      if (firstQueueItemRef.current !== currentFirstItemId) {
        mqttService.publishOrders(queue);
        firstQueueItemRef.current = currentFirstItemId;
        
        // Show toast notification
        toast.info(`Publishing production order: ${queue[0].name}`, {
          icon: "📤"
        });
      }
    } else if (queue && queue.length === 0 && firstQueueItemRef.current !== null) {
      mqttService.publishOrders([]);
      firstQueueItemRef.current = null;
      
      // Show toast notification
      toast.info('Queue empty, notifying production system', {
        icon: "📭"
      });
    }
  }, [queue, mqttConnected]);
  
  const packagingOptions = [
    { id: '1', name: 'Cartridge (3mL)' },
    { id: '2', name: 'Cartridge (1mL)' },
    { id: '3', name: 'Prefilled Syringe (3mL)' },
    { id: '4', name: 'Prefilled Syringe (2.5mL)' }
  ];

  // Updated recipe presets with realistic pharmaceutical products
  const recipePresets = [
    { 
      id: '1', 
      name: 'MIM8 Standard (15L)',
      config: {
        product: 'MIM8',
        productFamily: 'Monoclonal Antibodies',
        volume: '5000', // 15L/3mL = 5000 units
        primaryPackaging: '1', // Cartridge (3mL)
        qcCount: '50',
        ipcWeighing: 75,
        ipcInspection: 80,
        productionTemperature: '22.0',
        humidity: '45.0'
      }
    },
    { 
      id: '7', 
      name: 'MIM8 Medium Batch (20L)',
      config: {
        product: 'MIM8',
        productFamily: 'Monoclonal Antibodies',
        volume: '8000', // 20L/2.5mL = 8000 units
        primaryPackaging: '4', // Prefilled Syringe (2.5mL)
        qcCount: '65',
        ipcWeighing: 85,
        ipcInspection: 75,
        productionTemperature: '22.0',
        humidity: '45.0'
      }
    },
    { 
      id: '2', 
      name: 'MIM8 High Volume (40L)',
      config: {
        product: 'MIM8',
        productFamily: 'Monoclonal Antibodies',
        volume: '40000', // 40L/1mL = 40000 units
        primaryPackaging: '2', // Cartridge (1mL)
        qcCount: '100',
        ipcWeighing: 90,
        ipcInspection: 85,
        productionTemperature: '22.0',
        humidity: '45.0'
      }
    },
    { 
      id: '3', 
      name: 'Concizumb (15L)',
      config: {
        product: 'Concizumb',
        productFamily: 'Biosimilars',
        volume: '5000', // 15L/3mL = 5000 units
        primaryPackaging: '3', // Prefilled Syringe (3mL)
        qcCount: '75',
        ipcWeighing: 95,
        ipcInspection: 90,
        productionTemperature: '20.0',
        humidity: '50.0'
      }
    },
    { 
      id: '4', 
      name: 'HgH Large Batch (100L)',
      config: {
        product: 'HgH',
        productFamily: 'Growth Hormones',
        volume: '40000', // 100L/2.5mL = 40000 units
        primaryPackaging: '4', // Prefilled Syringe (2.5mL)
        qcCount: '150',
        ipcWeighing: 100,
        ipcInspection: 100,
        productionTemperature: '18.0',
        humidity: '40.0'
      }
    },
    { 
      id: '5', 
      name: 'Sogroya Medium Batch (50L)',
      config: {
        product: 'Sogroya',
        productFamily: 'Growth Hormones',
        volume: '16665', // 50L/3mL ≈ 16667 units
        primaryPackaging: '3', // Prefilled Syringe (3mL)
        qcCount: '90',
        ipcWeighing: 85,
        ipcInspection: 95,
        productionTemperature: '18.0',
        humidity: '42.0'
      }
    },
    { 
      id: '6', 
      name: 'Sogroya Large Batch (100L)',
      config: {
        product: 'Sogroya',
        productFamily: 'Growth Hormones',
        volume: '30000', // 100L/1mL = 100000 units
        primaryPackaging: '1', // Cartridge (3mL)
        qcCount: '120',
        ipcWeighing: 80,
        ipcInspection: 90,
        productionTemperature: '18.0',
        humidity: '42.0'
      }
    }
  ];

  // Handle input changes
  const handleChange = (e) => {
    const { name, value } = e.target;
    
    // If recipe selection changed
    if (name === 'selectedRecipe' && value) {
      const selectedRecipe = recipePresets.find(recipe => recipe.id === value);
      if (selectedRecipe) {
        setBatchConfig({
          ...batchConfig,
          selectedRecipe: value,
          ...selectedRecipe.config
        });
        return;
      }
    }
    
    // Normal field update
    setBatchConfig({
      ...batchConfig,
      [name]: value
    });
  };

  const addBatchToQueue = (batchData) => {
    const getPackagingName = (id) => {
      const pkg = packagingOptions.find(p => p.id === id);
      return pkg ? pkg.name : 'Unknown packaging';
    };

    const batchUuid = uuidv4();
    const packagingName = getPackagingName(batchData.primaryPackaging);
    
    const newBatch = {
      id: `batch-${Date.now()}`,
      Uuid: batchUuid,
      name: `${batchData.product} (${batchData.volume} units)`,
      product: batchData.product,
      productFamily: batchData.productFamily || batchData.product,
      volume: `${batchData.volume} units`,
      packaging: packagingName,
      status: 'Pending',
      qcCount: batchData.qcCount,
      ipcWeighing: batchData.ipcWeighing,
      ipcInspection: batchData.ipcInspection,
      productionTemperature: batchData.productionTemperature,
      humidity: batchData.humidity,
      orderTimestamp: new Date().toISOString()
    };

    // Add to queue
    setQueue(prevQueue => [...prevQueue, newBatch]);
    toast.success(`Added batch: ${newBatch.name} to queue`);
  };

  const removeBatchFromQueue = (batchId) => {
    // Find the batch to check its status
    const batchToRemove = queue.find(batch => batch.id === batchId);
    
    if (!batchToRemove) return;
    
    // If the batch is running, show a confirmation dialog
    if (batchToRemove.status === 'Running') {
      // Use custom toast notification with user confirmation
      toast.warn(
        <div>
          <p>This batch is currently running.</p>
          <p>Are you sure you want to remove it?</p>
          <div className="toast-buttons">
            <button onClick={() => {
              // Remove the batch on confirm
              setQueue(prevQueue => prevQueue.filter(batch => batch.id !== batchId));
              toast.success(`Removed batch: ${batchToRemove.name}`);
              toast.dismiss();
            }}>
              Yes, Remove
            </button>
            <button onClick={() => toast.dismiss()}>Cancel</button>
          </div>
        </div>,
        {
          autoClose: false,
          closeOnClick: false
        }
      );
      return;
    }
    
    // Proceed with removal for non-running batches
    setQueue(prevQueue => prevQueue.filter(batch => batch.id !== batchId));
    toast.info(`Removed batch: ${batchToRemove.name}`);
  };

  /**
   * Handler for when a batch is moved to the top of the queue
   * Posts the Product AAS with "{productName}AAS" naming to the server
   */
  const handleBatchMovedToTop = async (batch) => {
    try {
      console.log('Batch moved to top of queue:', batch);
      await aasService.postActiveProductAas(batch);
    } catch (error) {
      console.error('Failed to post active Product AAS:', error);
      // Toast error is already shown by the service
    }
  };

  const handleOrderAcknowledge = (message) => {
    try {
      console.log('Acknowledge message received:', message);
      
      // Use UUID for matching instead of ProductId
      if (!message || !message.UUID) {
        console.warn('Received acknowledge message without UUID');
        toast.warning('Received invalid acknowledge message');
        return;
      }
  
      // Find the batch with matching UUID
      setQueue(currentQueue => {
        if (currentQueue.length === 0) return currentQueue;
        
        // Find batch with matching UUID
        const batchIndex = currentQueue.findIndex(batch => batch.Uuid === message.UUID);
        
        if (batchIndex !== -1) {
          // Get the batch name for the notification
          const batchName = currentQueue[batchIndex].name;
          
          // Update the status to "Running"
          const updatedQueue = [...currentQueue];
          updatedQueue[batchIndex] = { ...updatedQueue[batchIndex], status: 'Running' };
          
          // Show toast notification
          toast.info(`Order acknowledged: ${batchName} is now running`, {
            icon: "🔄",
            autoClose: 5000
          });
          
          return updatedQueue;
        } else {
          toast.warning(`Received acknowledge for unknown batch UUID: ${message.UUID}`);
        }
        
        return currentQueue;
      });
    } catch (error) {
      console.error('Error handling order acknowledgement:', error);
      toast.error(`Error processing acknowledgement: ${error.message}`);
    }
  };

  const handleOrderDone = (message) => {
    try {
      console.log('Done message received:', message);
      
      // Use UUID for matching instead of ProductId
      if (!message || !message.UUID) {
        console.warn('Received done message without UUID');
        toast.warning('Received invalid completion message - missing UUID');
        return;
      }
  
      // Find the batch with matching UUID
      setQueue(currentQueue => {
        if (currentQueue.length === 0) {
          console.warn('Queue is empty, cannot find batch to mark as done');
          toast.warning('Cannot process completion - queue is empty');
          return currentQueue;
        }
        
        // Find batch with matching UUID
        const batchIndex = currentQueue.findIndex(batch => batch.Uuid === message.UUID);
        
        if (batchIndex !== -1) {
          const completedBatch = currentQueue[batchIndex];
          
          // Show toast notification for completion
          toast.success(`Batch ${completedBatch.name} completed successfully!`, {
            icon: "✅",
            autoClose: 5000
          });
          
          // Move the batch to the log
          const logEntry = {
            id: `log-${Date.now()}`,
            name: completedBatch.name,
            product: completedBatch.product,
            completedDate: new Date().toISOString().slice(0, 10),
            status: 'Completed'
          };
          
          // Add to log
          setLog(prevLog => [...prevLog, logEntry]);
          
          // Remove from queue
          return currentQueue.filter(batch => batch.Uuid !== message.UUID);
        } else {
          toast.warning(`Received completion for unknown batch UUID: ${message.UUID}`);
        }
        
        return currentQueue;
      });
    } catch (error) {
      console.error('Error handling order completion:', error);
      toast.error(`Error processing completion: ${error.message}`);
    }
  };

  // Handle form submission
  const handleSubmit = (e) => {
    e.preventDefault();
    console.log('Submitted batch configuration:', batchConfig);
    
    // Validate form
    if (!batchConfig.product || !batchConfig.volume || !batchConfig.primaryPackaging) {
      alert('Please fill in all required fields: Product, Volume, and Packaging');
      return;
    }
    
    // Add the batch to the queue
    addBatchToQueue(batchConfig);
    
    // Optionally reset the form
    // setBatchConfig(initialState);
  };

  const handleReset = () => {
    setBatchConfig(initialState);
  };

  return (
    <div className="batch-configurator-page">
      <h1>Production Orders</h1>
      
      <div className="page-container">
        <div className="configurator-container">
          <div className="configurator-header">
            <h2>Batch Configurator</h2>
            <p>Configure production batch parameters and quality control settings</p>
          </div>
        <form onSubmit={handleSubmit} className="configurator-form">
          <div className="config-section">
            <div className="section-header">
              <h2>Production Recipe</h2>
            </div>
            <div className="section-content">
              <div className="form-group">
                <label htmlFor="selectedRecipe">Preset Recipe:</label>
                <select 
                  id="selectedRecipe" 
                  name="selectedRecipe" 
                  value={batchConfig.selectedRecipe}
                  onChange={handleChange}
                  className="form-select"
                >
                  <option value="">-- Select a Recipe --</option>
                  {recipePresets.map(recipe => (
                    <option key={recipe.id} value={recipe.id}>
                      {recipe.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
          <div className="config-section">
            <div className="section-header">
              <h2>Product Specifications</h2>
            </div>
            <div className="section-content two-columns">
              <div className="form-group">
                <label htmlFor="product">Product Name:</label>
                <input 
                  type="text" 
                  id="product" 
                  name="product" 
                  value={batchConfig.product}
                  onChange={handleChange}
                  className="form-input"
                  placeholder="Enter product name"
                />
              </div>
              
              <div className="form-group">
                <label htmlFor="productFamily">Product Family:</label>
                <input 
                  type="text" 
                  id="productFamily" 
                  name="productFamily" 
                  value={batchConfig.productFamily}
                  onChange={handleChange}
                  className="form-input"
                  placeholder="e.g., Monoclonal Antibodies"
                />
              </div>
              
              <div className="form-group">
                <label htmlFor="volume">Units:</label>
                <input 
                  type="number" 
                  id="volume" 
                  name="volume" 
                  min="1" 
                  step="1" // Integer steps only
                  value={batchConfig.volume}
                  onChange={handleChange}
                  className="form-input"
                  placeholder="Enter number of units"
                />
              </div>
            </div>
          </div>

          <div className="config-section">
            <div className="section-header">
              <h2>Packaging Information</h2>
            </div>
            <div className="section-content two-columns">
              <div className="form-group">
                <label htmlFor="primaryPackaging">Primary Packaging:</label>
                <select 
                  id="primaryPackaging" 
                  name="primaryPackaging" 
                  value={batchConfig.primaryPackaging}
                  onChange={handleChange}
                  className="form-select"
                >
                  <option value="">-- Select Packaging --</option>
                  {packagingOptions.map(pkg => (
                    <option key={pkg.id} value={pkg.id}>
                      {pkg.name}
                    </option>
                  ))}
                </select>
              </div>
              
              <div className="form-group">
                <label htmlFor="qcCount">Number of QC Samples:</label>
                <input 
                  type="number" 
                  id="qcCount" 
                  name="qcCount" 
                  step="1"
                  value={batchConfig.qcCount}
                  onChange={handleChange}
                  className="form-input"
                  placeholder="Enter number of QC samples"
                />
              </div>
            </div>
          </div>

          <div className="config-section">
            <div className="section-header">
              <h2>Environmental Requirements</h2>
            </div>
            <div className="section-content two-columns">
              <div className="form-group">
                <label htmlFor="productionTemperature">Production Temperature (°C):</label>
                <input 
                  type="number" 
                  id="productionTemperature" 
                  name="productionTemperature" 
                  step="0.1"
                  min="15"
                  max="30"
                  value={batchConfig.productionTemperature}
                  onChange={handleChange}
                  className="form-input"
                  placeholder="e.g., 22.0"
                />
              </div>
              
              <div className="form-group">
                <label htmlFor="humidity">Humidity (%RH):</label>
                <input 
                  type="number" 
                  id="humidity" 
                  name="humidity" 
                  step="0.1"
                  min="30"
                  max="70"
                  value={batchConfig.humidity}
                  onChange={handleChange}
                  className="form-input"
                  placeholder="e.g., 45.0"
                />
              </div>
            </div>
          </div>

          <div className="config-section">
            <div className="section-header">
              <h2>In-Process Controls</h2>
            </div>
            <div className="section-content two-columns">
              <div className="form-group">
                <label htmlFor="ipcWeighing">
                  In-Process Control Weighing (%)
                  <span className="value-display">{batchConfig.ipcWeighing}%</span>
                </label>
                <input 
                  type="range" 
                  id="ipcWeighing" 
                  name="ipcWeighing" 
                  min="0" 
                  max="100"
                  value={batchConfig.ipcWeighing}
                  onChange={handleChange}
                  className="form-slider"
                />
                <div className="slider-labels">
                  <span>0%</span>
                  <span>50%</span>
                  <span>100%</span>
                </div>
              </div>
              
              <div className="form-group">
                <label htmlFor="ipcInspection">
                  In-Process Control Inspection (%)
                  <span className="value-display">{batchConfig.ipcInspection}%</span>
                </label>
                <input 
                  type="range" 
                  id="ipcInspection" 
                  name="ipcInspection" 
                  min="0" 
                  max="100"
                  value={batchConfig.ipcInspection}
                  onChange={handleChange}
                  className="form-slider"
                />
                <div className="slider-labels">
                  <span>0%</span>
                  <span>50%</span>
                  <span>100%</span>
                </div>
              </div>
            </div>
          </div>
          <div className="config-actions">
              <button type="submit" className="btn btn-primary">
                Configure Batch
              </button>
              <button type="button" className="btn btn-secondary">
                Save as Draft
              </button>
              <button 
                type="button" 
                className="btn btn-tertiary"
                onClick={handleReset}
              >
                Reset Form
              </button>
          </div>
        </form>
      </div>
      <BatchSidebar
        queue={queue} 
        setQueue={setQueue}
        log={log}
        setLog={setLog}
        onRemoveBatch={removeBatchFromQueue}
        onBatchMovedToTop={handleBatchMovedToTop}/>
    </div>
    </div>
  );
}