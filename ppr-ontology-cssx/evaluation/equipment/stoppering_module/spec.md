━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRODUCT DATASHEET                              Rev. 1.3 | EN
PlungerSet-80 Automated Stoppering Station
Elara Automation GmbH | www.elara-automation.de
Document No: EA-DS-PS080-EN | Release: 2024-04-08
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IDENTIFICATION
  Product Designation : PlungerSet-80 Stoppering Station
  Manufacturer        : Elara Automation GmbH
  Manufacturer Address: Brückenstraße 14, 70173 Stuttgart, Germany
  Contact             : +49 711 4920 0 | support@elara-automation.de
  Order Code          : EA-PS080-230V-EU
  Product Family      : PlungerSet Series
  Product Type        : PlungerSet-80
  Serial Number       : EA-PS-2024-00391
  Year of Construction: 2024
  Date of Manufacture : 2024-03-22
  Country of Origin   : DE
  Hardware Version    : 1.3
  Firmware Version    : 1.4.2
  URI of Product      : https://elara-automation.de/products/plungerset-80

  Note: The PlungerSet-80 shares its base platform, power supply, and
  firmware with the LinFill-120. Spare parts for the lift assembly are
  interchangeable between the two product lines.

ORDERING INFORMATION
  EA-PS080-230V-EU    Standard EU version, 230V AC adapter included
  EA-PS080-120V-US    North America version, 120V AC adapter included
  EA-PS080-MAG-EXT    Extended magazine kit (capacity 8 plungers, replaces
                      standard 4-plunger magazine; requires firmware ≥1.4)
  EA-PS080-SVC-1Y     1-year extended service contract, 48h on-site response
  EA-PS080-SPARE-ACT  Replacement 12V linear actuator assembly
  EA-PS080-SPARE-SRV  Replacement SG90 servo motor with pre-mounted gear
  EA-PS080-SPARE-MAG  Replacement triangular magazine channel (4-plunger)

  Compatible plunger types: 1mL ISO standard rubber plungers (tested with
  West Pharmaceutical 4432/50 Gray and Datwyler FM27 series).
  Plunger consumables not supplied by Elara Automation.

DESCRIPTION
  The PlungerSet-80 is an automated stoppering station that inserts rubber
  plungers into pre-filled syringes in laboratory and pilot filling lines.
  The station combines three mechanisms in a single compact unit:

  1. Vertical Lift: Identical to the LinFill-120 base. A 12V DC motor
     drives a lead screw to position the stoppering head at the correct
     height above the syringe. A limit switch provides homing.

  2. Plunger Magazine: A triangular-profile channel holding up to 4
     plungers in vertical orientation. The triangular cross-section was
     selected after testing circular and semicircular profiles, as it
     minimises inter-plunger friction while maintaining orientation.

  3. Feeding and Insertion: An SG90 servo motor drives a custom screw
     mechanism (1:4 gear ratio, 720° total rotation, 20mm linear travel)
     that advances one plunger into the insertion chamber. A 12V linear
     actuator then executes the plunger insertion stroke.

COMPONENTS
  Microcontroller  : ESP32-WROOM-32, WiFi 802.11 b/g/n, dual-core 240 MHz
  Motor Controller : L298N dual H-bridge, 5V onboard regulator, 2A/ch
  Lift Actuator    : 12V DC motor, 1.2 Nm, 80 RPM no-load
  Insert Actuator  : 12V linear actuator, 20mm stroke, 50N rated force
                     Retraction speed: ~8mm/s, Extension speed: ~5mm/s
  Feed Mechanism   : SG90 9g servo (5V, 1.8 kg·cm stall torque)
                     Gear drive: 2-stage, 1:4 ratio
                     Screw: 10mm pitch, 2 full rotations (720°), 20mm travel
  Position Sensing : 1× straight lever limit switch (lift homing)
  Magazine         : Triangular channel, 4-plunger capacity
                     Material: PLA (3D printed), replaceable
  Frame            : Powder-coated steel base, 3D-printed ABS upper assembly
  Power Supply     : 12V DC, 3A (IEC 60320 C14 inlet, 100–240V AC)

HIERARCHY
  PlungerSet-80 (this unit)
    └─ ESP32 Controller Module
    └─ L298N Motor Controller Board
    └─ 12V DC Lift Motor
    └─ Lead Screw Assembly (8mm, 2mm pitch)
    └─ 12V Linear Insert Actuator (20mm stroke)
    └─ SG90 Servo Feed Motor
    └─ Gear Drive Assembly (1:4 ratio, 2-stage)
    └─ Homing Limit Switch
    └─ Plunger Magazine Assembly (4-plunger capacity)

