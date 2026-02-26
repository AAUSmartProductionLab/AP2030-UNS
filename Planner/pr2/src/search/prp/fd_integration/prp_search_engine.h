#ifndef SEARCH_ENGINES_PRP_SEARCH_H
#define SEARCH_ENGINES_PRP_SEARCH_H

#include "../../option_parser_util.h"
#include "../../search_engine.h"
#include "../../utils/timer.h"
#include "../../open_lists/standard_scalar_open_list.h"

#include "../prp.h"

#include <memory>

namespace options {
class Options;
}

namespace prp_search {
class PRPSearch : public SearchEngine {

    Heuristic *h; // The heuristic we want to use

    vector<Heuristic *> preferred_list;
    vector<Evaluator *> preferred_list_scalar;

    std::unique_ptr<SearchEngine> get_search_engine();
    virtual SearchStatus step() override;

public:
    explicit PRPSearch(const options::Options &opts);

    virtual void save_plan_if_necessary() const override;
    virtual void print_statistics() const override;
};
}

#endif
