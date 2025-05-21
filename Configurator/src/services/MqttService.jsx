import mqtt from 'mqtt';
import { v4 as uuidv4 } from 'uuid';
import { toast } from 'react-toastify';

class MqttService {
  client = null;
  isConnected = false;
  connectionChangeHandlers = [];
  messageHandlers = {};
  pendingOrderData = null;

  // ... (onMessage, onConnectionChange, subscribe, notifyConnectionChange, disconnect, connect methods remain the same) ...
  onMessage(topic, handler) {
    if (!this.messageHandlers[topic]) {
      this.messageHandlers[topic] = [];
    }
    this.messageHandlers[topic].push(handler);
    console.log(`MqttService: Registered handler for topic: ${topic}`);

    if (this.client && this.isConnected) {
      this.client.subscribe(topic, (err) => {
        if (err) {
          console.error(`MqttService: Failed to subscribe to ${topic} for new handler`, err);
        } else {
          console.log(`MqttService: Subscribed to ${topic} for new handler.`);
        }
      });
    }

    return () => {
      this.messageHandlers[topic] = this.messageHandlers[topic].filter(h => h !== handler);
      // Consider unsubscribing if no handlers left, if necessary for your use case
      if (this.client && this.isConnected && this.messageHandlers[topic] && this.messageHandlers[topic].length === 0) {
        // console.log(`MqttService: Unsubscribing from ${topic} as no handlers are left.`);
        // this.client.unsubscribe(topic, (err) => {
        //   if (err) console.error(`MqttService: Failed to unsubscribe from ${topic}`, err);
        // });
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
      this.client.subscribe(topic, (err) => {
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
      this.client.end(true); // Force close, stop auto-reconnect for this instance
      // Set client to null *after* events related to disconnection might have fired or been handled.
      // The 'close' event handler will manage notifying connection change.
      // this.client = null; // Moved to 'close' handler or ensure it's robustly handled
    }
  }

  connect() {
    if (this.client && (this.client.connected || this.client.connecting)) {
        console.log('MqttService: Already connected or connecting.');
        return;
    }
    this.disconnect(); // Ensure any old client is properly ended.

    console.log('MqttService: Attempting to connect...');
    const savedSettings = localStorage.getItem('appSettings');
    
    let brokerHost = "192.168.0.104"; 
    let brokerPort = "8000";       
    let clientId = "configurator-" + Math.random().toString(16).substring(2, 8);

    if (savedSettings) {
      try {
        const settings = JSON.parse(savedSettings);
        brokerHost = settings.mqttBrokerHost || brokerHost;
        brokerPort = settings.mqttBrokerPort || brokerPort;
        clientId = settings.clientId || clientId;
      } catch (e) {
        console.error("MqttService: Error parsing appSettings", e);
        this.notifyConnectionChange(false, 'Failed to parse settings', 'error');
        return; 
      }
    }

    const brokerUrl = `ws://${brokerHost}:${brokerPort}/mqtt`;
    console.log(`MqttService: Connecting to ${brokerUrl} with ClientID: ${clientId}`);
    this.notifyConnectionChange(false, `Connecting to ${brokerHost}...`, 'info');

    try {
      this.client = mqtt.connect(brokerUrl, { 
        clientId: clientId,
        reconnectPeriod: 5000, // ms
        connectTimeout: 10000, // ms
        clean: true, // false to receive QoS 1 and 2 messages published while disconnected
      });

      this.client.on('connect', () => {
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
          this.client.publish(this.pendingOrderData.topic, this.pendingOrderData.message, { qos: 2, retain: true }, (error) => {
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
        // this.client = null; // Client is ended, can be set to null here.
      });

      this.client.on('offline', () => {
        console.log('MqttService: Client offline.');
        this.notifyConnectionChange(false, 'MQTT Offline', 'error');
      });

      this.client.on('error', (err) => {
        console.error('MqttService: Connection error:', err.message);
        // Avoid disconnecting here as the client might attempt to reconnect based on reconnectPeriod
        this.notifyConnectionChange(false, `MQTT Error: ${err.message}`, 'error');
      });

      this.client.on('message', (topic, payload) => {
        const message = payload.toString();
        if (this.messageHandlers[topic]) {
          this.messageHandlers[topic].forEach(handler => {
            try {
              let parsedMessage;
              try { parsedMessage = JSON.parse(message); } 
              catch (e) { parsedMessage = message; } // If not JSON, pass as string
              handler(parsedMessage);
            } catch (e) {
              console.error(`MqttService: Error in message handler for ${topic}`, e);
            }
          });
        }
      });

    } catch (error) {
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
  publish(topic, message, options, callback) {
    if (this.client && this.isConnected) {
      this.client.publish(topic, message, options, (error) => {
        if (error) {
          console.error('MqttService: MQTT publish error:', error, 'Topic:', topic);
          if (callback) callback(error);
        } else {
          // console.log(`MqttService: Message published to ${topic}`);
          if (callback) callback(null);
        }
      });
    } else {
      const errorMsg = `MQTT client not connected. Cannot publish to topic: ${topic}`;
      console.warn(`MqttService: ${errorMsg}`);
      toast.warn('MQTT not connected. Message not sent.');
      if (callback) callback(new Error(errorMsg));
    }
  }

  _publishHelper(topic, data, qos, retain, successMessage, errorMessage) {
    // This can now use the generic publish method or keep its promise structure
    return new Promise((resolve) => {
      try {
        const message = JSON.stringify(data);
        this.publish(topic, message, { qos, retain }, (error) => {
          if (error) {
            console.error(`${errorMessage} to ${topic}:`, error.message);
            toast.error(`${errorMessage} failed.`);
            resolve(false);
          } else {
            console.log(`${successMessage} to ${topic}`);
            toast.success(successMessage);
            resolve(true);
          }
        });
      } catch (e) {
        console.error(`MqttService: Error preparing publish to ${topic}:`, e);
        toast.error('Error preparing message for publish.');
        resolve(false);
      }
    });
  }

  publishLayout(layoutData) {
    return this._publishHelper(
      'NN/Nybrovej/InnoLab/Configuration/DATA/Planar/Stations',
      layoutData, 2, true,
      'Layout published successfully', 'Error publishing layout'
    );
  }

  publishLimits(limitsData) {
    return this._publishHelper(
      'NN/Nybrovej/InnoLab/Configuration/DATA/Planar/Limits',
      limitsData, 2, true,
      'Limits published successfully', 'Error publishing limits'
    );
  }

  publishOrders(queueData) {
    if (!queueData || queueData.length === 0) {
      console.warn('MqttService: Queue is empty, nothing to publish for orders.');
      return;
    }
    
    try {
      const topic = 'NN/Nybrovej/InnoLab/Configuration/DATA/Order';
      const firstBatch = { ...queueData[0] }; 

      if (!firstBatch.uuid) {
        firstBatch.uuid = uuidv4();
      }
      
      const formattedOrder = {
          UUID: firstBatch.uuid,
          ProductId: `${firstBatch.product}${firstBatch.packaging?.match(/\(([^)]+)\)/)?.at(1).replace(/\s/g, '') || ''}`,
          Format: firstBatch.packaging?.match(/\(([^)]+)\)/)?.at(1) || '',
          Units: parseInt(firstBatch.volume?.replace(/[^\d]/g, '') || 0, 10),
          IPCw: firstBatch.ipcWeighing || 0,
          IPCi: firstBatch.ipcInspection || 0,
          "QC-samples": parseInt(firstBatch.qcCount || 0, 10)
      };
  
      const message = JSON.stringify(formattedOrder);
      
      if (!this.client || !this.isConnected) {
        console.warn('MqttService: MQTT not connected. Order will be published upon connection.');
        this.pendingOrderData = { topic, message, uuid: firstBatch.uuid };
        toast.info('Order queued, will send when MQTT connects.');
        return;
      }
      
      // Using the generic publish method here for consistency
      this.publish(topic, message, { qos: 2, retain: true }, (error) => {
        if (error) {
          console.error('MqttService: Error publishing order:', error);
          toast.error('Failed to publish order.');
        } else {
          console.log(`MqttService: Order published successfully to ${topic} with UUID: ${firstBatch.uuid}`);
          toast.success('Order published successfully.');
        }
      });
    } catch (error) {
      console.error('MqttService: Error in publishOrders operation:', error);
      toast.error('Error processing order for publish.');
    }
  }

  sendCommand(command) {
    const topic = `NN/Nybrovej/InnoLab/bt_controller/CMD/${command}`;
    const payload = JSON.stringify({}); // Standard empty JSON payload
    // Using the generic publish method
    this.publish(topic, payload, { qos: 2, retain: false }, (error) => { // Using QoS 1 and no retain for commands
      if (error) {
        // Error already logged by publish method and toast shown
        console.warn(`MqttService: Failed to send command '${command}'.`);
      } else {
        console.log(`MqttService: Command '${command}' published to ${topic}`);
         toast.info(`Command '${command}' sent.`); // Optional: toast for command sent
      }
    });
  }

  startSystem() {
    this.sendCommand('Start');
  }

  stopSystem() {
    this.sendCommand('Stop');
  }

  resetSystem() {
    this.sendCommand('Clear');
  }

  holdSystem() {
    this.sendCommand('Suspend');
  }

  unholdSystem() {
    this.sendCommand('Unsuspend');
  }
}

const mqttServiceInstance = new MqttService();
export default mqttServiceInstance;