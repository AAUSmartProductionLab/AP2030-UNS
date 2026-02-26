#ifndef TASK_UTILS_SUCCESSOR_GENERATOR_H
#define TASK_UTILS_SUCCESSOR_GENERATOR_H

#include "../prp/deadend.h"

#include <memory>
#include <vector>

class StateInterface;
class GlobalState;
class OperatorID;
class State;
class TaskProxy;

namespace successor_generator {
class GeneratorBase;

class SuccessorGenerator {
    std::unique_ptr<GeneratorBase> root;

    typedef std::vector<FactProxy> Condition;
    GeneratorBase *construct_recursive(
        int switch_var_id, std::list<OperatorProxy> &&operator_queue);

    std::vector<Condition> conditions;
    std::vector<Condition::const_iterator> next_condition_by_op;

    SuccessorGenerator(const SuccessorGenerator &) = delete;
public:
    explicit SuccessorGenerator(const TaskProxy &task_proxy);
    /*
      We cannot use the default destructor (implicitly or explicitly)
      here because GeneratorBase is a forward declaration and the
      incomplete type cannot be destroyed.
    */
    ~SuccessorGenerator();

    void generate_applicable_ops(
        const State &state, std::vector<OperatorID> &applicable_ops) const;
    // Transitional method, used until the search is switched to the new task interface.
    void generate_applicable_ops(
        const StateInterface &state, std::vector<OperatorID> &applicable_ops) const;
};
}

#endif
