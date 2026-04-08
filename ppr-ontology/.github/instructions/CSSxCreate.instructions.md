
# Extending CSS ontology for AAS compatibility

This overall objetive is to create an extension of the CSS ontology provided in the CSS-Ontology.ttl file. This extension should detail the product, process and resource in such a way that it is possible to apply standardized submodels e.g. submodel templates to each of the concepts.

## How do we do it?

We need to start by understanding the relevant submodel templates and their relation to each of the PPR concepts. So, I have made a list of submodels that should be present in each AAS that represent ProductAAS, ProcessAAS and ResourceAAS. What is really important is that we DON'T describe the concepts in AAS terms yet. They need to more generic than that like a product is composed of parts and a product has a manufacturer, order number etc. We need to convert each of the AAS types from below into generic concepts that describe the PPR within the PPR-CSS model as we have seen before.

### ProductAAS
 The productAAS consist of the following 
- Bill of Material (BoM) – A hierarchical SMT IDTA 02011-1-1 structure describing the product’s parts and subassemblies. Each part or subassembly has its own AAS.

- Bill of Processes (BoP) – A custom structure analogous to the BoM: every part and subassembly has its own BoP, allowing the overall BoP to be assembled dynamically from the product hierarchy. In practice, you look up the product, retrieve its parts, identify their associated processes, and combine them into a unified BoP.

- Technical Data - A SMT IDTA 02003 for storing generic technical information about for operation, static data and design specs. General information, productClassifications, TechnicalPropertyAreas, specificDescriptions. This will be used to define order information like batch size, order timestamp, packaging, status and so on.

- Digital Nameplate - A SMT IDTA 02006 for identifying the product Serial/Batch Number, Manufacturing Date, etc.

### ProcessAAS
The processAAS is not a high priority as of now since planning comes later, but we have to keep in mind what this submodel should contain. This list of submodels and their information is therefore incomplete at the current time.

- Process Information - Describes the production process of a given production run. The overarching process type for the production.

- RequiredCapabilities - The generated list of required capabilities from the BoPs of each part/product.

- Policy - submodel containing the technology specific production policy e.g. behaviour tree or BPMN or similar.


### ResourceAAS

- Parameters – static configuration values for a resource. E.g. location, orientation that are independent of skill parameters. This does not yet have a submodel template so it also needs to be custom. 
- Variables – dynamic values (software/logical variables, sensor measurements, etc.). These should be similar to sensor4.0 (SMT IDTA 02029-1) but extended to either do measurements or logical variables. And it should reference the AID submodel where the data is coming from. However, it might also follow the IDTA 02008 for timeseries data but the problem is that for a given resource it might have multiple live measurements and timeseries data. Therefore, we need to take the essence of the SMT IDTA 02008 and put it into a submodel element collection available in the Variables submodel.
- Capabilities – high‑level functional abilities of the resource. So far, this submodel will be custom since none exist that will work for it.
- Skills – executable behaviours that realise these capabilities. CC (SMT IDTA 02016-1-0) modified to reference the AID submodel.
- AssetInterfaceDescription – AID, AIMC SMTs that describe how to connect to a given asset. This description should be referenced in the Skills and Variables submodels for all live data entering and commands getting invoked by the AAS.
- BoM - describing the equipment hierarchy and this links to the lower level components that can given resource is composed of. The Hierarchical structures SMT is used for this.
- Digital Nameplate (SMT IDTA 02006) for identifying the resource.

## The execution of the plan

We need build the extension CSSx.ttl that extends the PPR-CSS ontology with the information and concepts that would be required for the production of the product. To accomodate the SMTs we need to extend the ontology with the related concepts. A related concept could be product consist of parts/subassemblies and a product has a manufacturer, a resource has interfaces with subclasses: SW, electrical and hardware. In the case of SW interfaces this would then later map to the AID SMT. But as you see the initial descriptions do not have any AAS related definitions. This comes later. 


