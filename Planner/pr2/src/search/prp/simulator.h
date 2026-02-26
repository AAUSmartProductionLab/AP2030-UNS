#ifndef SIMULATOR_H
#define SIMULATOR_H

#include "prp.h"
#include "expand.h"

class Solution;
class SolutionStep;

class Simulator {

    PartialState *current_state;
    PartialState *current_goal;

    void search();
    void setup_simulation(PartialState *cur = 0);
    void reset_goal();
    void set_local_goal();
    bool check_1safe();
    SolutionStep* record_plan();

    const GlobalOperator pick_action(SolutionStep *step, int index = -1);

    bool last_run_hit_depth = false;
    int last_run_count = 0;

public:

    shared_ptr<SearchEngine> engine;

    Simulator(shared_ptr<SearchEngine> engine);
    ~Simulator() {};

    bool simulate_policy(Solution *sol, PartialState *cur = 0);
    bool simulate_graph(Solution *sol, PartialState *cur = 0);
    bool simulate_solution(Solution *sol, PartialState *cur = 0);

    void run_trials();

    SolutionStep* replan();

    void set_state(PartialState * s) { current_state = s; }
    void set_goal(PartialState * s) { current_goal = s; }

};

#endif
