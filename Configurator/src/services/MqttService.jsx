import mqtt from 'mqtt';
import { v4 as uuidv4 } from 'uuid';
import { toast } from 'react-toastify';

class MqttService {
  constructor() {
    this.client = null;
    this.isConnected = false;
    this.connectionCallbacks = [];
    this.messageHandlers = {}; // Store message handlers by topic
    this._pendingSubscriptions = [];
  }

  // Add method to register for connection status updates
  onConnectionChange(callback) {
    this.connectionCallbacks.push(callback);
    // Immediately notify with current status
    callback(this.isConnected);
    return () => {
      this.connectionCallbacks = this.connectionCallbacks.filter(cb => cb !== callback);
    };
  }

  onMessage(topic, callback) {
    // Check if we already have this exact callback registered
    // This helps prevent duplicate registrations
    if (this.messageHandlers[topic] && 
        this.messageHandlers[topic].some(cb => cb.toString() === callback.toString())) {
      console.log(`Handler already registered for topic: ${topic}, skipping duplicate`);
      
      // Return a no-op unsubscribe function to avoid errors
      return () => {};
    }
    
    console.log(`Registering handler for topic: ${topic}`);
    
    if (!this.messageHandlers[topic]) {
      this.messageHandlers[topic] = [];
    }
    this.messageHandlers[topic].push(callback);
    
    // Return unsubscribe function
    return () => {
      console.log(`Unregistering handler for topic: ${topic}`);
      this.messageHandlers[topic] = this.messageHandlers[topic].filter(cb => cb !== callback);
    };
  }

  // Update connection status and notify listeners
  setConnectionStatus(status) {
    this.isConnected = status;
    this.connectionCallbacks.forEach(callback => callback(status));
  }

  connect() {
    // Only connect if not already connected
    if (this.client && this.isConnected) {
      console.log('MQTT already connected, reusing connection');
      return;
    }
  
    try {
      console.log('Connecting to MQTT broker...');
      
      this.client = mqtt.connect('ws://192.168.0.104:8000/mqtt', {
        clientId: `${"Production Configurator"}_${uuidv4().substring(0, 8)}`,
        reconnectPeriod: 3000,
        connectTimeout: 10000
      });
      
      // IMPORTANT: Register connect event first
      this.client.on('connect', () => {
        console.log('Connected to MQTT broker successfully!');
        this.isConnected = true;
        
        // Process any pending subscriptions
        if (this._pendingSubscriptions.length > 0) {
          console.log(`Processing ${this._pendingSubscriptions.length} pending subscriptions`);
          
          // Process each pending subscription
          this._pendingSubscriptions.forEach(topic => {
            console.log(`Subscribing to previously pending topic: ${topic}`);
            this.client.subscribe(topic, (err) => {
              if (err) {
                console.error(`Error subscribing to ${topic}:`, err);
                toast.error(`Failed to subscribe to ${topic}`);
              } else {
                console.log(`Successfully subscribed to ${topic}`);
              }
            });
          });
          
          // Clear pending subscriptions after processing
          this._pendingSubscriptions = [];
        }
        
        // Notify all connection listeners
        this.connectionCallbacks.forEach(callback => callback(true));
      });
      
      // Then register message handler
      this.client.on('message', (topic, message) => {
        console.log(`Received message on ${topic}:`, message.toString());
        
        // Forward to appropriate handlers
        const handlers = this.messageHandlers[topic];
        if (handlers && handlers.length > 0) {
          console.log(`Found ${handlers.length} handlers for topic ${topic}`);
          
          const messageStr = message.toString();
          let messageObj;
          
          try {
            messageObj = JSON.parse(messageStr);
            console.log('Parsed message object:', messageObj);
          } catch (e) {
            console.warn('Failed to parse message as JSON, using raw string');
            messageObj = messageStr;
          }
          
          handlers.forEach(handler => {
            try {
              handler(messageObj, topic);
            } catch (err) {
              console.error(`Error in message handler for topic ${topic}:`, err);
              toast.error(`Error processing message: ${err.message}`);
            }
          });
        } else {
          console.log(`No handlers registered for topic ${topic}`);
        }
      });
      
      // Add error handler
      this.client.on('error', (err) => {
        console.error('MQTT connection error:', err);
        toast.error(`MQTT connection error: ${err.message}`);
        this.setConnectionStatus(false);
      });
  
      // Add offline handler
      this.client.on('offline', () => {
        console.log('MQTT connection offline');
        this.setConnectionStatus(false);
      });
      
      // Add reconnect handler
      this.client.on('reconnect', () => {
        console.log('Attempting to reconnect to MQTT broker...');
      });
      
      // Add close handler
      this.client.on('close', () => {
        console.log('MQTT connection closed');
        this.setConnectionStatus(false);
      });
      
    } catch (error) {
      console.error('MQTT connection error:', error);
      toast.error(`MQTT connection error: ${error.message}`);
      this.setConnectionStatus(false);
    }
  }

