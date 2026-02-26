#include "deadend.h"

#include "partial_state.h"
#include "regression.h"

#include "../global_operator.h"



void FSAP::dump() const {
    cout << "FSAP:" << endl;
    cout << "Operator: " << g_operators[op_index].get_nondet_name() << endl;
    cout << " -{ State }-" << endl;
    state->dump_pddl();
    cout << "" << endl;
}

void Deadend::dump() const {
    cout << "Deadend:" << endl;
    cout << " -{ State }-" << endl;
    state->dump_pddl();
    cout << "" << endl;
}

bool FSAP::operator< (const FSAP& other) const {
    if (is_active != other.is_active)
        return is_active;
    else
        return op_index > other.op_index;
}

string FSAP::get_name() {
    return (*(PRP.general.nondet_mapping[op_index]))[0]->get_nondet_name();
}

int FSAP::get_index() {
    return op_index;
}


bool is_deadend(PartialState &state) {
    PRP.deadend.reachability_heuristic->reset();
    return (-1 == ((fsap_penalized_ff_heuristic::FSAPPenalizedFFHeuristic *)PRP.deadend.reachability_heuristic)->compute_add_and_ff(state));
}

bool is_forbidden(PartialState &state, const GlobalOperator *op) {
    vector<OperatorID> ops;
    g_successor_generator->generate_applicable_ops(state, ops);
    return op->is_possibly_applicable(state) && (find(ops.begin(), ops.end(), OperatorID(get_op_index_hacked(op))) == ops.end());
}


bool generalize_deadend(PartialState &state) {

    // If the whole state isn't recognized as a deadend, then don't bother
    //  looking for a subset of the state
    if (!is_deadend(state))
        return false;

    // We go through each variable and unset it, checking if the relaxed
    //  reachability is violated.
    for (unsigned i = 0; i < g_variable_name.size(); i++) {

        int old_val = state[i];
        state[i] = -1;

        // If relaxing variable i causes us to reach the goal, keep it
        if (!is_deadend(state))
            state[i] = old_val;
    }

    if (PRP.logging.deadends) {
        cout << "Found relaxed deadend:" << endl;
        state.dump_pddl();
    }

    return true;
}

void update_deadends(vector< DeadendTuple* > &failed_states) {

    list<PolicyItem *> fsaps;
    list<PolicyItem *> deadends;

    PartialState * dummy_state = new PartialState();

    for (auto fs : failed_states) {

        // Generalize the deadend if need be
        PartialState * failed_state = fs->de_state;
        PartialState * failed_state_prev = fs->prev_state;
        const GlobalOperator * prev_op = fs->prev_op;

        // Add the failed state to our list of deadends (no op_index means
        //  that we are just using this FSAP as a deadend).
        deadends.push_back(new Deadend(new PartialState(*failed_state)));

        // HAZ: Only do the forbidden state-action computation when
        //  the non-deterministic action doesn't have any associated
        //  conditional effects. This is ensured by the construction
        //  of the g_regressable_ops data structure.

        // Get the regressable operators for the given state.
        vector<PolicyItem *> reg_items;
        PRP.general.regressable_ops->generate_consistent_items(*failed_state,
                                                               reg_items,
                                                               PRP.deadend.regress_trigger_only);

        // For each operator, create a new deadend avoidance pair
        for (auto item : reg_items) {

            RegressableOperator *ro = (RegressableOperator*)item;

            fsaps.push_back(new FSAP(failed_state->regress(*(ro->op), dummy_state),
                                     ro->op->nondet_index));

        }

        ////////////////////////////////////////////

        // Check to see if we have any consistent "all-fire" operators
        /*
        reg_items.clear();
        PRP.general.regressable_cond_ops->generate_consistent_items(*failed_state,
                                                                    reg_items,
                                                                    PRP.deadend.regress_trigger_only);

        // For each operator, create a new deadend avoidance pair
        for (auto item : reg_items) {

            RegressableOperator *ro = (RegressableOperator*)item;

            fsaps.push_back(new FSAP(failed_state->regress(*(ro->op), ro->op->all_fire_context),
                                     ro->op->nondet_index));
        }
        */

        ////////////////////////////////////////////

        // If we have a specified previous state and action, use that to
        //  build a forbidden state-action pair
        if (NULL != failed_state_prev) {
            fsaps.push_back(new FSAP(
                    failed_state->regress(*prev_op, failed_state_prev),
                    prev_op->nondet_index));
        }
    }

    delete dummy_state;

    if (PRP.logging.deadends) {
        cout << "DEADENDS(" << PRP.logging.id() << "): Adding the following new FSAPS:" << endl;
        for (auto fsap : fsaps)
            fsap->dump();
    }

    // Add a pointer from the operator to the newly created fsaps
    for (auto fsap : fsaps)
        PRP.deadend.nondetop2fsaps[((FSAP*)fsap)->op_index]->push_back((FSAP*)fsap);

    PRP.deadend.policy->update_policy(fsaps);
    PRP.deadend.states->update_policy(deadends);
}


