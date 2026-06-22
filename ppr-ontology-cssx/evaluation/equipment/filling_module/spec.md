━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRODUCT DATASHEET                              Rev. 2.1 | EN
LinFill-120 Vertical Syringe Filling Station
Elara Automation GmbH | www.elara-automation.de
Document No: EA-DS-LF120-EN | Release: 2024-04-01
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IDENTIFICATION
  Product Designation : LinFill-120 Syringe Filling Station
  Manufacturer        : Elara Automation GmbH
  Manufacturer Address: Brückenstraße 14, 70173 Stuttgart, Germany
  Contact             : +49 711 4920 0 | support@elara-automation.de
  Order Code          : EA-LF120-230V-EU
  Product Family      : LinFill Series
  Product Type        : LinFill-120
  Serial Number       : EA-LF-2024-00472
  Year of Construction: 2024
  Date of Manufacture : 2024-03-15
  Country of Origin   : DE
  Hardware Version    : 2.1
  Firmware Version    : 1.4.2
  URI of Product      : https://elara-automation.de/products/linfill-120

ORDERING INFORMATION
  EA-LF120-230V-EU   Standard EU version, 230V AC adapter included
  EA-LF120-120V-US   North America version, 120V AC adapter included
  EA-LF120-230V-EU-C Same as EU version with pre-installed Cytiva needle top
  EA-LF120-SVC-1Y    1-year extended service contract, on-site response 48h
  EA-LF120-SPARE-TOP Spare removable needle top assembly (no needle)
  EA-LF120-SPARE-MTR Replacement 12V DC motor assembly with coupling

  Note: Needle consumables (Sanisure Fill4Sure, Cytiva Allegro Style) are
  not supplied by Elara Automation and must be ordered separately from
  the respective manufacturer.

DESCRIPTION
  The LinFill-120 is a compact, vertically-actuated syringe filling station
  designed for use in small-batch pharmaceutical and laboratory filling lines.
  The station accepts a removable needle top compatible with Sanisure
  Fill4Sure and Cytiva Allegro-style needles. Vertical position is
  controlled by a 12V DC motor driving a lead screw mechanism. Two
  integrated limit switches provide homing detection and upper travel
  limit protection. The station communicates over WiFi using the MQTT
  protocol, making it compatible with Unified Namespace (UNS) architectures.

  The LinFill-120 is intended for laboratory and pilot production use only.
  It is not certified for use in classified pharmaceutical clean rooms
  above ISO Class 7 without additional enclosure measures.

COMPONENTS
  Microcontroller : ESP32-WROOM-32 with integrated WiFi (802.11 b/g/n)
                    Dual-core Xtensa LX6, 240 MHz, 4MB Flash
  Motor Controller: L298N dual H-bridge, 5V onboard regulator
                    Max continuous current 2A per channel
  Actuator        : 12V DC motor, rated 1.2 Nm, 80 RPM no-load
                    Stall current: 3.5A (protected by L298N thermal shutdown)
  Position Sensing: 2× straight lever limit switches
                    Rating: 5A 250VAC, IP40, snap-action
  Needle Interface: Removable top assembly with dual tool clips
                    Compatible: Cytiva Allegro Style, Sanisure Fill4Sure
  Lead Screw      : 8mm diameter, 2mm pitch, 150mm travel
  Frame           : Powder-coated steel base, 3D-printed ABS upper structure
  Power Supply    : 12V DC, 3A external adapter (IEC 60320 C14 inlet)
                    Input: 100–240V AC, 50/60Hz (auto-ranging)

HIERARCHY
  LinFill-120 (this unit)
    └─ ESP32 Controller Module
    └─ L298N Motor Controller Board
    └─ 12V DC Drive Motor
    └─ Lead Screw Assembly (8mm, 2mm pitch)
    └─ Homing Limit Switch
    └─ Top Limit Switch
    └─ Removable Needle Top Assembly

