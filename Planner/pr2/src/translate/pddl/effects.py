from __future__ import print_function
from itertools import product

from . import conditions

def cartesian_product(*sequences):
    # TODO: Also exists in tools.py outside the pddl package (defined slightly
    #       differently). Not good. Need proper import paths.
    if not sequences:
        yield ()
    else:
        for tup in cartesian_product(*sequences[1:]):
            for item in sequences[0]:
                yield (item,) + tup


class Effect(object):
    def __init__(self, parameters, condition, literal):
        self.parameters = parameters
        self.condition = condition
        self.literal = literal
    def __eq__(self, other):
        return (self.__class__ is other.__class__ and
                self.parameters == other.parameters and
                self.condition == other.condition and
                self.literal == other.literal)
    def dump(self):
        indent = "  "
        if self.parameters:
            print("%sforall %s" % (indent, ", ".join(map(str, self.parameters))))
            indent += "  "
        if self.condition != conditions.Truth():
            print("%sif" % indent)
            self.condition.dump(indent + "  ")
            print("%sthen" % indent)
            indent += "  "
        print("%s%s" % (indent, self.literal))
    def copy(self):
        return Effect(self.parameters, self.condition, self.literal)
    def uniquify_variables(self, type_map):
        renamings = {}
        self.parameters = [par.uniquify_name(type_map, renamings)
                           for par in self.parameters]
        self.condition = self.condition.uniquify_variables(type_map, renamings)
        self.literal = self.literal.rename_variables(renamings)
    def instantiate(self, var_mapping, init_facts, fluent_facts,
                    objects_by_type, result):
        if self.parameters:
            var_mapping = var_mapping.copy() # Will modify this.
            object_lists = [objects_by_type.get(par.type_name, [])
                            for par in self.parameters]
            for object_tuple in cartesian_product(*object_lists):
                for (par, obj) in zip(self.parameters, object_tuple):
                    var_mapping[par.name] = obj
                self._instantiate(var_mapping, init_facts, fluent_facts, result)
        else:
            self._instantiate(var_mapping, init_facts, fluent_facts, result)
    def _instantiate(self, var_mapping, init_facts, fluent_facts, result):
        condition = []
        try:
            self.condition.instantiate(var_mapping, init_facts, fluent_facts, condition)
        except conditions.Impossible:
            return
        effects = []
        self.literal.instantiate(var_mapping, init_facts, fluent_facts, effects)
        assert len(effects) <= 1
        if effects:
            result.append((condition, effects[0]))
    def relaxed(self):
        if self.literal.negated:
            return None
        else:
            return Effect(self.parameters, self.condition.relaxed(), self.literal)
    def simplified(self):
        return Effect(self.parameters, self.condition.simplified(), self.literal)


class ConditionalEffect(object):
    def __init__(self, condition, effect):
        if isinstance(effect, ConditionalEffect):
            self.condition = conditions.Conjunction([condition, effect.condition])
            self.effect = effect.effect
        else:
            self.condition = condition
            self.effect = effect
    def dump(self, indent="  "):
        print("%sif" % (indent))
        self.condition.dump(indent + "  ")
        print("%sthen" % (indent))
        self.effect.dump(indent + "  ")
    def normalize(self, objmap):
        norm_effect = self.effect.normalize(objmap)
        if isinstance(norm_effect, ConjunctiveEffect):
            new_effects = []
            for effect in norm_effect.effects:
                assert isinstance(effect, SimpleEffect) or isinstance(effect, ConditionalEffect)
                new_effects.append(ConditionalEffect(self.condition, effect))
            return ConjunctiveEffect(new_effects)
        elif isinstance(norm_effect, UniversalEffect):
            child = norm_effect.effect
            cond_effect = ConditionalEffect(self.condition, child)
            return UniversalEffect(norm_effect.parameters, cond_effect)
        elif isinstance(norm_effect, OneofEffect):
            return OneofEffect([ConditionalEffect(self.condition, eff) for eff in norm_effect.effects])
        else:
            return ConditionalEffect(self.condition, norm_effect)
    def extract_cost(self):
        return None, self
    def instantiate(self, varmapping):
        return ConditionalEffect(self.condition.clone_and_instantiate(varmapping),
                                 self.effect.instantiate(varmapping))

