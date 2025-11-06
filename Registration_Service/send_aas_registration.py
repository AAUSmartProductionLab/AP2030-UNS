#!/usr/bin/env python3
"""
Send any AAS JSON file for registration via MQTT

Wraps the AAS JSON in the required registration message format.

Usage:
    python3 send_aas_registration.py <path-to-aas-json-file>
    python3 send_aas_registration.py ../schemas/ResourceDescription/imaLoadingSystem.json
"""

import json
import time
import uuid
import paho.mqtt.client as mqtt
import os
import sys
import argparse

# Default MQTT Configuration
DEFAULT_BROKER = "192.168.0.104"
DEFAULT_PORT = 1883
DEFAULT_REQUEST_TOPIC = "NN/Nybrovej/InnoLab/Registration/Request"
DEFAULT_RESPONSE_TOPIC = "NN/Nybrovej/InnoLab/Registration/Response"

# Response tracking (will be set in send_registration_request)
response_received = False
response_data = None
request_id = None
mqtt_broker = None
mqtt_port = None
request_topic = None
response_topic = None


def on_connect(client, userdata, flags, rc):
    """Callback when connected to MQTT broker"""
    if rc == 0:
        print(f"✓ Connected to MQTT broker {mqtt_broker}:{mqtt_port}")
        # Subscribe to response topic
        client.subscribe(response_topic, qos=2)
        print(f"✓ Subscribed to response topic: {response_topic}")
    else:
        print(f"✗ Failed to connect with code: {rc}")


def on_message(client, userdata, msg):
    """Callback when message received"""
    global response_received, response_data
    
    try:
        response = json.loads(msg.payload.decode('utf-8'))
        resp_request_id = response.get('requestId')
        
        # Check if this is our response
        if resp_request_id == request_id:
            response_received = True
            response_data = response
            print(f"\n✓ Received response:")
            print(f"  Request ID: {resp_request_id}")
            print(f"  Success: {response.get('success')}")
            print(f"  Message: {response.get('message')}")
    except Exception as e:
        print(f"✗ Error parsing response: {e}")


def send_registration_request(aas_file_path, broker=None, port=None, req_topic=None, resp_topic=None):
    """Send registration request and wait for response"""
    global response_received, response_data, request_id, mqtt_broker, mqtt_port, request_topic, response_topic
    
    # Set configuration
    mqtt_broker = broker or DEFAULT_BROKER
    mqtt_port = port or DEFAULT_PORT
    request_topic = req_topic or DEFAULT_REQUEST_TOPIC
    response_topic = resp_topic or DEFAULT_RESPONSE_TOPIC
    request_id = str(uuid.uuid4())
    response_received = False
    response_data = None
    
    # Extract asset name from file for display
    asset_name = os.path.basename(aas_file_path).replace('.json', '')
    
    print("=" * 60)
    print(f"AAS Registration: {asset_name}")
    print("=" * 60)
    print()
    
    # Load the AAS JSON file
    if not os.path.isabs(aas_file_path):
        # If relative path, resolve it
        aas_file_path = os.path.abspath(aas_file_path)
    
    try:
        with open(aas_file_path, 'r') as f:
            aas_data = json.load(f)
        print(f"✓ Loaded AAS data from {os.path.basename(aas_file_path)}")
        print(f"  Path: {aas_file_path}")
    except FileNotFoundError:
        print(f"✗ File not found: {aas_file_path}")
        return False
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON in file: {e}")
        return False
    
    # Wrap in registration message format
    # Note: assetId is optional - it will be auto-extracted from the AAS idShort
    registration_message = {
        "requestId": request_id,
        "aasData": aas_data
    }
    
    # Create MQTT client
    client = mqtt.Client(client_id=f"aas-registration-{uuid.uuid4().hex[:8]}")
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        # Connect to broker
        print(f"Connecting to MQTT broker {mqtt_broker}:{mqtt_port}...")
        client.connect(mqtt_broker, mqtt_port, keepalive=60)
        client.loop_start()
        
        # Wait for connection
        time.sleep(2)
        
        # Send registration request
        print(f"\nSending registration request:")
        print(f"  Request ID: {request_id}")
        print(f"  Asset ID: (will be auto-extracted from AAS)")
        print(f"  Topic: {request_topic}")
        print()
        
        result = client.publish(
            request_topic,
            json.dumps(registration_message),
            qos=2
        )
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print("✓ Registration request sent successfully")
        else:
            print(f"✗ Failed to send request: {result.rc}")
            return
        
        # Wait for response (timeout 60 seconds)
        print("\nWaiting for response...")
        timeout = 60
        elapsed = 0
        
        while not response_received and elapsed < timeout:
            time.sleep(1)
            elapsed += 1
            if elapsed % 5 == 0:
                print(f"  ... waiting ({elapsed}s / {timeout}s)")
        
        if response_received:
            print("\n" + "=" * 60)
            print("Registration completed!")
            print("=" * 60)
            
            if response_data and response_data.get('success'):
                print(f"\n✓ Asset registered successfully!")
                print("\nThe DataBridge has been configured and restarted.")
                print("You can now:")
                print("  - Check DataBridge logs: docker logs databridge --tail 50")
                print("  - View configs: ls -la ../databridge/")
                return True
            else:
                error_msg = response_data.get('message', 'Unknown error') if response_data else 'Unknown error'
                print(f"\n✗ Registration failed: {error_msg}")
                return False
        else:
            print("\n✗ No response received within timeout")
            print("  Make sure the registration service is running:")
            print("  cd Registration_Service")
            print("  python3 aas-registration-service.py listen")
            return False
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        client.loop_stop()
        client.disconnect()
        print("\nDisconnected from MQTT broker")


def main():
    """Main entry point with argument parsing"""
    parser = argparse.ArgumentParser(
        description='Send AAS JSON file for registration via MQTT',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Register IMA Loading System
  python3 send_aas_registration.py ../schemas/ResourceDescription/imaLoadingSystem.json
  
  # Register Syntegon Stoppering System
  python3 send_aas_registration.py ../schemas/ResourceDescription/SyntegonStopperingSystemInstance.json
  
  # With custom MQTT broker
  python3 send_aas_registration.py myasset.json --broker 192.168.1.100 --port 1883
        '''
    )
    
    parser.add_argument(
        'aas_file',
        help='Path to the AAS JSON file to register'
    )
    
    parser.add_argument(
        '--broker',
        default=DEFAULT_BROKER,
        help=f'MQTT broker address (default: {DEFAULT_BROKER})'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=DEFAULT_PORT,
        help=f'MQTT broker port (default: {DEFAULT_PORT})'
    )
    
    parser.add_argument(
        '--request-topic',
        default=DEFAULT_REQUEST_TOPIC,
        help=f'MQTT registration request topic (default: {DEFAULT_REQUEST_TOPIC})'
    )
    
    parser.add_argument(
        '--response-topic',
        default=DEFAULT_RESPONSE_TOPIC,
        help=f'MQTT registration response topic (default: {DEFAULT_RESPONSE_TOPIC})'
    )
    
    args = parser.parse_args()
    
    # Check if file exists
    if not os.path.exists(args.aas_file):
        print(f"✗ Error: File not found: {args.aas_file}")
        sys.exit(1)
    
    # Send registration request
    success = send_registration_request(
        args.aas_file,
        broker=args.broker,
        port=args.port,
        req_topic=args.request_topic,
        resp_topic=args.response_topic
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