ELECTRICAL SPECIFICATIONS
  Supply Voltage        : 12V DC ±5%
  Max Power Draw        : 18W (during full actuation)
  Standby Power         : <1.5W
  WiFi Supply (ESP32)   : 3.3V regulated onboard, max 500mA
  Motor Supply          : 12V direct, switched by L298N
  Fuse                  : 3.15A slow-blow (F1, accessible on rear panel)
  Connector type (power): 5.5/2.1mm barrel jack, centre positive

MECHANICAL SPECIFICATIONS
  Dimensions (W × D × H): 220 × 180 × 450 mm (needle extended)
                           220 × 180 × 310 mm (needle retracted)
  Weight                 : 2.4 kg (without needle consumable)
  Mounting               : M6 bolts, 4-hole pattern, 150 × 120 mm PCD
                           Compatible with ACOPOS table mounting surface
  Lead screw travel      : 150 mm
  Vertical speed         : ~3 mm/s (50% PWM), ~6 mm/s (100% PWM)
  Repeatability          : ±0.5 mm (homing cycle)

COMMUNICATION INTERFACE
  Protocol    : MQTT 3.1.1 over WiFi (IEEE 802.11 b/g/n, 2.4 GHz)
  Broker      : Configured at deployment via provisioning interface
  Client ID   : linfill120-{serialNumber}
  QoS         : Level 1 (at least once) for all topics
  Keepalive   : 60 seconds

  Published Topics:
    {base}/filling/state
      Payload  : string
      Values   : "IDLE" | "RUNNING" | "ERROR" | "HOMING"
      Frequency: on change

    {base}/filling/cycletime
      Payload  : float (seconds)
      Content  : duration of last completed fill cycle
      Frequency: on cycle completion

    {base}/filling/syringeweight
      Payload  : float (grams)
      Content  : weight reading taken post-fill
      Frequency: on cycle completion

  Subscribed Topics:
    {base}/filling/cmd
      Payload  : string
      Values   : "START" | "STOP" | "HOME" | "RESET"
      Response : triggers state change; acknowledged via state topic

  Note: {base} topic prefix and broker address are configured during
  commissioning and are not fixed product parameters.

ENVIRONMENTAL AND SAFETY
  Ambient Operating Temp : 5°C to 40°C
  Storage Temp           : -20°C to 60°C
  Humidity (operating)   : 20–80% RH, non-condensing
  Altitude               : up to 2000 m
  IP Rating              : IP20
  Pollution Degree       : 2 (IEC 60664-1)
  Installation Category  : II

  CAUTION: The lead screw and motor assembly contains moving parts.
  Keep hands clear of the vertical travel path during operation.
  Do not exceed the rated 3A fuse value when replacing fuses.
  The ESP32 module is not designed for use in safety-critical applications.

FIRMWARE UPDATE PROCEDURE
  1. Connect host PC to the same WiFi network as the device.
  2. Open browser and navigate to http://linfill120-{serialNumber}.local
  3. Select "Firmware Update" in the web interface.
  4. Upload the .bin file provided by Elara Automation support.
  5. Device will reboot automatically. Do not power off during update.
  Current firmware (v1.4.2) changelog:
    - Fixed rare watchdog reset during extended HOMING cycles
    - Improved MQTT reconnection logic after broker unavailability
    - Added syringeweight averaging over 3 readings (was 1)

CERTIFICATIONS AND COMPLIANCE
  CE marking in accordance with:
    - Low Voltage Directive (LVD) 2014/35/EU
    - EMC Directive 2014/30/EU
    - RoHS Directive 2011/65/EU
  WiFi radio: ESP32 FCC ID: 2AC7Z-ESPWROOM32

MAINTENANCE
  Recommended maintenance interval: every 500 operating hours
    - Inspect and lubricate lead screw (NLGI #2 grease)
    - Check limit switch actuation force and contact condition
    - Verify WiFi signal strength and broker connectivity
    - Check all M3 fasteners on motor and switch mounts for tightness
  Contact Elara Automation support for authorised repair procedures.
  Warranty void if unit is disassembled by unauthorised personnel.

WARRANTY
  24 months from date of shipment for manufacturing defects.
  Excludes: consumable needle tops, ESP32 WiFi antenna damage,
  damage caused by exceeding rated electrical specifications.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━