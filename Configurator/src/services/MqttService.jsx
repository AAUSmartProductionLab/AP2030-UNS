import mqtt from 'mqtt';
import { v4 as uuidv4 } from 'uuid';
import { toast } from 'react-toastify';

class MqttService {
  client = null;
  isConnected = false;
  connectionChangeHandlers = [];
  messageHandlers = {};
  pendingOrderData = null; // To store order data if publish is called while disconnected

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
      this.client = null;
      this.notifyConnectionChange(false, 'MQTT Disconnected', 'warn');
    }
  }

  connect() {
    this.disconnect(); 

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
        return; // Stop connection attempt if settings parse fails
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
        clean: true,
      });

      this.client.on('connect', () => {
        console.log('MqttService: Connected!');
        this.notifyConnectionChange(true, 'MQTT Connected Successfully!', 'success');
        
        // Re-subscribe to topics
        Object.keys(this.messageHandlers).forEach(topic => {
          if (this.messageHandlers[topic]?.length > 0) {
            this.client.subscribe(topic, (err) => {
              if (err) console.error(`MqttService: Failed to re-subscribe to ${topic}`, err);
              else console.log(`MqttService: Re-subscribed to ${topic}`);
            });
          }
        });

        // Publish any pending order
        if (this.pendingOrderData) {
          console.log("MqttService: Publishing pending order data.");
          this.client.publish(this.pendingOrderData.topic, this.pendingOrderData.message, { qos: 2, retain: true }, (error) => {
            if (error) console.error('MqttService: Error publishing pending order:', error);
            else console.log('MqttService: Pending order published successfully.');
            this.pendingOrderData = null; // Clear pending data
          });
        }
      });

      this.client.on('reconnect', () => {
        console.log(`MqttService: Reconnecting to ${brokerUrl}...`);
        toast.info('MQTT Reconnecting...');
      });

      this.client.on('close', () => {
        console.log('MqttService: Connection closed.');
        if (this.client) { // If client still exists, it was an unexpected close
            this.notifyConnectionChange(false, 'MQTT Connection Closed', 'warn');
        }
      });

      this.client.on('offline', () => {
        console.log('MqttService: Client offline.');
        this.notifyConnectionChange(false, 'MQTT Offline', 'error');
      });

      this.client.on('error', (err) => {
        console.error('MqttService: Connection error:', err.message);
        this.notifyConnectionChange(false, `MQTT Error: ${err.message}`, 'error');
      });

      this.client.on('message', (topic, payload) => {
        const message = payload.toString();
        //console.log(`MqttService: Message on [${topic}]: ${message.substring(0,100)}...`);
        if (this.messageHandlers[topic]) {
          this.messageHandlers[topic].forEach(handler => {
            try {
              let parsedMessage;
              try { parsedMessage = JSON.parse(message); } 
              catch (e) { parsedMessage = message; }
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

  _publishHelper(topic, data, qos, retain, successMessage, errorMessage) {
    if (!this.client || !this.isConnected) {
      console.warn(`MqttService: Cannot publish to ${topic}. Client not connected.`);
      toast.warn('MQTT not connected. Message not sent.');
      return Promise.resolve(false); // Return a resolved Promise with `false`
    }
  
    return new Promise((resolve) => {
      try {
        const message = JSON.stringify(data);
        this.client.publish(topic, message, { qos, retain }, (error) => {
          if (error) {
            console.error(`${errorMessage} to ${topic}:`, error);
            toast.error(`${errorMessage} failed.`);
            resolve(false); // Resolve the Promise with `false`
          } else {
            console.log(`${successMessage} to ${topic}`);
            toast.success(successMessage);
            resolve(true); // Resolve the Promise with `true`
          }
        });
      } catch (e) {
        console.error(`MqttService: Error preparing publish to ${topic}:`, e);
        toast.error('Error preparing message for publish.');
        resolve(false); // Resolve the Promise with `false`
      }
    });
  }

  publishLayout(layoutData) {
    return this._publishHelper(
      'NN/Nybrovej/InnoLab/Configuration/DATA/Planar/Stations',
      layoutData, 2, true,
      'Layout published successfully', 'Error publishing layout'
    ).then((success) => {
      console.log('publishLayout with status:', success);
      return success; // Return the success status
    });
  }

  publishLimits(limitsData) {
    return this._publishHelper(
      'NN/Nybrovej/InnoLab/Configuration/DATA/Planar/Limits',
      limitsData, 2, true,
      'Limits published successfully', 'Error publishing limits'
    ).then((success) => {
      console.log('publishLimits with status:', success);
      return success; // Return the success status
    });
  }

  publishOrders(queueData) {
    if (!queueData || queueData.length === 0) {
      console.warn('MqttService: Queue is empty, nothing to publish for orders.');
      return;
    }
    
    try {
      const topic = 'NN/Nybrovej/InnoLab/Configuration/DATA/Order';
      const firstBatch = { ...queueData[0] }; // Work with a copy

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
        this.pendingOrderData = { topic, message, uuid: firstBatch.uuid }; // Store UUID for logging
        toast.info('Order queued, will send when MQTT connects.');
        return;
      }
      
      this.client.publish(topic, message, { qos: 2, retain: true }, (error) => {
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
}

const mqttServiceInstance = new MqttService();
export default mqttServiceInstance;