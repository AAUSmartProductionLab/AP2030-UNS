#include "partial_state.h"

#include "../axioms.h"
#include "../globals.h"
#include "../global_operator.h"
#include "../utils/hash.h"

#include <algorithm>
#include <iostream>
#include <cassert>

void PartialState::_allocate() {
    vars = new int[g_variable_domain.size()];
    if (_varvals)
        delete _varvals;
    _varvals = 0;
}

void PartialState::_deallocate() {
    delete[] vars;
    if (_varvals)
        delete _varvals;
}

void PartialState::_copy_buffer_from_state(const PartialState &state) {
    for (unsigned i = 0; i < g_variable_domain.size(); i++)
        vars[i] = state.vars[i];
    if (_varvals)
        delete _varvals;
}

PartialState & PartialState::operator=(const PartialState &other) {
    if (this != &other) {
        _allocate();
        _copy_buffer_from_state(other);
    }
    return *this;
}

PartialState::PartialState() {
    _allocate();
    for (unsigned i = 0; i < g_variable_domain.size(); i++)
        vars[i] = -1;
}

PartialState::PartialState(std::vector<int> init_vals) {
    _allocate();
    for (unsigned i = 0; i < g_variable_domain.size(); i++)
        vars[i] = init_vals[i];
}

PartialState::PartialState(const StateInterface &state) {
    _allocate();
    for (unsigned i = 0; i < g_variable_domain.size(); i++)
        vars[i] = state[i];
}

PartialState::PartialState(const PartialState &state) {
    _allocate();
    _copy_buffer_from_state(state);
}

PartialState::PartialState(const State &state) {
    _allocate();
    for (unsigned i = 0; i < g_variable_domain.size(); i++)
        vars[i] = state.get_values()[i];
}


PartialState::~PartialState() {
    _deallocate();
}

int PartialState::size() const {
    int count = 0;
    for (unsigned i = 0; i < g_variable_domain.size(); i++) {
        if (vars[i] != -1)
            count++;
    }
    return count;
}

vector< pair<int,int> > * PartialState::varvals() {
    if (0 == _varvals) {
        _varvals = new vector< pair<int,int> >();
        for (int i = 0; i < (int) g_variable_domain.size(); i++)
            if (-1 != vars[i])
                _varvals->push_back(make_pair(i,vars[i]));
    }
    return _varvals;
}

PartialState * PartialState::progress(const GlobalOperator &op) {

    assert(!op.is_axiom());

    PartialState * next = new PartialState(*this);

    for (auto eff : op.get_all_effects()) {
        if (eff.does_fire(*this))
            (*next)[eff.var] = eff.val;
    }

    // HAZ: This is disabled since we cannot handle domains with axioms,
    //      leaving it in slows us down.
    //g_axiom_evaluator->evaluate(*this);

    return next;

}

PartialState * PartialState::regress(const GlobalOperator &op, PartialState *context) {

    assert(!op.is_axiom());
    assert(NULL != context);

    PartialState * prev = new PartialState(*this);

    // Remove all of the effect settings
    for (auto eff : op.get_all_effects()) {
        if (eff.does_fire(*context)) {

            bool inconsistent = (vars[eff.var] != -1) && (vars[eff.var] != eff.val);

            if (inconsistent) {
                cout << "\n\n !! Error: Inconsistent regression !!\n" << endl;
                eff.dump();
                cout << "\n" << eff.var << " / " << vars[eff.var] << " / " << eff.val << endl;
                dump_pddl();
                op.dump();
            }

            assert(!inconsistent);
            (*prev)[eff.var] = -1;
        }
    }

    // Assign the values from the context that are mentioned in conditions
    for (auto var : *(PRP.general.conditional_mask[op.nondet_index]))
        (*prev)[var] = (*context)[var];

    // Add all of the precondition conditions
    for (auto pre : op.get_preconditions())
        (*prev)[pre.var] = pre.val;

    // HAZ: This is disabled since we cannot handle domains with axioms,
    //      leaving it in slows us down.
    //g_axiom_evaluator->evaluate(*this);

    return prev;

}

bool PartialState::entails(const PartialState &other) {
    for (unsigned i = 0; i < g_variable_domain.size(); i++)
        if ((other[i] != -1) && (vars[i] != other[i]))
            return false;
    return true;
}

bool PartialState::consistent_with(const PartialState &other) {
    for (unsigned i = 0; i < g_variable_domain.size(); i++)
        if ((other[i] != -1) && (vars[i] != -1) && (vars[i] != other[i]))
            return false;
    return true;
}

void PartialState::combine_with(const PartialState &other) {
    if (_varvals)
        delete _varvals;
    for (unsigned i = 0; i < g_variable_domain.size(); i++) {
        assert((vars[i] == -1) || (other[i] == -1) || (vars[i] == other[i]));
        if (other[i] != -1)
            vars[i] = other[i];
    }
}

void PartialState::dump_pddl() const {
    if (PRP.logging.disable_state_dump) {
        cout << "  <disabled>" << endl;
        return;
    }
    for (unsigned i = 0; i < g_variable_domain.size(); i++) {
        if (-1 != vars[i]) {
            const string &fact_name = g_fact_names[i][vars[i]];
            if (fact_name != "<none of those>")
                cout << fact_name << endl;
            else
                cout << "[" << g_variable_name[i] << "] None of those." << endl;
        }
    }
}

void PartialState::dump_fdr() const {
    if (PRP.logging.disable_state_dump) {
        cout << "  <disabled>" << endl;
        return;
    }
    for (unsigned i = 0; i < g_variable_domain.size(); i++) {
        if (-1 != vars[i]) {
            cout << "  #" << i << " [" << g_variable_name[i] << "] -> "
                 << vars[i] << endl;
        }
    }
}

void PartialState::record_snapshot(ofstream &outfile, string indent) {
    outfile << indent << "\"" << this << "\": [" << endl;
    bool first = true;
    for (unsigned i = 0; i < g_variable_domain.size(); i++) {
        if (-1 != vars[i]) {
            if (first)
                first = false;
            else
                outfile << "," << endl;
            const string &fact_name = g_fact_names[i][vars[i]];
            if (fact_name != "<none of those>")
                outfile << indent << "  \"" << fact_name << "\"";
            else
                outfile << indent << "  \"[" << g_variable_name[i] << "] None of those.\"";
        }
    }
    outfile << endl << indent << "]";
}

bool PartialState::operator==(const PartialState &other) const {
    unsigned size = g_variable_domain.size();
    return ::equal(vars, vars + size, other.vars);
}

bool PartialState::operator<(const PartialState &other) const {
    unsigned size = g_variable_domain.size();
    return ::lexicographical_compare(vars, vars + size,
                                     other.vars, other.vars + size);
}

size_t PartialState::hash() const {
    return utils::hash_sequence(vars, g_variable_domain.size());
}