void DeadendAwareSuccessorGenerator::generate_applicable_ops(const State &, vector<OperatorProxy> &) {

    cout << "!!ERROR!!" << endl << " - Using a deprecated successor generator call with State argument instead of StateInterface." << endl;
    assert(false);

    /*
    PartialState temp = PartialState();
    for (size_t i = 0; i < _curr.size(); ++i)
        temp[i] =  _curr.get_values()[i];
    vector<const GlobalOperator *> ops;
    generate_applicable_ops(temp, ops);
    */
}

void DeadendAwareSuccessorGenerator::generate_applicable_ops(const StateInterface &_curr, vector<OperatorID> &ops) {
    if (PRP.deadend.enabled && PRP.deadend.policy) {

        PartialState curr = PartialState(_curr);

        vector<PolicyItem *> reg_items;
        vector<OperatorID> orig_ops;
        map<int, PolicyItem *> fsap_map;

        g_successor_generator_orig->generate_applicable_ops(_curr, orig_ops);
        PRP.deadend.policy->generate_entailed_items(curr, reg_items);

        set<int> forbidden;
        for (auto item : reg_items) {

            int index = ((FSAP*)item)->op_index;

            forbidden.insert(index);

            if ((fsap_map.find(index) == fsap_map.end()) ||
                (item->state->size() < fsap_map[index]->state->size()))
                    fsap_map[index] = item;
        }

        vector<int> ruled_out;
        for (auto opid : orig_ops) {
            if (0 == forbidden.count(g_operators[opid.get_index()].nondet_index))
                ops.push_back(opid);
            else if (PRP.deadend.combine)
                ruled_out.push_back(g_operators[opid.get_index()].nondet_index);
        }

        // Add this state as a deadend if we have ruled out everything
        if (!PRP.weaksearch.limit_states && PRP.deadend.record_online &&
             PRP.deadend.combine && (orig_ops.size() > 0) && ops.empty()) {

            // Combind all of the FSAPs
            PartialState *newDE = new PartialState();
            for (unsigned i = 0; i < ruled_out.size(); i++) {
                newDE->combine_with(*(((FSAP*)(fsap_map[ruled_out[i]]))->state));
            }

            // Also rule out all of the unapplicable actions
            for (auto & op : g_operators) {
                if (0 == forbidden.count(op.nondet_index)) {
                    if (op.is_possibly_applicable(*newDE)) {
                        assert (!(op.is_possibly_applicable(curr)));
                        int conflict_var = op.compute_conflict_var(curr);
                        assert (conflict_var != -1);
                        assert ((*newDE)[conflict_var] == -1);
                        (*newDE)[conflict_var] = curr[conflict_var];
                    }
                }
            }

            PRP.deadend.combination_count++;

            vector<DeadendTuple *> failed_states;
            failed_states.push_back(new DeadendTuple(newDE, NULL, NULL));
            update_deadends(failed_states);
        }

    } else {

        g_successor_generator_orig->generate_applicable_ops(_curr, ops);

    }

    return;
}
