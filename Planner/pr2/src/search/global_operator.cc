#include "global_operator.h"

#include "globals.h"

#include "utils/collections.h"
#include "utils/system.h"

#include <algorithm>
#include <cassert>
#include <string>
#include <iostream>

using namespace std;
using utils::ExitCode;


static void check_fact(int var, int val) {
    if (!utils::in_bounds(var, g_variable_domain)) {
        cerr << "Invalid variable id: " << var << endl;
        utils::exit_with(ExitCode::INPUT_ERROR);
    }
    if (val < 0 || val >= g_variable_domain[var]) {
        cerr << "Invalid value for variable " << var << ": " << val << endl;
        utils::exit_with(ExitCode::INPUT_ERROR);
    }
}

GlobalCondition::GlobalCondition(istream &in) {
    in >> var >> val;
    check_fact(var, val);
}

GlobalCondition::GlobalCondition(int variable, int value)
    : var(variable),
      val(value) {
    check_fact(var, val);
}

// TODO if the input file format has been changed, we would need something like this
// Effect::Effect(istream &in) {
//    int cond_count;
//    in >> cond_count;
//    for (int i = 0; i < cond_count; ++i)
//        cond.push_back(Condition(in));
//    in >> var >> post;
//}

GlobalEffect::GlobalEffect(int variable, int value, const vector<GlobalCondition> &conds)
    : var(variable),
      val(value),
      conditions(conds) {
    check_fact(var, val);
}

void GlobalOperator::read_pre_post(istream &in) {
    int cond_count, var, pre, post;
    in >> cond_count;
    vector<GlobalCondition> conditions;
    conditions.reserve(cond_count);
    for (int i = 0; i < cond_count; ++i)
        conditions.push_back(GlobalCondition(in));
    in >> var >> pre >> post;
    if (pre != -1)
        check_fact(var, pre);
    check_fact(var, post);
    if (pre != -1)
        preconditions.push_back(GlobalCondition(var, pre));
    effects.push_back(GlobalEffect(var, post, conditions));
}

GlobalOperator::GlobalOperator(istream &in, bool axiom) {
    nondet_index = -1;

    is_an_axiom = axiom;
    if (!is_an_axiom) {
        check_magic(in, "begin_operator");
        in >> ws;
        getline(in, name);
        int count;
        in >> count;
        for (int i = 0; i < count; ++i)
            preconditions.push_back(GlobalCondition(in));
        in >> count;
        for (int i = 0; i < count; ++i)
            read_pre_post(in);

        int op_cost;
        in >> op_cost;
        cost = g_use_metric ? op_cost : 1;

        g_min_action_cost = min(g_min_action_cost, cost);
        g_max_action_cost = max(g_max_action_cost, cost);

        check_magic(in, "end_operator");

        // The nondet name is the original name of the non-deterministic action
        if ((name.length()-1) == name.find(" "))
            name = name.substr(0, name.length()-1);
        if (name.find("_DETDUP") == string::npos) {
            nondet_name = name;
        } else {
            nondet_name = name.substr(0, name.find("_DETDUP"));
            if (name.find(" ") != string::npos)
                nondet_name += name.substr(name.find(" "), string::npos);
        }

    } else {
        name = "<axiom>";
        cost = 0;
        check_magic(in, "begin_rule");
        read_pre_post(in);
        check_magic(in, "end_rule");
    }

    // Create the set of all effects (which include prevails)
    std::set<int> seen;
    vector<GlobalCondition> no_conditions;
    for (auto & eff : effects) {
        all_effects.push_back(GlobalEffect(eff.var, eff.val, eff.conditions));
        seen.insert(eff.var);
    }

    for (auto & pre : preconditions) {
        if (0 == seen.count(pre.var)) {
            all_effects.push_back(GlobalEffect(pre.var, pre.val, no_conditions));
            seen.insert(pre.var);
        }
    }


    /* ********************
     *
     *  !!WARNING!!
     *
     *   This operation doesn't check for inconsistencies
     *    because we assume that was done to construct the
     *    g_regressable_cond_ops data structure (see the
     *    generate_regressable_ops function).
     *
     * ************* */

    // Deal with the all-fire context (essentially every conditional head
    //  and precondition rolled into one state)
    all_fire_context = new PartialState();

    for (auto & eff : all_effects)
        for (auto & cond : eff.conditions)
            (*all_fire_context)[cond.var] = cond.val;

    for (auto & pre : preconditions)
        (*all_fire_context)[pre.var] = pre.val;


}

void GlobalCondition::dump() const {
    const string &fact_name = g_fact_names[var][val];
    if (fact_name != "<none of those>")
        cout << fact_name;
    else
        cout << "[" << g_variable_name[var] << "] None of those.";
}

void GlobalEffect::dump() const {

    cout << g_variable_name[var] << ":= (" << val << ") " << g_fact_names[var][val];
    if (!conditions.empty()) {
        cout << " if";
        for (size_t i = 0; i < conditions.size(); ++i) {
            cout << " ";
            conditions[i].dump();
        }
    }
}

void GlobalOperator::dump() const {
    cout << name << " (" << nondet_name << "):";
    for (size_t i = 0; i < preconditions.size(); ++i) {
        cout << " [";
        preconditions[i].dump();
        cout << "]";
    }
    for (auto eff : all_effects) {
        cout << " [";
        eff.dump();
        cout << "]";
    }
    cout << endl;
}

int get_op_index_hacked(const GlobalOperator *op) {
    int op_index = op - &*g_operators.begin();
    assert(op_index >= 0 && op_index < static_cast<int>(g_operators.size()));
    return op_index;
}
