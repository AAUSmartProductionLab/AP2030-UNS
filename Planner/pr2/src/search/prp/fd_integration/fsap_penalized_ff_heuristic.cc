#include "fsap_penalized_ff_heuristic.h"

#include "../../global_state.h"
#include "../../option_parser.h"
#include "../../plugin.h"

#include "../task_utils/task_properties.h"

#include "../prp.h"

#include <cassert>
#include <vector>

using namespace std;

namespace fsap_penalized_ff_heuristic {
// construction and destruction
FSAPPenalizedFFHeuristic::FSAPPenalizedFFHeuristic(const Options &opts)
    : RelaxationHeuristic(opts, false),
      did_write_overflow_warning(false),
      relaxed_plan(task_proxy.get_operators().size(), false) {
    if (PRP.logging.verbose)
        cout << "Initializing FSAP aware FF heuristic..." << endl;
}

FSAPPenalizedFFHeuristic::~FSAPPenalizedFFHeuristic() {
}

void FSAPPenalizedFFHeuristic::write_overflow_warning() {
    if (!did_write_overflow_warning) {
        // FDTODO: Should have a planner-wide warning mechanism to handle
        // things like this.
        cout << "WARNING: overflow on h^add! Costs clamped to "
             << MAX_COST_VALUE << endl;
        cerr << "WARNING: overflow on h^add! Costs clamped to "
             << MAX_COST_VALUE << endl;
        did_write_overflow_warning = true;
    }
}

void FSAPPenalizedFFHeuristic::reset() {
    // Turn the old goals off
    for (auto prop : goal_propositions)
        prop->is_goal = false;
    goal_propositions.clear();

    // Turn the new goals on
    for (auto varval : g_goal) {
        Proposition * prop = get_proposition(varval.first, varval.second);
        prop->is_goal = true;
        goal_propositions.push_back(prop);
    }
}

// heuristic computation
void FSAPPenalizedFFHeuristic::setup_exploration_queue() {
    queue.clear();
    seen_fsaps.clear();

    for (size_t var = 0; var < propositions.size(); ++var) {
        for (size_t value = 0; value < propositions[var].size(); ++value) {
            Proposition &prop = propositions[var][value];
            prop.cost = -1;
            prop.marked = false;
        }
    }

    // Deal with operators and axioms without preconditions.
    for (size_t i = 0; i < unary_operators.size(); ++i) {
        UnaryOperator &op = unary_operators[i];
        op.unsatisfied_preconditions = op.precondition.size();
        op.cost = op.base_cost; // will be increased by precondition costs

        if (op.unsatisfied_preconditions == 0)
            enqueue_if_necessary(op.effect, op.base_cost, &op);
    }
}

void FSAPPenalizedFFHeuristic::setup_exploration_queue_state(const State &state) {
    for (FactProxy fact : state) {
        Proposition *init_prop = get_proposition(fact);
        enqueue_if_necessary(init_prop, 0, 0);
    }
}
void FSAPPenalizedFFHeuristic::setup_exploration_queue_state(const StateInterface &state) {
    // We need to be a bit more careful about going through the var/val
    //  pairs, as we may have undefined variables (which should take on
    //  every value simultaneously).
    for (size_t var = 0; var < g_variable_domain.size(); ++var) {
        if (-1 == state[var]) {
            for (int val = 0; val < g_variable_domain[var]; ++val) {
                Proposition *init_prop = get_proposition(var, val);
                enqueue_if_necessary(init_prop, 0, 0);
            }
        } else {
            Proposition *init_prop = get_proposition(var, state[var]);
            enqueue_if_necessary(init_prop, 0, 0);
        }
    }
}

int FSAPPenalizedFFHeuristic::compute_fsap_penalty(int op_num) {
    // Axioms have a -1 operator number
    if (-1 == op_num)
        return 0;

    // Give the option to bypass this (potentially costly) computation
    if (!PRP.weaksearch.penalize_potential_fsaps)
        return 0;

    // We'll keep the running total of all the FSAPs found, scaled by the penalty amount
    int total = 0;
    for (auto fsap : *(PRP.deadend.nondetop2fsaps[g_operators[op_num].nondet_index])) {

        // If we've already seen it, then we don't need to check the partial state again
        if (0 != seen_fsaps.count(fsap))
            total += PRP.weaksearch.fsap_penalty;
        else {

            // It will only hold if all of the props are already added in the relaxed graph
            bool holds = true;
            for (auto varval : *(fsap->varvals())) {
                if (-1 == get_proposition(varval.first, varval.second)->cost) {
                    holds = false;
                    break;
                }
            }

            // When it holds, we add the new fsap as being enabled, and increase the penalty
            if (holds) {
                seen_fsaps.insert(fsap);
                total += PRP.weaksearch.fsap_penalty;
                if (PRP.logging.heuristic) {
                    cout << "\nFSAP-Heur(" << PRP.logging.id() << "): Penalizing for FSAP (" << fsap << "):" << endl;
                    fsap->dump();
                }
            }
        }
    }
    return total;
}

void FSAPPenalizedFFHeuristic::relaxed_exploration() {
    int unsolved_goals = goal_propositions.size();
    while (!queue.empty()) {
        pair<int, Proposition *> top_pair = queue.pop();
        int distance = top_pair.first;
        Proposition *prop = top_pair.second;
        int prop_cost = prop->cost;
        assert(prop_cost >= 0);
        assert(prop_cost <= distance);
        if (prop_cost < distance)
            continue;
        if (prop->is_goal && --unsolved_goals == 0)
            return;
        const vector<UnaryOperator *> &triggered_operators =
            prop->precondition_of;
        for (size_t i = 0; i < triggered_operators.size(); ++i) {
            UnaryOperator *unary_op = triggered_operators[i];
            increase_cost(unary_op->cost, prop_cost);
            --unary_op->unsatisfied_preconditions;
            assert(unary_op->unsatisfied_preconditions >= 0);
            if (unary_op->unsatisfied_preconditions == 0)
                enqueue_if_necessary(unary_op->effect,
                                     unary_op->cost + compute_fsap_penalty(unary_op->operator_no),
                                     unary_op);
        }
    }
}

void FSAPPenalizedFFHeuristic::mark_preferred_operators(
    const State &state, Proposition *goal) {
    if (!goal->marked) { // Only consider each subgoal once.
        goal->marked = true;
        UnaryOperator *unary_op = goal->reached_by;
        if (unary_op) { // We have not yet chained back to a start node.
            for (size_t i = 0; i < unary_op->precondition.size(); ++i)
                mark_preferred_operators(state, unary_op->precondition[i]);
            int operator_no = unary_op->operator_no;
            if (unary_op->cost == unary_op->base_cost && operator_no != -1) {
                // Necessary condition for this being a preferred
                // operator, which we use as a quick test before the
                // more expensive applicability test.
                // If we had no 0-cost operators and axioms to worry
                // about, this would also be a sufficient condition.
                OperatorProxy op = task_proxy.get_operators()[operator_no];

                // Note that we also will only want to do this if the
                //  action isn't forbidden here. Marking a forbidden
                //  action as preferred can lead to bad search expansion.
                if ((0 == forbidden_ops.count(g_operators[operator_no].nondet_index)) &&
                    (task_properties::is_applicable(op, state)))
                  set_preferred(op);
            }
        }
    }
}

void FSAPPenalizedFFHeuristic::mark_preferred_operators_and_relaxed_plan(
    const State &state, Proposition *goal) {
    if (!goal->marked) { // Only consider each subgoal once.
        goal->marked = true;
        UnaryOperator *unary_op = goal->reached_by;
        if (unary_op) { // We have not yet chained back to a start node.
            for (size_t i = 0; i < unary_op->precondition.size(); ++i)
                mark_preferred_operators_and_relaxed_plan(
                    state, unary_op->precondition[i]);
            int operator_no = unary_op->operator_no;
            if (operator_no != -1) {
                // This is not an axiom.
                relaxed_plan[operator_no] = true;

                if (unary_op->cost == unary_op->base_cost) {
                    // This test is implied by the next but cheaper,
                    // so we perform it to save work.
                    // If we had no 0-cost operators and axioms to worry
                    // about, it would also imply applicability.
                    OperatorProxy op = task_proxy.get_operators()[operator_no];


                    // Note that we also will only want to do this if the
                    //  action isn't forbidden here. Marking a forbidden
                    //  action as preferred can lead to bad search expansion.

                    if ((0 == forbidden_ops.count(g_operators[operator_no].nondet_index)) &&
                        (task_properties::is_applicable(op, state)))
                        set_preferred(op);
                }
            }
        }
    }
}

int FSAPPenalizedFFHeuristic::compute_add_and_ff(const State &state) {

    if (PRP.logging.heuristic) {
        cout << "\nFSAP-Heur(" << PRP.logging.id() << "): Computing heuristic for the following state:" << endl;
        state.dump_pddl();
        cout << endl;
    }

    setup_exploration_queue();
    setup_exploration_queue_state(state);
    relaxed_exploration();

    int total_cost = 0;
    for (size_t i = 0; i < goal_propositions.size(); ++i) {
        int prop_cost = goal_propositions[i]->cost;
        if (prop_cost == -1)
            return DEAD_END;
        increase_cost(total_cost, prop_cost);
    }

    if (PRP.logging.heuristic)
        cout << "\nFSAP-Heur(" << PRP.logging.id() << "): Heuristic value = " << total_cost << endl;

    return total_cost;
}
int FSAPPenalizedFFHeuristic::compute_add_and_ff(const StateInterface &state) {

    setup_exploration_queue();
    setup_exploration_queue_state(state);
    relaxed_exploration();

    int total_cost = 0;
    for (size_t i = 0; i < goal_propositions.size(); ++i) {
        int prop_cost = goal_propositions[i]->cost;
        if (prop_cost == -1)
            return DEAD_END;
        increase_cost(total_cost, prop_cost);
    }
    return total_cost;
}

int FSAPPenalizedFFHeuristic::compute_heuristic(const State &state) {

    if (PRP.deadend.record_online &&
        PRP.deadend.online_policy->check_entailed_match(PartialState(state)))
        return DEAD_END;

    int h = compute_add_and_ff(state);
    if (h != DEAD_END) {

        // Make sure we don't mark an operator as preferred if it's forbidden
        forbidden_ops.clear();
        vector<PolicyItem *> reg_items;
        PartialState * ps = new PartialState(state);
        PRP.deadend.policy->generate_entailed_items(*ps, reg_items);
        delete ps;
        for (auto item : reg_items)
            forbidden_ops.insert(((FSAP*)item)->op_index);

        // Collecting the relaxed plan also sets the preferred operators.
        for (size_t i = 0; i < goal_propositions.size(); ++i)
            mark_preferred_operators_and_relaxed_plan(state, goal_propositions[i]);

        int h_ff = 0;
        for (size_t op_no = 0; op_no < relaxed_plan.size(); ++op_no) {
            if (relaxed_plan[op_no]) {
                relaxed_plan[op_no] = false; // Clean up for next computation.
                h_ff += task_proxy.get_operators()[op_no].get_cost();
            }
        }
        return h_ff;

        // for (size_t i = 0; i < goal_propositions.size(); ++i)
        //     mark_preferred_operators(state, goal_propositions[i]);
    } else {
        if (PRP.logging.deadends)
            cout << "\nHeuristic found deadend!" << endl;

        if (PRP.deadend.record_online) {
            PRP.deadend.found_online.push_back(new DeadendTuple(new PartialState(state), NULL, NULL));
            PRP.deadend.online_policy->add_item(new Deadend(new PartialState(state)));
        }
    }
    return h;
}
int FSAPPenalizedFFHeuristic::compute_heuristic(const StateInterface &state) {
    return compute_add_and_ff(state);
}

int FSAPPenalizedFFHeuristic::compute_heuristic(const GlobalState &global_state) {
    return compute_heuristic(convert_global_state(global_state));
}

void FSAPPenalizedFFHeuristic::compute_heuristic_for_cegar(const State &state) {
    compute_heuristic(state);
}

static Heuristic *_parse(OptionParser &parser) {
    parser.document_synopsis("FSAP Penalized FF heuristic", "");
    parser.document_language_support("action costs", "supported");
    parser.document_language_support("conditional effects", "supported");
    parser.document_language_support("axioms", "supported soon");
    parser.document_property("admissible", "no");
    parser.document_property("consistent", "no");
    parser.document_property("safe", "yes for tasks without axioms");
    parser.document_property("preferred operators", "yes");

    Heuristic::add_options_to_parser(parser);
    Options opts = parser.parse();
    if (parser.dry_run())
        return 0;
    else
        return new FSAPPenalizedFFHeuristic(opts);
}

static Plugin<Heuristic> _plugin("fsapff", _parse);
}