ELECTRICAL SPECIFICATIONS
  Supply Voltage    : 12V DC ±5% (lift motor, linear actuator)
                      5V regulated (servo, from L298N onboard regulator)
                      3.3V regulated (ESP32, from onboard LDO)
  Max Power Draw    : 22W (all actuators active simultaneously)
  Standby Power     : <1.8W
  Fuse              : 3.15A slow-blow (accessible on rear panel)
  Connector (power) : 5.5/2.1mm barrel jack, centre positive

  Note: The SG90 servo is powered from the L298N 5V regulator. If the
  extended magazine kit (EA-PS080-MAG-EXT) is installed, peak current draw
  increases to approximately 28W. Verify power supply rating before
  installing optional kits.

MECHANICAL SPECIFICATIONS
  Dimensions (W × D × H): 240 × 200 × 480 mm (lift extended)
                           240 × 200 × 330 mm (lift retracted)
  Weight                 : 3.1 kg (standard 4-plunger magazine)
                           3.3 kg (with EA-PS080-MAG-EXT)
  Mounting               : M6 bolts, 4-hole pattern, 150 × 120 mm PCD
                           Compatible with ACOPOS table mounting surface
  Magazine capacity      : 4 plungers (standard), 8 plungers (optional)
  Insertion stroke       : 20mm
  Lift travel            : 150mm (shared with LinFill-120)
  Repeatability (lift)   : ±0.5 mm after homing

COMMUNICATION INTERFACE
  Protocol    : MQTT 3.1.1 over WiFi (IEEE 802.11 b/g/n, 2.4 GHz)
  Broker      : Configured at deployment via provisioning interface
  Client ID   : plungerset80-{serialNumber}
  QoS         : Level 1 (at least once)
  Keepalive   : 60 seconds

  Published Topics:
    {base}/stoppering/state
      Payload  : string
      Values   : "IDLE" | "RUNNING" | "ERROR" | "HOMING"
      Frequency: on change

    {base}/stoppering/cycletime
      Payload  : float (seconds)
      Content  : duration of last completed stoppering cycle
      Frequency: on cycle completion

  Subscribed Topics:
    {base}/stoppering/cmd
      Payload  : string
      Values   : "START" | "STOP" | "HOME" | "RESET"

  Note: {base} topic prefix and broker address are site-specific and
  must be configured during commissioning. Not fixed product parameters.

ENVIRONMENTAL AND SAFETY
  Ambient Operating Temp : 5°C to 40°C
  Storage Temp           : -20°C to 60°C
  Humidity               : 20–80% RH, non-condensing
  IP Rating              : IP20

  CAUTION: The magazine feeding mechanism contains a rotating gear and
  screw assembly. Do not reach into the magazine slot while the station
  is powered. Maximum magazine load: 4 plungers (standard). Overloading
  the magazine may cause plunger jamming and servo stall damage.

  WARNING: The linear actuator extension force (50N) is sufficient to
  cause injury. Ensure the stoppering chamber is clear before issuing
  a START command.

FIRMWARE UPDATE PROCEDURE
  Identical to LinFill-120 (EA-DS-LF120-EN §Firmware Update).
  Access web interface at http://plungerset80-{serialNumber}.local
  Current firmware (v1.4.2) is shared across the LinFill/PlungerSet
  platform. Changelog identical to LinFill-120 release notes.

CERTIFICATIONS
  CE marking: LVD 2014/35/EU, EMC 2014/30/EU, RoHS 2011/65/EU
  WiFi radio: ESP32 FCC ID: 2AC7Z-ESPWROOM32

MAINTENANCE
  Recommended interval: every 500 operating hours
    - Lubricate lead screw (NLGI #2 grease)
    - Inspect magazine channel for wear or deformation (replace if cracked)
    - Verify servo gear mesh and backlash (replace gear set if >1mm play)
    - Check linear actuator end-stop and cable routing
    - Inspect all M3 fasteners for tightness
  Replacement magazine (EA-PS080-SPARE-MAG) requires firmware ≥1.3.

WARRANTY
  24 months from date of shipment.
  Excludes: magazine wear, SG90 servo damage from overload,
  3D-printed structural parts, plunger consumables.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━