## Next steps

NOTE: The next steps should not be the focus for now! The next steps should just be kept in mind while building the CSSx.ttl ontology.
The next steps would involve creating a mapping ontology that combines the CSSx.ttl ontology with the concept in AAS. So, this means relating concepts from the CSSx to submodels, submodelelementcollections, properties, references etc. This will actually consist of two ontologies: an AAS ontology that describes the metamodel and structures of the AAS and a mapping ontology that bridges the AAS elements like a submodel to a specific submodel like AID that then references a concept of a SW interface in the CSSx. 

## Mapping approach to use later (after CSSx is complete)

When the CSS + CSSx ontology is sufficiently complete, use a **bidirectional declarative mapping approach** inspired by the ETFA paper on mapping capability/skill ontology and AAS.

### Core principle

Do not try to force a single universal transformation format. Use two explicit one-way mappings:

- **AAS -> Ontology** using **RML** (JSON/XML sources -> RDF/OWL individuals and relations)
- **Ontology -> AAS** using **RDFex** (SPARQL-selected ontology elements -> JSON/XML AAS structures)

This follows the idea:

- f_A->O: m_AAS -> m_Onto
- f_O->A: m_Onto -> m_AAS

where both mappings are maintained declaratively and versioned.

### Practical rule format

- For **RML** rules:
    - use JSONPath iterators over submodel structures
    - map each relevant AAS element into ontology individuals/classes
    - map relation elements into object properties
    - map comments/descriptions/semanticId into ontology annotations or datatype properties

- For **RDFex** rules:
    - use SPARQL to select ontology elements to export
    - define JSONPath container targets in AAS JSON
    - use snippets to generate SMC/SME structures
    - preserve stable idShort generation strategy

### How to handle model differences

The mapping must be **semantic-first**, not shape-first.

- First compare model elements (Capability, Skill, Property, Constraints, Interfaces, Parameters, etc.)
- If structures differ, map by meaning rather than by identical nesting
- When AAS lacks detail, map to the closest representable construct and preserve intent via semanticId, references, qualifiers, or annotations
- Document non-isomorphic mappings explicitly (lossy or approximated transformations)

### Direction for CSSx-specific work

Unlike the CaSkMan approach that relies heavily on VDI process classifications, our CSSx extension should include clearer submodel-aligned concepts directly in the ontology so that mapping does not depend on external process standards as a fallback.

This means:

- model explicit submodel-relevant concepts in CSSx (BoM, BoP, Technical Data, Process Information, Required Capabilities, Policy, AID links, etc.)
- create mapping rules from these explicit CSSx concepts to AAS templates/submodel elements
- keep external standards (VDI/ECLASS/etc.) as optional semantic enrichments, not the only bridge

### Implementation timing

Do **not** prioritize full mapping implementation now.

Mapping rule development should start after:

1. CSSx concept coverage for Product/Process/Resource is stable
2. required object/datatype properties for submodel alignment are in place
3. naming and URI patterns are fixed enough to avoid rule churn

Then implement mappings incrementally and validate round-trip behavior on selected example assets.

## How to work

The instructions are very clear. Small incremental additions. So we build from submodel to concepts one-by-one in the following order.

1. Resource
    - Digital Nameplate (SMT)
    - BoM (SMT)
    - Skills (modded CC SMT)
    - Variables (Custom)
    - Parameters (Custom)
    - AssetInterfaceDescription (SMT)
2. Product
    - Digital Nameplate (SMT)
    - Technical Data (SMT)
    - BoM (SMT)
    - BoP (custom structure)
3. Process
    - ProcessInformation (custom)
    - requiredCapabilities (custom)
    - Policy (custom)

When making the relations for each submodel we'll together figure out the exact content for each submodel for the custom ones. And for the modified submodel templates we can also work together on the structure. The ones following the submodel templates should be straight forward to figure out what concepts are needed in the CSSx ontology.