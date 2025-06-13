import mqtt from 'mqtt';
import { v4 as uuidv4 } from 'uuid';
import { toast } from 'react-toastify';

class MqttService {
  client = null;
  isConnected = false;
  connectionChangeHandlers = [];
  messageHandlers = {};
  pendingOrderData = null;
  connectionInProgress = false;
  
  // Message caching to prevent duplicate processing
  messageCache = new Map();
  cacheTimeout = 50; // ms

  onMessage(topic, handler) {
    if (!this.messageHandlers[topic]) {
      this.messageHandlers[topic] = [];
    }
    this.messageHandlers[topic].push(handler);
    console.log(`MqttService: Registered handler for topic: ${topic}`);

    if (this.client && this.isConnected) {
      this.client.subscribe(topic, { qos: 1 }, (err) => { // Use QoS 1 instead of 2 for better performance
        if (err) {
          console.error(`MqttService: Failed to subscribe to ${topic} for new handler`, err);
        } else {
          console.log(`MqttService: Subscribed to ${topic} for new handler.`);
        }
      });
    }

    return () => {
      this.messageHandlers[topic] = this.messageHandlers[topic].filter(h => h !== handler);
      if (this.client && this.isConnected && this.messageHandlers[topic] && this.messageHandlers[topic].length === 0) {
        this.client.unsubscribe(topic, (err) => {
          if (err) console.error(`MqttService: Failed to unsubscribe from ${topic}`, err);
        });
      }
    };
  }

  onConnectionChange(handler) {
    this.connectionChangeHandlers.push(handler);
    handler(this.isConnected); // Notify immediately with current status
    return () => {
      this.connectionChangeHandlers = this.connectionChangeHandlers.filter(h => h !== handler);
    };
  }

  subscribe(topic) {
    if (this.client && this.isConnected) {
      this.client.subscribe(topic, { qos: 1 }, (err) => {
        if (err) {
          console.error(`MqttService: Failed to subscribe to ${topic}`, err);
        } else {
          console.log(`MqttService: Subscribed to ${topic}`);
        }
      });
    } else {
      console.warn(`MqttService: Cannot subscribe to ${topic}. Client not connected.`);
    }
  }

  notifyConnectionChange(status, message, toastType = 'info') {
    if (this.isConnected !== status) {
      this.isConnected = status;
      this.connectionChangeHandlers.forEach(handler => {
        try {
          handler(this.isConnected);
        } catch (e) {
          console.error("MqttService: Error in connectionChangeHandler:", e);
        }
      });
    }

    if (message) {
      toast[toastType] ? toast[toastType](message) : toast.info(message);
    }
  }

  disconnect() {
    if (this.client) {
      console.log('MqttService: Disconnecting...');
      this.connectionInProgress = false;
      this.client.end(true);
      this.client = null; // Set to null immediately
    }
  }

  // Optimized message handling with caching
  setupMessageHandler() {
    this.client.on('message', (topic, payload) => {
      const message = payload.toString();
      const now = Date.now();
      const cacheKey = `${topic}:${message}`;
      
      // Skip duplicate messages within cache timeout
      if (this.messageCache.has(cacheKey)) {
        const lastTime = this.messageCache.get(cacheKey);
        if (now - lastTime < this.cacheTimeout) {
          return;
        }
      }
      this.messageCache.set(cacheKey, now);
      
      // Clean old cache entries
      if (this.messageCache.size > 1000) {
        const entries = Array.from(this.messageCache.entries());
        entries.slice(0, 500).forEach(([key]) => this.messageCache.delete(key));
      }

      if (this.messageHandlers[topic]) {
        this.messageHandlers[topic].forEach(handler => {
          try {
            let parsedMessage;
            try { 
              parsedMessage = JSON.parse(message); 
            } catch (e) { 
              parsedMessage = message; 
            }
            handler(parsedMessage);
          } catch (e) {
            console.error(`MqttService: Error in message handler for ${topic}`, e);
          }
        });
      }
    });
  }

  // Add a method to ensure single instance
  ensureConnection() {
    if (!this.client || (!this.client.connected && !this.client.connecting && !this.connectionInProgress)) {
      this.connect();
    }
  }

