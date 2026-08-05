"""
Extended Skills — Pydantic model extending CCI Skill with ExecutionModel.

The IDTA ControlComponentInstance template defines a Skill SMC with basic
fields (disabled, modes, parameters, errors, uses). This module extends it
with:
- execution_model: ExecutionModel (symbolic planning semantics)
- interface_reference: ReferenceElement pointing to the AID action

These extensions are read by the BT_Controller at runtime for state grounding
and by the operation delegation service for MQTT topic resolution.
"""

from __future__ import annotations

from typing import ClassVar, Dict, List, Optional

from pydantic import Field

from aas_pydantic import (
    SubmodelElement, SubmodelElementCollection, Qualifier,
    Property, ReferenceElement, ContainerValue,
)

from aas_pydantic.submodel_templates.control_component_instance import (
    Skill as _BaseSkill,
    SkillValues as _BaseSkillValues,
    Skills as _BaseSkills,
    Modes,
    Parameters,
    Errors,
    Uses,
)

from ..constants import (
    BASE_URL, CSSX
)


EXECUTION_MODEL = f"{BASE_URL}/ExectionModel"
EXEC_MODEL_REF_STEP = f"{BASE_URL}/execution/ModelRefStep/1/0"
EXEC_AAS_REF = f"{BASE_URL}/execution/AasRef/1/0"
EXEC_SUBMODEL_REF = f"{BASE_URL}/execution/SubmodelRef/1/0"
EXEC_ELEMENT_REF = f"{BASE_URL}/execution/ElementRef/1/0"
EXEC_PROPERTY_REF = f"{BASE_URL}/execution/PropertyRef/1/0"
EXEC_PARAM_KEY = f"{BASE_URL}/execution/ParameterKey/1/0"
EXEC_PARAM_SEMANTIC_ID = f"{BASE_URL}/execution/ParameterSemanticId/1/0"
EXEC_OPERATOR = f"{BASE_URL}/execution/Operator/1/0"
EXEC_WHEN_CONDITION = f"{BASE_URL}/execution/WhenCondition/1/0"

# Predicate condition (redesigned — Phase 5)
EXEC_PREDICATE = f"{CSSX}/Predicate"

# LogicTerms
EXEC_LOGIC_TERM = f"{BASE_URL}/LogicTerm"
EXEC_LOGIC_TERM_AND = f"{EXEC_LOGIC_TERM}/And"
EXEC_LOGIC_TERM_OR = f"{EXEC_LOGIC_TERM}/Or"
EXEC_LOGIC_TERM_WHILE = f"{EXEC_LOGIC_TERM}/While"
EXEC_LOGIC_TERM_ONE_OF = f"{EXEC_LOGIC_TERM}/OneOf"
EXEC_LOGIC_TERM_NOT = f"{EXEC_LOGIC_TERM}/Not"

# ArithmeticTerms
EXEC_ARITHMETIC_TERM = f"{BASE_URL}/ArithmeticTerms"
EXEC_ARITHMETIC_TERM_PLUS = f"{EXEC_ARITHMETIC_TERM}/Plus"
EXEC_ARITHMETIC_TERM_MINUS = f"{EXEC_ARITHMETIC_TERM}/Minus"
EXEC_ARITHMETIC_TERM_DIVIDE = f"{EXEC_ARITHMETIC_TERM}/Divide"
EXEC_ARITHMETIC_TERM_MULTIPLY = f"{EXEC_ARITHMETIC_TERM}/Multiply"


EXTENDED_SKILLS="{BASE_URL}/ControlComponent/Skills/2/0"
EXTENDED_SKILL="{BASE_URL}/ControlComponent/Skill/2/0"
EXTENDED_SKILL_INTERFACE_REF = f"{BASE_URL}/ControlComponent/Skill/1/0"


class ExtendedSkillValues(_BaseSkillValues):
    """Skill children + the execution-model/interface-reference extension."""
    interface_reference: ReferenceElement = ReferenceElement(
        semantic_id=EXTENDED_SKILL_INTERFACE_REF,
        description="Reference to the corresponding AID action interface for MQTT topic resolution.",
    )


class ExtendedSkill(_BaseSkill):
    semantic_id: str = EXTENDED_SKILL
    value: ExtendedSkillValues = ExtendedSkillValues()


