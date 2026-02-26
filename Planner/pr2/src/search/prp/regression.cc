
#include "regression.h"

#include "../global_operator.h"

#include "../globals.h"

bool RegressableOperator::check_relevance(const PartialState &ps) {
    for (auto eff : op->get_all_effects())
        if (-1 != ps[eff.var])
            return true;
    return false;
}

void RegressableOperator::dump() const {
    cout << "Regressable operator:" << endl;
    cout << " -{ Operator }-" << endl;
    op->dump();
    cout << " -{ State }-" << endl;
    state->dump_pddl();
    cout << "" << endl;
}

string RegressableOperator::get_name() {
    return op->get_name();
}

void generate_regressable_ops() {

    list<PolicyItem *> reg_steps;
    list<PolicyItem *> cond_reg_steps;

    PartialState *s;
    for (auto & op : g_operators) {

        // First, consider operators that lack conditional effects
        if (0 == PRP.general.conditional_mask[op.nondet_index]->size()) {
            s = new PartialState();

            // Only applicable if the effects currently hold.
            for (auto eff : op.get_all_effects())
                (*s)[eff.var] = eff.val;

            reg_steps.push_back(new RegressableOperator(op, s));
        }

        // Next, consider operators that have conditional effects that
        //  are consistent -- i.e., they can all fire simultaneously.
        else {

            s = new PartialState();
            bool consistent = true;

            // Ensure that the preconditions and conditional effect
            //  conditions are all consistent to fire.
            for (auto pre : op.get_preconditions()) {

                if ((-1 != (*s)[pre.var]) && (pre.val != (*s)[pre.var])) {
                    consistent = false;
                    break;
                } else {
                    (*s)[pre.var] = pre.val;
                }
            }

            // Only makes sense to continue if it is consistent so far
            if (consistent) {
                for (auto eff : op.get_all_effects()) {
                    for (auto cond : eff.conditions) {
                        if ((-1 != (*s)[cond.var]) && (cond.val != (*s)[cond.var])) {
                            consistent = false;
                            break;
                        } else {
                            (*s)[cond.var] = cond.val;
                        }
                    }
                    if (!consistent)
                        break;
                }
            }

            // Reset the state for checking the post conditions
            delete s;
            s = new PartialState();

            // Only makes sense to continue if it is consistent so far
            if (consistent) {
                // Only applicable if the post conditions currently hold.
                for (auto eff : op.get_all_effects()) {
                    if ((-1 != (*s)[eff.var]) && (eff.val != (*s)[eff.var])) {
                        consistent = false;
                        break;
                    } else {
                        (*s)[eff.var] = eff.val;
                    }
                }
            }

            if (consistent)
                cond_reg_steps.push_back(new RegressableOperator(op, s));
            else
                delete s;
        }
    }

    PRP.general.regressable_ops = new Policy();
    PRP.general.regressable_ops->update_policy(reg_steps);
    PRP.general.regressable_cond_ops = new Policy();
    PRP.general.regressable_cond_ops->update_policy(cond_reg_steps);

}
