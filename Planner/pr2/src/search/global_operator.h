#ifndef GLOBAL_OPERATOR_H
#define GLOBAL_OPERATOR_H

#include "global_state.h"

#include "prp/partial_state.h"

#include <iostream>
#include <string>
#include <vector>
#include <set>

class PartialState;

struct GlobalCondition {
    int var;
    int val;
    explicit GlobalCondition(std::istream &in);
    GlobalCondition(int variable, int value);

    bool is_applicable(const StateInterface &state) const {
        assert(var >= 0 && (unsigned)var < g_variable_name.size());
        assert(val >= 0 && val < g_variable_domain[var]);

        if (-1 == val) {
            std::cout << "\n\nError: You probably tried progressing a partial state that has underspecified variables for a precondition or conditional effect.\n" << std::endl;
            exit(1);
        }

        return state[var] == val;
    }

    bool is_possibly_applicable(const StateInterface &state) const {
        return ((state[var] == -1) || (state[var] == val));
    }

    bool operator==(const GlobalCondition &other) const {
        return var == other.var && val == other.val;
    }

    bool operator!=(const GlobalCondition &other) const {
        return !(*this == other);
    }

    void dump() const;
};

struct GlobalEffect {
    int var;
    int val;
    std::vector<GlobalCondition> conditions;
    explicit GlobalEffect(std::istream &in);
    GlobalEffect(int variable, int value, const std::vector<GlobalCondition> &conds);

    bool does_fire(const StateInterface &state) const {
        for (size_t i = 0; i < conditions.size(); ++i)
            if (!conditions[i].is_applicable(state))
                return false;
        return true;
    }

    bool has_conditional_effect() const {
        return conditions.size() > 0;
    }

    void dump() const;
};

class GlobalOperator {
    bool is_an_axiom;
    std::vector<GlobalCondition> preconditions;
    std::vector<GlobalEffect> effects;
    std::vector<GlobalEffect> all_effects;
    std::string name;
    std::string nondet_name;
    int cost;

    void read_pre_post(std::istream &in);
public:
    explicit GlobalOperator(std::istream &in, bool is_axiom);
    void dump() const;
    const std::string &get_name() const {return name; }
    const std::string &get_nondet_name() const {return nondet_name; }

    int nondet_index;
    int nondet_outcome;
    PartialState * all_fire_context;

    bool is_axiom() const {return is_an_axiom; }

    const std::vector<GlobalCondition> &get_preconditions() const {return preconditions; }
    const std::vector<GlobalEffect> &get_effects() const {return effects; }
    const std::vector<GlobalEffect> &get_all_effects() const {return all_effects; }

    bool is_applicable(const StateInterface &state) const {
        for (size_t i = 0; i < preconditions.size(); ++i)
            if (!preconditions[i].is_applicable(state))
                return false;
        return true;
    }

    bool is_possibly_applicable(const StateInterface &state) const {
        for (auto &pre : preconditions)
            if (!pre.is_possibly_applicable(state))
                return false;
        return true;
    }

    int compute_conflict_var(const StateInterface &state) const {
        for (auto &pre : preconditions) {
            if (!pre.is_possibly_applicable(state))
                return pre.var;
        }
        return -1;
    }

    bool has_conditional_effect() const {
        for (auto &eff : effects)
            if (eff.has_conditional_effect())
                return true;
        return false;
    }

    int get_cost() const {return cost; }
};

extern int get_op_index_hacked(const GlobalOperator *op);

#endif