class ExtendedSkills(_BaseSkills):
    """Dynamic map of extended skills offered by the component instance
    (name → ExtendedSkill)."""
    semantic_id: str = EXTENDED_SKILLS
    value: Dict[str, ExtendedSkill] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# Parameter references
# ═══════════════════════════════════════════════════════════════════════════════

class ExecParamModelRef(ReferenceElement):
    semantic_id: str = EXEC_MODEL_REF_STEP
    description: str = "The refereable to be used as a parameter within predicates"


class ExecutionModelParameter(ReferenceElement):
    """
    A parameter of the skill's execution model.

    Parameters are always reference elements pointing to either: 
    - semanticId-only: points to an ontology concept (ExternalReference)
    - modelRef: points to a specific AAS/SubmodelElement (ModelReference)
    """
    semantic_id: str = f"{EXECUTION_MODEL}/Parameter"
    description: str = "A parameter of the skill execution model (semantic concept or model reference)."

    # Cardinality OneToMany → list of model references
    model_ref: List[ExecParamModelRef] = []


# ═══════════════════════════════════════════════════════════════════════════════
# Term tree — conditions and effects
# ═══════════════════════════════════════════════════════════════════════════════

class PredicateCondition(SubmodelElementCollection):
    """
    An atomic predicate condition in the term tree.

    The SMC itself IS the predicate — its supplemental_semantic_ids carries
    the specific predicate URI (e.g., cssx:Operational), and its id_short
    gives it a human-readable display name.  Arguments are dynamic children
    in ``value`` keyed by position (\"0\", \"1\", ...) for proper ordering.

    Negation is represented by a Negated ConceptQualifier on the SMC.
    """
    semantic_id: str = EXEC_PREDICATE
    description: str = "Atomic predicate SMC.  supplemental_semantic_ids = specific predicate URI; value = positional arguments."
    supplemental_semantic_ids: List[str] = []
    qualifiers: List[Qualifier] = [
        Qualifier(
            type_="Negated",
            value="false",
            kind="ConceptQualifier",
        ),
    ]

    value: Dict[str, Property] = {}


class TermValues(ContainerValue):
    """Children of a Term node: operator + when-condition properties, an
    optional wrapped predicate, and dynamic nested term children."""
    operator: Property = Property(
        semantic_id=EXEC_OPERATOR,
        description="Logic operator: 'predicate', 'and', 'or', 'not', 'oneOf'.",
    )
    when_condition: Property = Property(
        semantic_id=EXEC_WHEN_CONDITION,
        description="FOND when-condition string (only for oneOf operator).",
    )
    predicate: Optional[PredicateCondition] = None
    terms: Dict[str, PredicateCondition | Term] = {}


class Term(SubmodelElementCollection):
    """
    Recursive term node — either atomic predicate or logic/FOND operator.

    For atomic predicates, this wraps a PredicateCondition.
    For logic operators (and, or, not), value.terms contain nested TermTrees.
    For FOND (oneOf), value.terms are wrapped with when-condition strings.
    """
    semantic_id: str = f"{CSSX}/Term"
    supplemental_semantic_ids: List[str] = []
    description: str = "A node in the condition/effect term tree (atomic predicate or logic operator)."

    # default_factory: TermValues references Term (recursive), so the default
    # must be built lazily — an eager ``= TermValues()`` would force schema
    # construction before Term exists.
    value: TermValues = Field(default_factory=TermValues)


class TermTree(Term):
    """A tree of terms — a collection of term nodes (atomic predicates or logic operators)."""
    semantic_id: str = f"{CSSX}/TermTree"
    description: str = "A tree of terms (atomic predicates or logic operators)."


# ═══════════════════════════════════════════════════════════════════════════════
# Condition and effect groups
# ═══════════════════════════════════════════════════════════════════════════════

class PreConditions(Term):
    """Preconditions that must hold before the skill can execute."""
    semantic_id: str = f"{CSSX}PreConditions"
    description: str = "Conditions that must be satisfied before skill execution."

class InvariantConditions(Term):
    """Conditions that must hold throughout skill execution."""
    semantic_id: str = f"{CSSX}InvariantConditions"
    description: str = "Conditions that must hold throughout skill execution (invariants)."