  connect() {
    // Prevent multiple simultaneous connection attempts
    if (this.connectionInProgress) {
      console.log('MqttService: Connection already in progress.');
      return;
    }

    if (this.client && (this.client.connected || this.client.connecting)) {
      console.log('MqttService: Already connected or connecting.');
      return;
    }

    this.connectionInProgress = true;
    this.disconnect(); // Ensure any old client is properly ended.

    console.log('MqttService: Attempting to connect...');
    const savedSettings = localStorage.getItem('appSettings');
    
    let brokerHost = "192.168.0.104"; 
    let brokerPort = "8000";       
    // Use more specific client IDs to avoid conflicts
    let clientId = `configurator-${window.location.hostname}-${Date.now()}-${Math.random().toString(16).substring(2, 8)}`;

    if (savedSettings) {
      try {
        const settings = JSON.parse(savedSettings);
        brokerHost = settings.mqttBrokerHost || brokerHost;
        brokerPort = settings.mqttBrokerPort || brokerPort;
        // Don't use saved clientId to avoid conflicts
        clientId = `configurator-${settings.sessionId || 'session'}-${Date.now()}-${Math.random().toString(16).substring(2, 8)}`;
      } catch (e) {
        console.error("MqttService: Error parsing appSettings", e);
        this.notifyConnectionChange(false, 'Failed to parse settings', 'error');
        this.connectionInProgress = false;
        return; 
      }
    }

    const brokerUrl = `ws://${brokerHost}:${brokerPort}/mqtt`;
    console.log(`MqttService: Connecting to ${brokerUrl} with ClientID: ${clientId}`);
    this.notifyConnectionChange(false, `Connecting to ${brokerHost}...`, 'info');

    try {
      this.client = mqtt.connect(brokerUrl, { 
        clientId: clientId,
        reconnectPeriod: 5000,
        connectTimeout: 10000,
        clean: true, // Use clean sessions for better performance
        keepalive: 30,
        protocolVersion: 4,
        // Add these for better performance
        properties: {
          maximumPacketSize: 65536,
          receiveMaximum: 100,
          topicAliasMaximum: 10
        }
      });

      this.client.on('connect', () => {
        this.connectionInProgress = false;
        console.log('MqttService: Connected!');
        this.notifyConnectionChange(true, 'MQTT Connected Successfully!', 'success');
        
        Object.keys(this.messageHandlers).forEach(topic => {
          if (this.messageHandlers[topic]?.length > 0) {
            this.client.subscribe(topic, { qos: 1 }, (err) => { // Using QoS 1 for subscriptions
              if (err) console.error(`MqttService: Failed to re-subscribe to ${topic}`, err);
              else console.log(`MqttService: Re-subscribed to ${topic}`);
            });
          }
        });

        if (this.pendingOrderData) {
          console.log("MqttService: Publishing pending order data.");
          this.client.publish(this.pendingOrderData.topic, this.pendingOrderData.message, { qos: 1, retain: true }, (error) => {
            if (error) {
                console.error('MqttService: Error publishing pending order:', error);
                toast.error('Failed to send queued order.');
            } else {
                console.log('MqttService: Pending order published successfully.');
                toast.success('Queued order sent successfully.');
            }
            this.pendingOrderData = null; 
          });
        }
      });

      this.client.on('reconnect', () => {
        console.log(`MqttService: Reconnecting to ${brokerUrl}...`);
        this.notifyConnectionChange(false, 'MQTT Reconnecting...', 'info');
      });

      this.client.on('close', () => {
        console.log('MqttService: Connection closed.');
        // Only notify if it wasn't a deliberate disconnect where client is set to null
        if (this.client) { 
            this.notifyConnectionChange(false, 'MQTT Connection Closed', 'warn');
        }
      });

      this.client.on('offline', () => {
        console.log('MqttService: Client offline.');
        this.notifyConnectionChange(false, 'MQTT Offline', 'error');
      });

      this.client.on('error', (err) => {
        this.connectionInProgress = false;
        console.error('MqttService: Connection error:', err.message);
        this.notifyConnectionChange(false, `MQTT Error: ${err.message}`, 'error');
      });

      // Replace the existing message handler setup
      this.setupMessageHandler();

    } catch (error) {
      this.connectionInProgress = false;
      console.error('MqttService: Error during MQTT client setup:', error);
      this.notifyConnectionChange(false, 'MQTT Setup Error', 'error');
    }
  }
  
  /**
   * Generic publish method.
   * @param {string} topic The topic to publish to.
   * @param {string | Buffer} message The message to publish.
   * @param {object} [options] Optional MQTT publish options (e.g., qos, retain).
   * @param {function} [callback] Optional callback.
   */
  publish(topic, message, options = {}, callback) {
    const defaultOptions = { qos: 1, retain: false };
    const publishOptions = { ...defaultOptions, ...options };

    if (this.client && this.isConnected) {
      this.client.publish(topic, message, publishOptions, (error) => {
        if (error) {
          console.error('MqttService: MQTT publish error:', error, 'Topic:', topic);
        } else {
          console.log(`MqttService: Successfully published to ${topic}`);
        }
        if (callback) callback(error);
      });
    } else {
      const errorMsg = `MQTT client not connected. Cannot publish to topic: ${topic}`;
      console.warn(`MqttService: ${errorMsg}`);
      toast.warn('MQTT not connected. Message not sent.');
      if (callback) callback(new Error(errorMsg));
    }
  }

