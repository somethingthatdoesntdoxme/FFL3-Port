// ffl3.ini beside the game: the front end's settings (window, palette, fast-forward). Plain
// "key = value" lines and '#' comments. Command-line flags override it for one run and aren't
// written back. Keys this build doesn't know are kept and written back unchanged, so a newer
// build's settings survive an older one saving the file.
#pragma once
#include <string>
#include <utility>
#include <vector>

namespace ffl3 {

struct Settings {
    int scale = 5;            // window size, times 160x144
    bool fullscreen = false;
    int palette = 0;
    bool wide = false;        // 256-wide view
    int ffSpeed = 4;          // fast-forward: 2-8 times while held

    bool load(const std::string& path);
    bool save(const std::string& path) const;
    bool operator==(const Settings& o) const {
        return scale == o.scale && fullscreen == o.fullscreen && palette == o.palette && wide == o.wide && ffSpeed == o.ffSpeed;
    }
    bool operator!=(const Settings& o) const { return !(*this == o); }

private:
    std::vector<std::pair<std::string, std::string>> unknown_;
};

} // namespace ffl3