class UniversalEffect(object):
    def __init__(self, parameters, effect):
        if isinstance(effect, UniversalEffect):
            self.parameters = parameters + effect.parameters
            self.effect = effect.effect
        else:
            self.parameters = parameters
            self.effect = effect
    def dump(self, indent="  "):
        print("%sforall %s" % (indent, ", ".join(map(str, self.parameters))))
        self.effect.dump(indent + "  ")
    def normalize(self, objmap):

        # Normalize recursively
        norm_effect = self.effect.normalize(objmap)

        # Get the full list of possible parameter instantiations
        param_options = [objmap[par.type_name] for par in self.parameters]
        param_options = product(*param_options)

        # Instantiate the effect for each parameter instantiation
        conjuncts = []
        for param_option in param_options:
            setting = dict(zip(self.parameters, param_option))
            setting = {par.name: obj.name for par, obj in setting.items()}
            conjuncts.append(norm_effect.instantiate(setting))
        new_effect = ConjunctiveEffect(conjuncts)
        norm_new_effect = new_effect.normalize(objmap)
        return norm_new_effect

    def old_normalize(self, objmap):
        norm_effect = self.effect.normalize(objmap)
        if isinstance(norm_effect, ConjunctiveEffect):
            new_effects = []
            for effect in norm_effect.effects:
                assert isinstance(effect, SimpleEffect) or isinstance(effect, ConditionalEffect)\
                       or isinstance(effect, UniversalEffect)
                new_effects.append(UniversalEffect(self.parameters, effect))
            return ConjunctiveEffect(new_effects)
        elif isinstance(norm_effect, OneofEffect):
            return OneofEffect([UniversalEffect(self.parameters, eff) for eff in norm_effect.effects])
        else:
            return UniversalEffect(self.parameters, norm_effect)
    def extract_cost(self):
        return None, self
    def instantiate(self, varmapping):
        return UniversalEffect(self.parameters, self.effect.instantiate(varmapping))

class ConjunctiveEffect(object):
    def __init__(self, effects):
        flattened_effects = []
        label = ""
        for effect in effects:
            if 'outcome_label' in dir(effect):
                label += "__" + effect.outcome_label
            if isinstance(effect, ConjunctiveEffect):
                flattened_effects += effect.effects
            else:
                flattened_effects.append(effect)
        self.effects = flattened_effects
        if label != "":
            self.outcome_label = label[2:]
    def dump(self, indent="  "):
        print("%sand" % (indent))
        for eff in self.effects:
            eff.dump(indent + "  ")
    def normalize(self, objmap):
        if not self.effects:
            return self
        norm_effects = [e.normalize(objmap) for e in self.effects]
        new_effects = []
        labeled = False
        for effect in norm_effects:
            if isinstance(effect, LabeledOneofEffect):
                labeled = True
            # We do this for either Oneof or LabeledOneof
            if isinstance(effect, OneofEffect):
                new_effects.append(effect.effects)
            else:
                new_effects.append([effect])
        if 1 == len(new_effects):
            return norm_effects[0]
        if 1 == max([len(e) for e in new_effects]):
            return ConjunctiveEffect(norm_effects)
        else:
            cost_eff = None
            for neweff in new_effects:
                if isinstance(neweff[0], CostEffect):
                    assert cost_eff is None
                    cost_eff = neweff[0]
            new_effects = [e for e in new_effects if not isinstance(e[0], CostEffect)]

            oneeff = None
            if labeled:
                outcomes = [LabeledOutcomeEffect(e.outcome_label, e) for e in map(ConjunctiveEffect, product(*new_effects))]
                oneeff = LabeledOneofEffect(False, outcomes).normalize(objmap)
            else:
                oneeff = OneofEffect(map(ConjunctiveEffect, product(*new_effects)))
            if cost_eff is not None:
                return ConjunctiveEffect([cost_eff, oneeff])
            else:
                return oneeff
    def extract_cost(self):
        new_effects = []
        cost_effect = None
        for effect in self.effects:
            if isinstance(effect, CostEffect):
                cost_effect = effect
            else:
                new_effects.append(effect)
        if len(new_effects) == 1:
            return cost_effect, new_effects[0]
        else:
            return cost_effect, ConjunctiveEffect(new_effects)
    def instantiate(self, varmapping):
        return ConjunctiveEffect([eff.instantiate(varmapping) for eff in self.effects])

