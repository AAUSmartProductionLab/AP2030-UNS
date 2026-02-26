#ifndef DEADEND_H
#define DEADEND_H

#include <iostream>
#include <list>
#include <string>
#include <vector>

#include "prp.h"

#include "policy.h"

#include "fd_integration/fsap_penalized_ff_heuristic.h"

#include "../operator_id.h"
#include "../task_utils/successor_generator.h"

class GlobalOperator;
class OperatorID;

class PartialState;

struct DeadendTuple {
    PartialState *de_state;
    PartialState *prev_state;
    const GlobalOperator *prev_op;

    DeadendTuple(PartialState *ds, PartialState *ps, const GlobalOperator *op) : de_state(ds), prev_state(ps), prev_op(op) {}
    ~DeadendTuple() {};
};

struct FSAP : PolicyItem {

    int op_index; // The nondet action id we are forbidding

    FSAP(PartialState *s, int index) : PolicyItem(s), op_index(index) {}

    ~FSAP() {}

    bool operator< (const FSAP& other) const;

    string get_name();
    int get_index();
    void dump() const;
};

struct Deadend : FSAP {
    Deadend(PartialState *s) : FSAP(s, -1) {};
    void dump() const;
};

void update_deadends(vector< DeadendTuple * > &failed_states);

bool is_deadend(PartialState &state);
bool is_forbidden(PartialState &state, const GlobalOperator *op);

bool generalize_deadend(PartialState &state);

struct DeadendAwareSuccessorGenerator {
    void generate_applicable_ops(const StateInterface &curr, vector<OperatorID> &ops);
    void generate_applicable_ops(const State &curr, vector<OperatorProxy> &ops);
};

#endif
