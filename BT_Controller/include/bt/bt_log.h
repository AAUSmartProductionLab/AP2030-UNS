#pragma once

#include <iostream>
#include <sstream>
#include <string>

/// Minimal log-level facade used by the new planner-driven nodes
/// (ExecuteAction / FluentCheck) and supporting AAS infrastructure.
///
/// The level is read once from the environment variable
/// `BT_CONTROLLER_LOG_LEVEL` (one of: debug, info, warn, error). The
/// default is `info`.
namespace bt_log
{
    enum class Level
    {
        Debug = 0,
        Info = 1,
        Warn = 2,
        Error = 3,
    };

    Level current_level();

    inline bool enabled(Level lvl)
    {
        return static_cast<int>(lvl) >= static_cast<int>(current_level());
    }

    inline std::ostream &stream(Level lvl)
    {
        // Errors and warnings go to stderr, info/debug to stdout, so that
        // operators can grep for failures without being drowned by debug
        // output during normal runs.
        return (static_cast<int>(lvl) >= static_cast<int>(Level::Warn))
                   ? std::cerr
                   : std::cout;
    }
} // namespace bt_log

#define BT_LOG(LVL, MSG)                                                             \
    do                                                                               \
    {                                                                                \
        if (bt_log::enabled(bt_log::Level::LVL))                                     \
        {                                                                            \
            bt_log::stream(bt_log::Level::LVL) << "[" #LVL "] " << MSG << std::endl; \
        }                                                                            \
    } while (0)

#define BT_LOG_DEBUG(MSG) BT_LOG(Debug, MSG)
#define BT_LOG_INFO(MSG) BT_LOG(Info, MSG)
#define BT_LOG_WARN(MSG) BT_LOG(Warn, MSG)
#define BT_LOG_ERROR(MSG) BT_LOG(Error, MSG)
