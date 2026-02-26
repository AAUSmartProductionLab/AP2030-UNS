#ifndef SOLUTION_H
#define SOLUTION_H

#include <map>
#include <list>
#include <vector>

#include "../search_engine.h"

#include "prp.h"

#include "policy.h"

class PartialState;
class Simulator;
struct PSGraph;

struct SolutionStep : PolicyItem {

private:

    vector<SolutionStep *> succ;
    multiset<SolutionStep *> pred;
    PSGraph *containing_graph;

    void set_successor(int id, SolutionStep * s) {
        assert (0 == succ[id]);
        reset_successor(id, s);
    }
    void reset_successor(int id, SolutionStep * s) { succ[id] = s; }
    void unset_successor(int id) { succ[id] = 0; }

    void add_predecessor(SolutionStep * s) {
        assert(s);
        pred.insert(s);
    }
    void unset_predecessor(SolutionStep * s) {
        assert(pred.find(s) != pred.end());
        pred.erase(pred.find(s));
    }

public:

    const GlobalOperator *op;
    int distance;

    bool is_relevant; // Used to keep track of reachable steps
    bool is_goal; // Self-explanatory
    bool is_sc; // Used to cache strong cyclicity. Once true, always true.

    int expected_id; // id for the expected successor
    int step_id; // Unique id for the solstep

    SolutionStep(PartialState *s, PSGraph *psg, int d, const GlobalOperator *op, int exid,
                 bool is_r=false, bool is_g=false, bool is_s=false);
    ~SolutionStep() {}

    string get_name();
    void dump() const;

    void strengthen(PartialState *s);

    bool operator< (const SolutionStep& other) const;
    SolutionStep* copy();

    void validate(set< PRPSearchNode * > &matching_nodes);
    void record_snapshot(ofstream &outfile, string indent);

    // Change this if you have a complex nondet successor function in
    //  the expand.* files.
    int num_successors() { return succ.size(); }
    const vector<SolutionStep *>& get_successors() { return succ; }
    SolutionStep * get_expected_successor() {return get_successor(expected_id);}
    SolutionStep * get_successor(int id) {
        if (-1 == id)
            return NULL;
        assert(0 <= id);
        assert(id < (int)succ.size());
        return succ[id];
    }
    bool has_successor(int id) { return 0 != succ[id]; }

    bool has_predecessor(SolutionStep * s) { return pred.find(s) != pred.end(); }
    const multiset<SolutionStep *>& get_predecessors() { return pred; }

    void connect_to_successor(int id, SolutionStep * s) {

        #ifndef NDEBUG
        if (PRP.logging.log_solstep(step_id) || PRP.logging.log_solstep(s->step_id))
            cout << "\nSOLSTEP(" << PRP.logging.id() << "): Connecting " << step_id << " to " << s->step_id << " via " << id << endl;
        #endif

        set_successor(id, s);
        s->add_predecessor(this);
    }

    void unconnect_from_successor(int id) {

        #ifndef NDEBUG
        if (PRP.logging.log_solstep(step_id) || PRP.logging.log_solstep(succ[id]->step_id))
            cout << "\nSOLSTEP(" << PRP.logging.id() << "): Disconnecting " << step_id << " from " << succ[id]->step_id << " via " << id << endl;
        #endif

        assert(has_successor(id));
        succ[id]->unset_predecessor(this);
        unset_successor(id);
    }

};

struct SolutionStepCompare {
    bool operator()(const SolutionStep* first, const SolutionStep* second) {
        return *first < *second;
    }
};


class Solution {

    Simulator *simulator;

    double score;

    void evaluate_random();

public:

    PSGraph *network;
    Policy *policy;

    Solution(Simulator *sim);
    ~Solution();

    const GlobalOperator * get_action(const StateInterface &state, bool avoid_forbidden = PRP.deadend.enabled);
    SolutionStep * get_step(const StateInterface &state, bool avoid_forbidden = PRP.deadend.enabled);

    void evaluate();
    double get_score();
    int get_size();
    bool better_than(Solution * other);

    void rebuild();

    SolutionStep* incorporate_plan(const SearchEngine::Plan &plan,
                                   PartialState *start_state,
                                   SolutionStep *goal_step);
    void insert_step(SolutionStep * step);
    void insert_steps(list<PolicyItem *> &steps);

    void clear_dead_solsteps(map< SolutionStep* , set< PRPSearchNode * > * > * solstep2searchnode);

    bool is_strong_cyclic();

    void record_snapshot(ofstream &outfile, map< SolutionStep* , set< PRPSearchNode * > * > &solstep2searchnode, list< PRPSearchNode * > * created_search_nodes, string type, string indent="");

};

#endif