class PostConditions(Term):
    """Conditions that must hold after skill execution."""
    semantic_id: str = f"{CSSX}PostConditions"
    description: str = "Conditions that must be satisfied after skill execution."


class ConditionsValues(ContainerValue):
    """Condition groups of a skill (pre / invariant / post)."""
    pre_conditions: Optional[PreConditions] = None
    invariant_conditions: Optional[InvariantConditions] = None
    post_conditions: Optional[PostConditions] = None


class Conditions(SubmodelElementCollection):
    """All condition groups for the skill."""
    semantic_id: str = f"{CSSX}SkillConditions"
    description: str = "Condition groups (pre, invariant, post) for skill execution."

    value: ConditionsValues = ConditionsValues()


class StartEffectsValues(ContainerValue):
    """Effect terms applied at skill start."""
    terms: List[TermTree] = []


class StartEffects(SubmodelElementCollection):
    """Effects applied at the start of skill execution."""
    semantic_id: str = f"{CSSX}StartEffects"
    description: str = "Effects applied when the skill starts."

    value: StartEffectsValues = StartEffectsValues()


class ContinuousEffectsValues(ContainerValue):
    """Effect terms applied continuously during skill execution."""
    terms: List[TermTree] = []


class ContinuousEffects(SubmodelElementCollection):
    """Effects applied continuously during skill execution."""
    semantic_id: str = f"{CSSX}ContinuousEffects"
    description: str = "Effects applied continuously during skill execution."

    value: ContinuousEffectsValues = ContinuousEffectsValues()


class EndEffectsValues(ContainerValue):
    """Effect terms applied at skill end."""
    terms: List[TermTree] = []


class EndEffects(SubmodelElementCollection):
    """Effects applied at the end of skill execution."""
    semantic_id: str = f"{CSSX}EndEffects"
    description: str = "Effects applied when the skill completes."

    value: EndEffectsValues = EndEffectsValues()


class EffectsValues(ContainerValue):
    """Effect groups of a skill (start / continuous / end)."""
    start_effects: Optional[StartEffects] = None
    continuous_effects: Optional[ContinuousEffects] = None
    end_effects: Optional[EndEffects] = None


class Effects(SubmodelElementCollection):
    """All effect groups for the skill."""
    semantic_id: str = f"{CSSX}SkillEffects"
    description: str = "Effect groups (start, continuous, end) for skill execution."

    value: EffectsValues = EffectsValues()


# ═══════════════════════════════════════════════════════════════════════════════
# Top-level ExecutionModel
# ═══════════════════════════════════════════════════════════════════════════════

class ExecutionModelValues(ContainerValue):
    """Children of the skill execution model: parameters, conditions, effects."""
    parameters: List[ExecutionModelParameter] = []
    conditions: Optional[Conditions] = None
    effects: Optional[Effects] = None


class ExecutionModel(SubmodelElementCollection):
    """
    Symbolic execution model for a skill.

    Encodes the planning-level semantics: what parameters the skill binds,
    what conditions must hold, and what effects it produces. This is the
    runtime contract between the Planner and the BT_Controller.

    The BT_Controller reads this model at execution time to:
    1. Ground effect terms against parameter bindings
    2. Apply symbolic state updates via the knowledge graph
    3. Branch on FOND (oneOf) outcomes
    """
    semantic_id: str = f"{CSSX}ExecutionModel"
    description: str = (
        "Symbolic execution model: parameters, conditions, and effects. "
        "Read by the BT_Controller at runtime for state grounding."
    )

    value: ExecutionModelValues = ExecutionModelValues()


# Ensure forward references are resolved (Pydantic v2)
PredicateCondition.model_rebuild()
TermValues.model_rebuild()
Term.model_rebuild()
TermTree.model_rebuild()
ConditionsValues.model_rebuild()
Conditions.model_rebuild()
StartEffectsValues.model_rebuild()
ContinuousEffectsValues.model_rebuild()
EndEffectsValues.model_rebuild()
EffectsValues.model_rebuild()
Effects.model_rebuild()
ExecutionModelValues.model_rebuild()
ExecutionModel.model_rebuild()


# Ensure forward references are resolved (Pydantic v2)
ExtendedSkill.model_rebuild()
ExtendedSkills.model_rebuild()
