
#include "expand.h"

#include "partial_state.h"

#include "../globals.h"
#include "../global_operator.h"

PartialState * generate_nondet_successors(PartialState * current_state, const GlobalOperator * op, vector<NondetSuccessor *> &successors) {

    PartialState * expected = 0;
    for (auto o : *(PRP.general.nondet_mapping[op->nondet_index])) {
        successors.push_back(new NondetSuccessor(current_state->progress(*o),
                                                 (o == op), o->nondet_outcome));
        if (o == op)
            expected = successors.back()->state;
    }

    // Make sure that we have the right number of successors and expected state
    assert(successors.size() == PRP.general.nondet_mapping[op->nondet_index]->size());
    assert(expected);

    return expected;

}

NondetSuccessor::~NondetSuccessor() {
    if (state)
        delete state;
}