  subscribe(topic) {
    if (!this.client) {
      console.warn(`MQTT client not initialized, cannot subscribe to ${topic}`);
      // Save for later subscription when connection is established
      if (!this._pendingSubscriptions.includes(topic)) {
        console.log(`Adding ${topic} to pending subscriptions (client not initialized)`);
        this._pendingSubscriptions.push(topic);
      }
      return false;
    }
  
    if (!this.isConnected) {
      console.warn(`MQTT not connected yet, will subscribe to ${topic} when connected`);
      if (!this._pendingSubscriptions.includes(topic)) {
        console.log(`Adding ${topic} to pending subscriptions (not connected)`);
        this._pendingSubscriptions.push(topic);
      }
      return false;
    }
    
    // We're connected, so subscribe now
    console.log(`Subscribing to ${topic} immediately`);
    this.client.subscribe(topic, (err) => {
      if (err) {
        console.error(`Error subscribing to ${topic}:`, err);
        toast.error(`Failed to subscribe to ${topic}`);
      } else {
        console.log(`Successfully subscribed to ${topic}`);
      }
    });
    
    return true;
  }

  // Add a method to check connection status before publishing
  publishLayout(layoutData) {
    if (!this.client || !this.isConnected) {
      console.error('MQTT not connected, cannot publish');
      // You can add a notification for users here
      return false;
    }

    try {
      const topic = 'NN/Nybrovej/InnoLab/Configuration/DATA/Planar/Stations';
      const message = JSON.stringify(layoutData);
      
      this.client.publish(topic, message, { qos: 2, retain: true }, (error) => {
        if (error) {
          console.error('Error publishing layout:', error);
          return false;
        } else {
          console.log('Layout published successfully to', topic);
          return true;
        }
      });
    } catch (error) {
      console.error('Error in publish operation:', error);
      return false;
    }
    
    return true;
  }

  // Add new method for publishing configurations
  publishConfig(configData) {
    if (!this.client || !this.isConnected) {
      console.error('MQTT not connected, cannot publish configuration');
      return false;
    }

    try {
      const topic = 'NN/Nybrovej/InnoLab/Configuration/DATA/Planar/Limits';
      const message = JSON.stringify(configData);
      
      this.client.publish(topic, message, { qos: 1, retain: true }, (error) => {
        if (error) {
          console.error('Error publishing configuration:', error);
          return false;
        } else {
          console.log('Configuration published successfully to', topic);
          return true;
        }
      });
    } catch (error) {
      console.error('Error in publish operation:', error);
      return false;
    }
    
    return true;
  }

  // Add new method for publishing limits
  publishLimits(limitsData) {
    if (!this.client || !this.isConnected) {
      console.error('MQTT not connected, cannot publish limits');
      return false;
    }

    try {
      const topic = 'NN/Nybrovej/InnoLab/Configuration/DATA/Planar/Limits';
      const message = JSON.stringify(limitsData);
      
      this.client.publish(topic, message, { qos: 2, retain: true }, (error) => {
        if (error) {
          console.error('Error publishing limits:', error);
          return false;
        } else {
          console.log('Limits published successfully to', topic);
          return true;
        }
      });
    } catch (error) {
      console.error('Error in publish operation:', error);
      return false;
    }
    
    return true;
  }

  publishOrders(queueData) {
    if (!this.client) {
      console.error('MQTT client not initialized, cannot publish orders');
      return false;
    }
  
    // Check if queue has any items
    if (!queueData || queueData.length === 0) {
      console.warn('Queue is empty, nothing to publish');
      return false;
    }
    
    try {
      const topic = 'NN/Nybrovej/InnoLab/Configuration/DATA/Order';
      
      // Take only the first entry in the queue
      const firstBatch = queueData[0];
      
      // Generate a UUID for this order if it doesn't already have one
      if (!firstBatch.uuid) {
        firstBatch.uuid = uuidv4();
        
        // Update the queue item with the UUID (this is a side effect, 
        // but ensures the UUID persists with the batch)
        const index = queueData.findIndex(b => b.id === firstBatch.id);
        if (index !== -1) {
          queueData[index] = { ...firstBatch };
        }
      }
      
      // Format the queue data to match required structure
      const formattedOrders = {
          UUID: firstBatch.uuid,
          ProductId: `${firstBatch.product}${firstBatch.packaging?.match(/\(([^)]+)\)/)?.at(1).replace(/\s/g, '') || ''}`,
          Format: firstBatch.packaging?.match(/\(([^)]+)\)/)?.at(1) || '',
          Units: parseInt(firstBatch.volume?.replace(/[^\d]/g, '') || 0, 10),
          IPCw: firstBatch.ipcWeighing || 0,
          IPCi: firstBatch.ipcInspection || 0,
          "QC-samples": parseInt(firstBatch.qcCount || 0, 10)
        };
  
      const message = JSON.stringify(formattedOrders);
      
      if (!this.isConnected) {
        console.warn('MQTT not connected yet, will publish when connected');
        this.pendingOrderData = {topic, message};
        return false;
      }
      
      this.client.publish(topic, message, { qos: 2, retain: true }, (error) => {
        if (error) {
          console.error('Error publishing order:', error);
          return false;
        } else {
          console.log('First order published successfully to', topic, 'with UUID:', firstBatch.uuid);
          return true;
        }
      });
    } catch (error) {
      console.error('Error in publish operation:', error);
      return false;
    }
    
    return true;
  }

  disconnect() {
    if (this.client && this.isConnected) {
      console.log('Disconnecting from MQTT broker...');
      
      this.client.end(true, () => {
        console.log('Disconnected from MQTT broker');
        this.isConnected = false;
        
        // Notify all connection listeners
        this.connectionCallbacks.forEach(callback => callback(false));
      });
    }
  }
}

// Create a singleton instance
const mqttService = new MqttService();
export default mqttService;