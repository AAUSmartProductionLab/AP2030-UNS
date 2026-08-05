"""
Shared constants for the aas_idta package.

All project-specific semantic IDs are defined here.
IDTA-defined semantic IDs (admin-shell.io/idta/...) stay in their generated templates.
Third-party semantic IDs (w3.org, schema.org, purl.org, etc.) stay inline in their modules.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# Base URLs
# ═══════════════════════════════════════════════════════════════════════════════

BASE_URL = "https://smartproductionlab.aau.dk"
SCHEMA_BASE = "https://aausmartproductionlab.github.io/AP2030-UNS/MQTTSchemas"

# ═══════════════════════════════════════════════════════════════════════════════
# Infrastructure defaults
# ═══════════════════════════════════════════════════════════════════════════════

BROKER = "mqtt://192.168.0.104:1883"
SITE = "NN/Nybrovej/InnoLab"

# ═══════════════════════════════════════════════════════════════════════════════
# Ontology
# ═══════════════════════════════════════════════════════════════════════════════

CSSX = "http://www.w3id.org/aau-ra/cssx"

# ═══════════════════════════════════════════════════════════════════════════════
# MQTT Asset Interfaces Description — extended fields
# ═══════════════════════════════════════════════════════════════════════════════

AID_MQTT_RESPONSE_FORM = f"{BASE_URL}/aid/MqttResponseForm/1/0"
AID_MQTT_RETAIN = f"{BASE_URL}/aid/MqttRetain/1/0"
AID_MQTT_CONTROL_PACKET = f"{BASE_URL}/aid/MqttControlPacket/1/0"
AID_MQTT_QOS = f"{BASE_URL}/aid/MqttQos/1/0"
AID_INPUT_SCHEMA = f"{BASE_URL}/aid/InputSchema/1/0"
AID_OUTPUT_SCHEMA = f"{BASE_URL}/aid/OutputSchema/1/0"
AID_SYNCHRONOUS = f"{BASE_URL}/aid/Synchronous/1/0"

