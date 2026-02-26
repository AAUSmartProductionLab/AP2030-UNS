
#include "simulator.h"

// Used to get us 2-decimal place precision
#include <iomanip>

#include "partial_state.h"
#include "solution.h"

#include "../global_operator.h"
#include "../globals.h"
#include "../utils/rng.h"

Simulator::Simulator(shared_ptr<SearchEngine> eng) : engine(eng) {
    current_state = new PartialState(g_root_task()->get_initial_state_values());
}

void Simulator::setup_simulation(PartialState * init) {
    if (init)
        current_state = new PartialState(*init);
    else
        current_state = new PartialState(g_root_task()->get_initial_state_values());
}

const GlobalOperator Simulator::pick_action(SolutionStep *step, int index) {
    if (-1 == index)
        index = PRP.rng(PRP.general.nondet_mapping[step->op->nondet_index]->size());
    return *(*(PRP.general.nondet_mapping[step->op->nondet_index]))[index];
}

void Simulator::reset_goal() {
    g_goal.clear();
    for (auto goal_tuple : PRP.localize.original_goal)
        g_goal.push_back(make_pair(goal_tuple.first, goal_tuple.second));
}

void Simulator::set_local_goal() {
    // Adjust the goal if we are planning locally
    if (PRP.localize.enabled) {
        g_goal.clear();
        for (auto varval : *(current_goal->varvals()))
            g_goal.push_back(make_pair(varval.first, varval.second));
    }
}

void Simulator::search() {
    // First set the new initial state
    for (size_t i = 0; i < g_variable_domain.size(); ++i)
        g_initial_state_data[i] = (*current_state)[i];

    if (PRP.logging.verbose) {
        cout << "\nPlanning for initial state:" << endl;
        for (size_t i = 0; i < g_variable_domain.size(); ++i)
            cout << g_fact_names[i][g_initial_state_data[i]] << endl;
        cout << "\n...and goal state:" << endl;
        for (auto varval : g_goal)
            cout << g_fact_names[varval.first][varval.second] << endl;
        cout << endl;
    }

    // Finally, solve the problem
    engine->search();
    PRP.weaksearch.num_searches++;
}

bool Simulator::simulate_policy(Solution *sol, PartialState * init) {

    setup_simulation(init);

    PartialState * tmp;

    SolutionStep * step = sol->get_step(*current_state);
    last_run_count = 0;

    while (step && (last_run_count < PRP.simulator.trial_depth)) {

        last_run_count++;

        if (step->is_goal) {
            delete current_state;
            return true;
        }

        tmp = current_state->progress(pick_action(step));
        delete current_state;
        current_state = tmp;
        step = sol->get_step(*current_state);
    }

    last_run_hit_depth = (last_run_count >= PRP.simulator.trial_depth);

    delete current_state;
    return false;
}

bool Simulator::simulate_graph(Solution *sol, PartialState * init) {

    setup_simulation(init);

    SolutionStep * step = sol->get_step(*current_state);
    delete current_state;
    last_run_count = 0;

    while (step && (last_run_count < PRP.simulator.trial_depth)) {
        last_run_count++;
        if (step->is_goal)
            return true;
        step = step->get_successor(PRP.rng(step->get_successors().size()));
    }

    last_run_hit_depth = (last_run_count >= PRP.simulator.trial_depth);

    return false;
}

bool Simulator::simulate_solution(Solution *sol, PartialState * init) {
    setup_simulation(init);

    PartialState * tmp;

    SolutionStep * step = sol->get_step(*current_state);
    last_run_count = 0;

    while (step && (last_run_count < PRP.simulator.trial_depth)) {

        last_run_count++;

        if (step->is_goal) {
            delete current_state;
            return true;
        }

        int choice = PRP.rng(step->get_successors().size());
        tmp = current_state->progress(pick_action(step, choice));
        delete current_state;
        current_state = tmp;

        step = step->get_successor(choice);
        if (!step)
            step = sol->get_step(*current_state);
        assert((!step) || (current_state->entails(*(step->state))));
    }

    last_run_hit_depth = (last_run_count >= PRP.simulator.trial_depth);

    return false;
}

