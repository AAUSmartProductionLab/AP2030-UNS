#include "option_parser.h"
#include "search_engine.h"

#include "utils/system.h"
#include "utils/timer.h"

#include "prp/prp.h"

#include <iostream>

using namespace std;
using utils::ExitCode;

int main(int argc, const char **argv) {
    utils::register_event_handlers();

    if (argc < 2) {
        cout << OptionParser::usage(argv[0]) << endl;
        utils::exit_with(ExitCode::INPUT_ERROR);
    }

    if (static_cast<string>(argv[1]) != "--help")
        read_everything(cin);

    shared_ptr<SearchEngine> engine;

    // The command line is parsed twice: once in dry-run mode, to
    // check for simple input errors, and then in normal mode.
    bool unit_cost = is_unit_cost();
    try {
        OptionParser::parse_cmd_line(argc, argv, true, unit_cost);
        engine = OptionParser::parse_cmd_line(argc, argv, false, unit_cost);
    } catch (ArgError &error) {
        cerr << error << endl;
        cerr << OptionParser::usage(argv[0]) << endl;
        utils::exit_with(ExitCode::INPUT_ERROR);
    } catch (ParseError &error) {
        cerr << error << endl;
        cerr << OptionParser::usage(argv[0]) << endl;
        utils::exit_with(ExitCode::INPUT_ERROR);
    }

    // We offload the solve to PRP's main function
    utils::exit_with(PRP.run_prp(engine));

}
