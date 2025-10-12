#pragma once

#include <string>

namespace clamp {

struct AnchorState {
    bool locked{false};
    std::string context;
};

class ClampAnchor {
public:
    ClampAnchor();

    void lock(const std::string& ctx);
    void release();
    AnchorState status() const;

private:
    AnchorState state_;
};

} // namespace clamp
