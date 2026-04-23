# Example: SimulationModel Submodel Configuration
# This shows how to configure the SimulationModel submodel for the imaDispensing asset

imaDispensingSystemAAS:
  idShort: imaDispensingSystemAAS
  id: "https://smartproductionlab.aau.dk/aas/imaDispensingSystem"
  
  # ... other submodel configurations ...
  
  # SimulationModel submodel configuration
  SimulationModel:
    # REQUIRED: Path to the simulation model file
    ModelPath: "simulation/ima_dispensing_model.py"
    
    # OPTIONAL: Description of the simulation model
    Description: "High-fidelity FEM-based simulation model for IMA dispensing system"
    
    # OPTIONAL: Type of simulation model
    # Examples: "PythonModule", "SimulinkModel", "FMU", "CosimModel"
    ModelType: "PythonModule"
    
    # OPTIONAL: Version of the simulation model
    Version: "1.0.0"
