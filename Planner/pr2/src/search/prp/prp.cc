
#include "prp.h"

#include "fond_search.h"
#include "partial_state.h"
#include "partial_state_graph.h"
#include "policy.h"
#include "regression.h"
#include "simulator.h"
#include "solution.h"

#include "fd_integration/fsap_penalized_ff_heuristic.h"

#include "../option_parser.h"
#include "../search_engine.h"

utils::ExitCode PRPWrapper::run_prp(shared_ptr<SearchEngine> engine) {

    PRP.time.start();

    /**********************************
     * Initialize the data structures *
     **********************************/

    if (PRP.deadend.enabled)
        generate_regressable_ops();

    // We create the policies even if we aren't using deadends, as
    //  they may be consulted by certain parts of the code.
    PRP.deadend.policy = new Policy();
    PRP.deadend.states = new Policy();
    PRP.deadend.online_policy = new Policy();

    // We also create a deadend heuristic computer
    Options h_options;
    h_options.set<bool>("cache_estimates", false);
    h_options.set<shared_ptr<AbstractTask>>("transform", g_root_task());
    PRP.deadend.reachability_heuristic = new fsap_penalized_ff_heuristic::FSAPPenalizedFFHeuristic(h_options);




    /**********************
     * Handle Time Limits *
     **********************/

    cout << "\nTotal allotted time (s): " << PRP.time.limit << endl;

    // If we are going to do a final FSAP-free round, then we modify the
    //  time limits to give a 50/50 split between the main phase and final
    //  round phase
    double time_ratio = 0.5;
    if (PRP.general.final_fsap_free_round)
        PRP.time.limit *= time_ratio;

    cout << "Max time for core phase (remaining used in final-round repairs): " << PRP.time.limit << endl;

    // Adjust the g_time_limit so the epochs are handled properly
    int epochs_remaining = PRP.epoch.max;
    double single_time_limit = PRP.time.limit / (double)PRP.epoch.max;
    PRP.time.limit = single_time_limit;

    cout << "Max time for each of the " << epochs_remaining << " epochs: " << PRP.time.limit << endl << endl;




    /***************************************************
     * Initialize the remaining data structures needed *
     ***************************************************/

    cout << "\n\nCreating the simulator..." << endl;
    Simulator *sim = new Simulator(engine);

    cout << "\n\nGenerating an incumbent solution..." << endl;
    PRP.solution.incumbent = new Solution(sim);
    PRP.solution.best = PRP.solution.incumbent;




    /********************************
     * Do the main computation loop *
     ********************************/

    cout << "\n\nBeginning search for strong cyclic solution..." << endl;

    while (find_better_solution(sim)) {
        if (PRP.logging.verbose)
            cout << "Finished repair round." << endl;

        if (!PRP.time.time_left()) {
            epochs_remaining--;
            if (epochs_remaining > 0)
                PRP.time.limit += single_time_limit;
        }
    }

    cout << "Done repairing..." << endl;

    // Use the best policy found so far
    if (PRP.solution.incumbent && PRP.solution.best &&
        (PRP.solution.best != PRP.solution.incumbent) &&
        PRP.solution.best->better_than(PRP.solution.incumbent))
            PRP.solution.incumbent = PRP.solution.best;




    /********************************
     * Do the final FSAP free round *
     ********************************/

    if (PRP.general.final_fsap_free_round)
        PRP.time.limit /= time_ratio;

    if (PRP.general.final_fsap_free_round &&
        !(PRP.solution.incumbent->is_strong_cyclic())) {

        bool os1 = PRP.deadend.enabled;
        bool os2 = PRP.deadend.generalize;
        bool os3 = PRP.deadend.record_online;
        bool os4 = PRP.deadend.force_1safe_weak_plans;
        bool os5 = PRP.deadend.poison_search;
        bool os6 = PRP.weaksearch.limit_states;
        int  os7 = PRP.weaksearch.max_states;

        PRP.deadend.enabled = false;
        PRP.deadend.generalize = false;
        PRP.deadend.record_online = false;
        PRP.deadend.force_1safe_weak_plans = false;
        PRP.deadend.poison_search = false;
        PRP.weaksearch.limit_states = true;
        PRP.weaksearch.max_states = 1000;

        cout << "\n\nDoing one final best-effort round ignoring FSAPs for unhandled states." << endl;
        find_better_solution(sim);

        PRP.deadend.enabled = os1;
        PRP.deadend.generalize = os2;
        PRP.deadend.record_online = os3;
        PRP.deadend.force_1safe_weak_plans = os4;
        PRP.deadend.poison_search = os5;
        PRP.weaksearch.limit_states = os6;
        PRP.weaksearch.max_states = os7;
    }


    /********************************
     * Optimize things if necessary *
     ********************************/
    if (PRP.general.optimize_final_solution) {
        PRP.solution.incumbent->rebuild();
        PRP.deadend.policy->rebuild();
    }




    /************************************
     * Print out the general statistics *
     ************************************/
    cout << "\n\n-------------------------------------------------------------------\n" << endl;
    cout << "\n\t\t-----------------------------------" << endl;
    cout << "\t\t      { General Statistics }" << endl;
    cout << "\t\t-----------------------------------\n" << endl;
    cout << "                         Time taken: " << PRP.time.time_taken() << " sec" << endl;
    cout << "                           # Rounds: " << PRP.logging.fond_search_count << endl;
    cout << "                    # Weak Searches: " << PRP.weaksearch.num_searches << endl;
    cout << "                      Solution Size: " << PRP.solution.incumbent->get_size() << endl;
    cout << "                          FSAP Size: " << PRP.deadend.policy->size() << endl;
    if (PRP.deadend.combine)
        cout << "                  Combination Count: " << PRP.deadend.combination_count << endl;
    if (PRP.deadend.poison_search)
        cout << "                       Poison Count: " << PRP.deadend.poison_count << endl;
    cout << "\n-------------------------------------------------------------------\n" << endl;




    /**********************
     * Run the simulation *
     **********************/

    // Disable the deadend settings for the online simulation(s)
    PRP.deadend.enabled = false;
    PRP.deadend.generalize = false;
    PRP.deadend.record_online = false;

    cout << "\nRunning the simulation..." << endl;
    sim->run_trials();




    /*******************************
     * Dump the required log files *
     *******************************/
    if (PRP.output.format == PRP.output.MATCHTREE) {

        cout << "Dumping the policy and fsaps..." << endl;
        ofstream outfile;

        outfile.open("policy.out", ios::out);
        PRP.solution.incumbent->policy->generate_cpp_input(outfile);
        outfile.close();

        outfile.open("policy.fsap", ios::out);
        PRP.deadend.policy->generate_cpp_input(outfile);
        outfile.close();

    } else if (PRP.output.format == PRP.output.LIST) {

        cout << "Dumping the policy and fsaps..." << endl;
        PRP.solution.incumbent->policy->write_policy("policy.out");
        PRP.deadend.policy->write_policy("policy.fsap", true);

    } else if (PRP.output.format == PRP.output.CONTROLLER) {

        cout << "Dumping the final psgraph as json..." << endl;

        ofstream outfile;
        outfile.open("policy.out", ios::out);
        PRP.solution.incumbent->network->record_snapshot(outfile, "", false);

    }


    cout << endl;


    /************************************
     * Return based on strong cyclicity *
     ************************************/

    if (PRP.solution.best->is_strong_cyclic())
        return utils::ExitCode::STRONG_CYCLIC;
    else
        return utils::ExitCode::NOT_STRONG_CYCLIC;
}
