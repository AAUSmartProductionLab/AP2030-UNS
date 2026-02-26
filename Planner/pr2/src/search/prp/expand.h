#ifndef EXPAND_H
#define EXPAND_H

#include <vector>

#include "prp.h"

class GlobalOperator;

class PartialState;

/*******************************************************
 * For more advanced reachability, such as multi-agent *
 *  stuff, derived predicates, etc, etc, you can add   *
 *  extra details to the NondetSuccessor struct and    *
 *  re-define what generate_successors does.           *
 *                                                     *
 * Note: If you want to modify things in such a way,   *
 *       then you will need to change the SolutionStep *
 *       interface for get_successor(...) to match the *
 *       same format as the id field below. This is    *
 *       because the reachable tree needs to coincide  *
 *       with the generalized solution graph.          *
 *******************************************************/

struct NondetSuccessor {
    PartialState * state; // The reached state
    bool expected; // True if this is the expected outcome
    int id; // Unique ID for the successor among its siblings
    NondetSuccessor(PartialState * ps, bool exp, int id) : state(ps),
                                                           expected(exp),
                                                           id(id) {};
    ~NondetSuccessor();
};

PartialState * generate_nondet_successors(PartialState * current_state,
                                          const GlobalOperator * op,
                                          vector<NondetSuccessor *> &successors);

#endif