class OneofEffect(object):
    def __init__(self, effects):
        self.effect_type = "oneof"
        self.class_type = OneofEffect
        flattened_effects = []
        for effect in effects:
            if isinstance(effect, OneofEffect):
                flattened_effects += effect.effects
            else:
                flattened_effects.append(effect)
        self.effects = flattened_effects
    def dump_effect(self, eff, indent):
        eff.dump(indent + "  ")
    def dump(self, indent="  "):
        print("%s%s" % (indent, self.effect_type))
        for i, eff in enumerate(self.effects):
            print(" %s%d:" % (indent, i+1))
            self.dump_effect(eff, indent)
    def normalize(self, objmap):
        norm_effects = [e.normalize(objmap) for e in self.effects]
        new_effects = []
        for effect in norm_effects:
            if isinstance(effect, OneofEffect):
                new_effects += effect.effects
            else:
                new_effects.append(effect)
        return OneofEffect(new_effects)
    def extract_cost(self):
        new_effects = []
        cost_effect = None
        for effect in self.effects:
            new_cost_effect, rest_effect = effect.extract_cost()
            new_effects.append(rest_effect)
            if new_cost_effect:
                assert cost_effect is None
                cost_effect = new_cost_effect
        return cost_effect, OneofEffect(new_effects)
    def instantiate(self, varmapping):
        return OneofEffect([eff.instantiate(varmapping) for eff in self.effects])

class LabeledOutcomeEffect(object):
    def __init__(self, outcome_label, effect):
        self.effect = effect
        self.outcome_label = outcome_label
    def dump(self, indent="  "):
        print("%soutcome = %s" % (indent, self.outcome_label))
        self.effect.dump(indent + "  ")
    def normalize(self, objmap):
        norm_effect = self.effect.normalize(objmap)
        return LabeledOutcomeEffect(self.outcome_label, norm_effect)
    def extract_cost(self):
        cost_effect, rest_effect = self.effect.extract_cost()
        return cost_effect, LabeledOutcomeEffect(self.outcome_label, rest_effect)
    def instantiate(self, varmapping):
        return LabeledOutcomeEffect(self.outcome_label, self.effect.instantiate(varmapping))

class LabeledOneofEffect(OneofEffect):
    def __init__(self, label, effects):
        self.label = label
        self.effect_type = "labeled-oneof"
        self.class_type = LabeledOneofEffect
        self.effects = effects
    def dump_effect(self, eff, indent):
        print("%s [%s]" % (indent, eff.outcome_label))
        eff.dump(indent + "  ")
    def normalize(self, objmap):
        norm_effects = []
        for e in self.effects:
            norm_effects.append(e.normalize(objmap))
            if self.label:
                norm_effects[-1].outcome_label = "%s-EQ-%s" % (self.label, e.outcome_label)
            else:
                norm_effects[-1].outcome_label = e.outcome_label
        new_effects = []
        for effect in norm_effects:
            assert isinstance(effect, LabeledOutcomeEffect)
            if isinstance(effect.effect, LabeledOneofEffect):
                for e in effect.effect.effects:
                    e.outcome_label = "%s__%s" % (effect.outcome_label, e.outcome_label)
                new_effects += effect.effect.effects
            else:
                new_effects.append(effect)
        return LabeledOneofEffect(self.label, new_effects)
    def extract_cost(self):
        new_effects = []
        cost_effect = None
        for effect in self.effects:
            new_cost_effect, rest_effect = effect.extract_cost()
            new_effects.append(rest_effect)
            new_effects[-1].outcome_label = rest_effect.outcome_label
            if new_cost_effect:
                assert cost_effect is None
                cost_effect = new_cost_effect
        return cost_effect, LabeledOneofEffect(self.label, new_effects)
    def instantiate(self, varmapping):
        return LabeledOneofEffect(self.label, [eff.instantiate(varmapping) for eff in self.effects])

class SimpleEffect(object):
    def __init__(self, effect):
        self.effect = effect
    def dump(self, indent="  "):
        print("%s%s" % (indent, self.effect))
    def normalize(self, objmap):
        return self
    def extract_cost(self):
        return None, self
    def instantiate(self, varmapping):
        return SimpleEffect(self.effect.clone_and_instantiate(varmapping))

class CostEffect(object):
    def __init__(self, effect):
        self.effect = effect
    def dump(self, indent="  "):
        print("%s%s" % (indent, self.effect))
    def normalize(self, objmap):
        return self
    def extract_cost(self):
        return self, None # this would only happen if an action has no effect apart from the cost effect
    def instantiate(self, varmapping):
        return self
