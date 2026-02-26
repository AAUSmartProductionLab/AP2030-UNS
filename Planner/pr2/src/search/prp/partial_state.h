#ifndef PARTIAL_STATE_H
#define PARTIAL_STATE_H

#include <iostream>
#include <fstream>
#include <vector>

#include "prp.h"

#include "../global_state.h"

class GlobalOperator;

class PartialState : public StateInterface {
    int *vars; // values for vars
    vector< pair<int,int> > * _varvals = 0; // varval pairs for partial states
    void _allocate();
    void _deallocate();
    void _copy_buffer_from_state(const PartialState &state);

public:

    PartialState &operator=(const PartialState &other);

    PartialState(); // Creates a state with -1 values for everything
    PartialState(std::vector<int> init_vals);
    PartialState(const StateInterface &state);
    PartialState(const State &state);
    PartialState(const PartialState &state);
    ~PartialState();

    int size() const;

    PartialState * progress(const GlobalOperator &op);
    PartialState * regress(const GlobalOperator &op, PartialState *context=NULL);

    bool consistent_with(const PartialState &other);
    bool entails(const PartialState &other);
    void combine_with(const PartialState &state);
    vector< pair<int,int> > * varvals();

    int &operator[](int index) {
        if (_varvals) {
            delete _varvals;
            _varvals = 0;
        }
        return vars[index];
    }
    int operator[](int index) const {
        return vars[index];
    }

    void dump_pddl() const;
    void dump_fdr() const;

    bool operator==(const PartialState &other) const;
    bool operator<(const PartialState &other) const;

    size_t hash() const;

    void record_snapshot(ofstream &outfile, string indent);

};

#endif
