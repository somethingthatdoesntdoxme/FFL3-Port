#include "settings.h"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <fstream>

namespace ffl3 {

static std::string trim(const std::string& s) {
    const size_t a = s.find_first_not_of(" \t\r"), b = s.find_last_not_of(" \t\r");
    return a == std::string::npos ? "" : s.substr(a, b - a + 1);
}
static bool truthy(const std::string& v) { return v == "1" || v == "true" || v == "yes" || v == "on"; }

bool Settings::load(const std::string& path) {
    std::ifstream f(path);
    if (!f) return false;
    std::string line;
    while (std::getline(f, line)) {
        if (const size_t h = line.find('#'); h != std::string::npos) line.resize(h);
        const size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        const std::string k = trim(line.substr(0, eq)), v = trim(line.substr(eq + 1));
        if (k.empty()) continue;
        if (k == "scale") scale = std::clamp(std::atoi(v.c_str()), 1, 12);
        else if (k == "fullscreen") fullscreen = truthy(v);
        else if (k == "palette") palette = std::max(0, std::atoi(v.c_str()));
        else if (k == "wide") wide = truthy(v);
        else if (k == "fast_forward") ffSpeed = std::clamp(std::atoi(v.c_str()), 2, 8);
        else unknown_.push_back({k, v});
    }
    return true;
}

bool Settings::save(const std::string& path) const {
    FILE* f = std::fopen(path.c_str(), "w");
    if (!f) return false;
    std::fprintf(f, "# FFL3 port settings. Command-line flags override these for one run.\n");
    std::fprintf(f, "scale = %d          # window size, times 160x144\n", scale);
    std::fprintf(f, "fullscreen = %s  # Alt+Enter / F6\n", fullscreen ? "true" : "false");
    std::fprintf(f, "palette = %d        # P cycles\n", palette);
    std::fprintf(f, "wide = %s        # Tab: 256-wide view\n", wide ? "true" : "false");
    std::fprintf(f, "fast_forward = %d   # speed while ` (backquote) or the right shoulder/trigger is held, 2-8\n", ffSpeed);
    for (const auto& [k, v] : unknown_) std::fprintf(f, "%s = %s\n", k.c_str(), v.c_str());
    return std::fclose(f) == 0;
}

} // namespace ffl3