  _publishHelper(topic, data, qos = 1, retain = false, successMessage, errorMessage) {
    return new Promise((resolve) => {
      try {
        const jsonData = JSON.stringify(data);
        this.publish(topic, jsonData, { qos, retain }, (error) => {
          if (error) {
            console.error(`MqttService: ${errorMessage}:`, error);
            toast.error(errorMessage);
            resolve(false);
          } else {
            console.log(`MqttService: ${successMessage}`);
            toast.success(successMessage);
            resolve(true);
          }
        });
      } catch (e) {
        console.error(`MqttService: JSON serialization error for ${topic}:`, e);
        toast.error('Failed to serialize data for publishing.');
        resolve(false);
      }
    });
  }
  /**Temporary Implementation, SORRY Martin**/
  publishOrders(queueData) {
    const topic = "NN/Nybrovej/InnoLab/Configuration/DATA/Order"; 
    const firstOrder = (queueData && queueData.length > 0) ? queueData[0] : {};

    const dataToPublish = {
      "Uuid": firstOrder.Uuid,
      "ProductId": firstOrder.ProductId,
      "Format": firstOrder.packaging,
      "Units": parseInt(firstOrder.volume, 10),
      "IPCw": firstOrder.ipcWeighing,
      "IPCi": firstOrder.ipcInspection,
      "QC-samples": parseInt(firstOrder.qcCount, 10),
      "TimeStamp": new Date().toISOString() 
    };
    
    return this._publishHelper(
      topic,
      dataToPublish,
      1,
      true,
      'Production order published successfully!',
      'Failed to publish production order');
  }

  publishTaskRepsonse(response) {
    const topic = 'NN/Nybrovej/InnoLab/Intervention/DATA/Task';
    const dataWithTimestamp = {
      ...response,
      TimeStamp: new Date().toISOString()
    };
    return this._publishHelper(
      topic,
      dataWithTimestamp,
      2,
      false,
      'Task response sent',
      'Failed to send task response'
    );
  }

  publishLayout(layoutData) {
    const topic = "NN/Nybrovej/InnoLab/Configuration/DATA/Planar/Stations";
    const dataWithTimestamp = {
      ...layoutData,
      TimeStamp: new Date().toISOString()
    };
    return this._publishHelper(
      topic, 
      dataWithTimestamp, 
      1, 
      true, 
      'Layout published successfully!', 
      'Failed to publish layout'
    );
  }

  publishLimits(limitsData) {
    const topic = "NN/Nybrovej/InnoLab/Configuration/DATA/Planar/Limits";
    const dataWithTimestamp = {
      ...limitsData,
      TimeStamp: new Date().toISOString()
    };
    return this._publishHelper(
      topic, 
      dataWithTimestamp, 
      1, 
      true, 
      'Limits published successfully!', 
      'Failed to publish limits'
    );
  }

  // System control methods
  startSystem() {
    const topic = "NN/Nybrovej/InnoLab/bt_controller/CMD/Start";
    const message = JSON.stringify({ Command: "Start", Timestamp: new Date().toISOString() });
    this.publish(topic, message, { qos: 1, retain: false });
  }

  stopSystem() {
    const topic = "NN/Nybrovej/InnoLab/bt_controller/CMD/Stop";
    const message = JSON.stringify({ Command: "Stop", Timestamp: new Date().toISOString() });
    this.publish(topic, message, { qos: 1, retain: false });
  }

  resetSystem() {
    const topic = "NN/Nybrovej/InnoLab/bt_controller/CMD/Reset";
    const message = JSON.stringify({ Command: "Reset", Timestamp: new Date().toISOString() });
    this.publish(topic, message, { qos: 1, retain: false });
  }

  holdSystem() {
    const topic = "NN/Nybrovej/InnoLab/bt_controller/CMD/Hold";
    const message = JSON.stringify({ Command: "Hold", Timestamp: new Date().toISOString() });
    this.publish(topic, message, { qos: 1, retain: false });
  }

  unholdSystem() {
    const topic = "NN/Nybrovej/InnoLab/bt_controller/CMD/Unhold";
    const message = JSON.stringify({ Command: "Unhold", Timestamp: new Date().toISOString() });
    this.publish(topic, message, { qos: 1, retain: false });
  }

  publishPlanarCommand(buttonId) {
    const topic = "NN/Nybrovej/InnoLab/Planar/CMD/Command";
    const message = JSON.stringify({
      ButtonId: buttonId,
      TimeStamp: new Date().toISOString()
    });
    
    this.publish(topic, message, { qos: 2, retain: false }, (error) => {
      if (error) {
        console.error(`MqttService: Failed to publish Planar command ${buttonId}:`, error);
      } else {
        console.log(`MqttService: Successfully published Planar command: ${buttonId}`);
      }
    });
  }
}



// Export singleton instance
const mqttService = new MqttService();
export default mqttService;