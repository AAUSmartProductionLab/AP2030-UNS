#include "bt/bt_log.h"

#include <cctype>
#include <cstdlib>
#include <mutex>

namespace bt_log
{
    namespace
    {
        Level parseLevel(const char *s)
        {
            if (!s)
                return Level::Info;
            std::string v(s);
            for (auto &c : v)
                c = static_cast<char>(::tolower(c));
            if (v == "debug")
                return Level::Debug;
            if (v == "info")
                return Level::Info;
            if (v == "warn" || v == "warning")
                return Level::Warn;
            if (v == "error")
                return Level::Error;
            return Level::Info;
        }
    } // namespace

    Level current_level()
    {
        static std::once_flag init_flag;
        static Level cached = Level::Info;
        std::call_once(init_flag, []
                       { cached = parseLevel(std::getenv("BT_CONTROLLER_LOG_LEVEL")); });
        return cached;
    }
} // namespace bt_log
