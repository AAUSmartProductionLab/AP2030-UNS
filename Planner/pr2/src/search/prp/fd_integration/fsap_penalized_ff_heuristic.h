#ifndef HEURISTICS_FSAP_PENALIZED_FF_HEURISTIC_H
#define HEURISTICS_FSAP_PENALIZED_FF_HEURISTIC_H

#include "../../heuristics/relaxation_heuristic.h"

#include "../../algorithms/priority_queues.h"
#include "../../utils/collections.h"
#include "../../global_operator.h"

#include "../prp.h"
#include "../policy.h"
#include "../deadend.h"

#include <cassert>

class State;

namespace fsap_penalized_ff_heuristic {
using relaxation_heuristic::Proposition;
using relaxation_heuristic::UnaryOperator;

class FSAPPenalizedFFHeuristic : public relaxation_heuristic::RelaxationHeuristic {
    /* Costs larger than MAX_COST_VALUE are clamped to max_value. The
       precise value (100M) is a bit of a hack, since other parts of
       the code don't reliably check against overflow as of this
       writing. With a value of 100M, we want to ensure that even
       weighted A* with a weight of 10 will have f values comfortably
       below the signed 32-bit int upper bound.
     */
    static const int MAX_COST_VALUE = 100000000;

    priority_queues::AdaptiveQueue<Proposition *> queue;
    bool did_write_overflow_warning;

    set<int> forbidden_ops; // The operators (non-det indices) that are currently forbidden
    set< FSAP* > seen_fsaps; // Keeps track of the enabled FSAPs during a heuristic computation

    // Relaxed plans are represented as a set of operators implemented
    // as a bit vector.
    typedef std::vector<bool> RelaxedPlan;
    RelaxedPlan relaxed_plan;

    void setup_exploration_queue();
    void setup_exploration_queue_state(const State &state);
    void setup_exploration_queue_state(const StateInterface &state);
    void relaxed_exploration();
    void mark_preferred_operators(const State &state, Proposition *goal);
    void mark_preferred_operators_and_relaxed_plan(
        const State &state, Proposition *goal);

    int compute_fsap_penalty(int op_num);

    void enqueue_if_necessary(Proposition *prop, int cost, UnaryOperator *op) {
        assert(cost >= 0);
        if (prop->cost == -1 || prop->cost > cost) {
            prop->cost = cost;
            prop->reached_by = op;
            queue.push(cost, prop);
        }
        if (PRP.logging.heuristic) {
            if (op) {
                cout << "Enquing operator " << g_operators[op->operator_no].get_name() << " at cost " << cost << endl;
                cout << "  PRE:";
                for (auto pre : op->precondition)
                    cout << "  " << unpropositions[pre->id];
                cout << "\n  EFF:  " << unpropositions[prop->id] << endl;
            } else
                cout << "Enquing true prop " << unpropositions[prop->id] << " at cost " << cost << endl;
        }
        assert(prop->cost != -1 && prop->cost <= cost);
    }

    void increase_cost(int &cost, int amount) {
        assert(cost >= 0);
        assert(amount >= 0);
        cost += amount;
        if (cost > MAX_COST_VALUE) {
            write_overflow_warning();
            cost = MAX_COST_VALUE;
        }
    }

    void write_overflow_warning();

    int compute_heuristic(const State &state);
    int compute_heuristic(const StateInterface &state);

protected:
    virtual int compute_heuristic(const GlobalState &global_state);

public:
    explicit FSAPPenalizedFFHeuristic(const options::Options &options);
    ~FSAPPenalizedFFHeuristic();

    // Reset things properly when we're about to replan
    virtual void reset();

    // Common part of h^add and h^ff computation.
    int compute_add_and_ff(const State &state);
    int compute_add_and_ff(const StateInterface &state);

    /*
      FDTODO: The two methods below are temporarily needed for the CEGAR
      heuristic. In the long run it might be better to split the
      computation from the heuristic class. Then the CEGAR code could
      use the computation object instead of the heuristic.
    */
    void compute_heuristic_for_cegar(const State &state);

    int get_cost_for_cegar(int var, int value) const {
        assert(utils::in_bounds(var, propositions));
        assert(utils::in_bounds(value, propositions[var]));
        return propositions[var][value].cost;
    }
};
}

#endif
