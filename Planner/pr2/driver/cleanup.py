from itertools import count
import os

def _try_remove(f):
    try:
        os.remove(f)
    except OSError:
        return False
    return True

def cleanup_temporary_files(args):
    _try_remove("output.sas")
    _try_remove(args.plan_file)
    _try_remove("elapsed.time")
    _try_remove("plan_numbers_and_cost")
    _try_remove("sas_plan")
    _try_remove("STRONG_OUTPUT")
    _try_remove("strong-domain.pddl")

    for i in count(1):
        if not _try_remove("%s.%s" % (args.plan_file, i)):
            break