void Simulator::run_trials() {

    int succ=0, fail=0, depth=0;
    double succ_avg_depth=0.0, fail_avg_depth=0.0;

    for (int i = 0; i < PRP.simulator.num_trials; i++) {
        if (simulate_solution(PRP.solution.incumbent)) {
            succ++;
            succ_avg_depth += double(last_run_count) / double(PRP.simulator.num_trials);
        } else {
            if (last_run_hit_depth)
                depth++;
            else {
                fail++;
                fail_avg_depth += double(last_run_count) / double(PRP.simulator.num_trials);
            }
        }
    }

    cout << setprecision(2) << fixed;
    cout << endl;
    cout << "\t\t--------------------------------------" << endl;
    cout << "\t\t      { Simulation Statistics }" << endl;
    cout << "\t\t--------------------------------------\n" << endl;
    cout << "                          Trials: " << PRP.simulator.num_trials << endl;
    cout << "                           Depth: " << PRP.simulator.trial_depth << endl;
    cout << "                         Success: " << succ << "\t (" << (100.0 * double(succ) / double(succ+depth+fail)) << " %)" << endl;
    cout << "                        Failures: " << (fail+depth) << "\t (" << (100.0 * double(depth+fail) / double(succ+depth+fail)) << " %)" << endl;
    cout << endl;
    cout << " Failures due to unhandled state: " << fail << "\t (" << (100.0 * double(fail) / double(depth+fail)) << " %)" << endl;
    cout << "     Failures due to depth limit: " << depth << "\t (" << (100.0 * double(depth) / double(depth+fail)) << " %)" << endl;
    cout << endl;
    cout << "      Mean successful run length: " << succ_avg_depth << endl;
    cout << "  Mean (state-)failed run length: " << fail_avg_depth << endl;
    cout << endl;
    cout << "-------------------------------------------------------------------\n" << endl;
}

bool Simulator::check_1safe() {

    if (!PRP.deadend.enabled)
        return true;

    // We need to reset in order to get reliable deadend detection
    reset_goal();

    vector<DeadendTuple *> new_deadends;
    PartialState* old_s = new PartialState(*current_state);
    PartialState* new_s;

    // If we do the full 1safe check, then we go through the entire plan. If not,
    //  then we should at least check the first action. In particular, we don't
    //  want the first action in the plan to end up being forbidden.
    unsigned safe_checks = 1;
    if (PRP.deadend.force_1safe_weak_plans)
        safe_checks = engine->get_plan().size();

    for (unsigned i = 0; i < safe_checks; i++) {
        const GlobalOperator *op = engine->get_plan()[i];
        vector<NondetSuccessor *> successors;
        new_s = generate_nondet_successors(old_s, op, successors);

        for (auto succ : successors) {
            if (is_deadend(*(succ->state))) {
                PartialState * new_dead_state = new PartialState(*(succ->state));
                const GlobalOperator *bad_op = (*(PRP.general.nondet_mapping[op->nondet_index]))[succ->id];
                if (PRP.deadend.generalize)
                    generalize_deadend(*new_dead_state);
                new_deadends.push_back(new DeadendTuple(new_dead_state, new PartialState(*old_s), bad_op));
            }
        }

        for (auto succ : successors)
            if (succ->state != new_s)
                delete succ;

        delete old_s;
        old_s = new_s;
    }

    if (new_deadends.size() > 0) {
        if (PRP.logging.deadends)
            cout << "Found " << new_deadends.size() << " new deadends during 1-safe checking!" << endl;
        update_deadends(new_deadends);
        return false;
    }

    // As a sanity check, make sure that we aren't forbidding the first action
    //  in the plan.
    assert(!is_forbidden(*current_state, engine->get_plan()[0]));

    return true;
}

SolutionStep* Simulator::record_plan() {

    if (PRP.logging.simulator)
        cout << "SIMULATOR(" << PRP.logging.id() << "): Recording the found plan." << endl;

    // Reset the global goal
    reset_goal();

    // Incorporate the new plan, and return the first SolutionStep constructed
    return PRP.solution.incumbent->incorporate_plan(engine->get_plan(),
                                                    current_state,
                                                    PRP.general.matched_step);
}

SolutionStep* Simulator::replan() {

    // If the policy is complete, searching further won't help us
    if (PRP.solution.incumbent->is_strong_cyclic()) {
        cout << "Error: Trying to replan with a strong cyclic incumbent." << endl;
        exit(0);
    }

    if (!current_state) {
        cout << "Error: No current state for the replan." << endl;
        exit(0);
    }

    // If we are detecting deadends, and know this is one, don't even try
    if (PRP.deadend.enabled)
        if (PRP.deadend.states->check_entailed_match(*current_state))
            return 0;

    // If we can detect that this is a deadend for the original goal, forget about it
    if (is_deadend(*current_state))
        return 0;

    // Will hold later only if no plan works, and we want to plan locally
    bool try_again = PRP.localize.enabled;
    if (try_again && PRP.localize.limited) {
        PRP.weaksearch.limit_states = true;
        PRP.weaksearch.max_states = PRP.localize.max_states;
    }

    if (PRP.logging.simulator)
        cout << "SIMULATOR(" << PRP.logging.id() << "): Trying to plan initially" << endl;

    set_local_goal();
    search();

    while (engine->found_solution() && !check_1safe()) {
        // We need to reset the local goal since the check_1safe resets it
        //  to the original for proper deadend detection
        set_local_goal();
        search();
    }

    PRP.weaksearch.limit_states = false;

    if (engine->found_solution())
        return record_plan();

    reset_goal(); // Note that if record_plan() was called, then so was reset_goal()

    if (try_again) {

        if (PRP.logging.simulator)
            cout << "SIMULATOR(" << PRP.logging.id() << "): Trying to plan again" << endl;

        search();

        while (engine->found_solution() && !check_1safe())
            search();

        if (engine->found_solution())
            return record_plan();
    }

    return 0;
}
