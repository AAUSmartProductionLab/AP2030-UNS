
#ifndef REGRESSION_H
#define REGRESSION_H

#include "prp.h"

#include "policy.h"

class GlobalOperator;
class PartialState;

struct RegressableOperator : PolicyItem {
    const GlobalOperator *op;

    RegressableOperator(const GlobalOperator &o, PartialState *s) : PolicyItem(s), op(&o) {}

    virtual ~RegressableOperator() {}

    bool check_relevance(const PartialState &ps);

    virtual string get_name();
    virtual void dump() const;
};

void generate_regressable_ops();

#endif
