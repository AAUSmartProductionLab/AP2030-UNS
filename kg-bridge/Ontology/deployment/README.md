# Deployment ABox Seed Files

Place static deployment-specific instance data in this directory as Turtle files.

These files are loaded by the Fuseki bootstrap service into the ABox graph
(default: urn:kg:abox).

Examples include station coordinates, fixed line topology, and named locations
that do not arrive through Kafka AAS CRUD events.

If no files are present, bootstrap skips this step.
