#include "clamp.h"

#include <iostream>

namespace clamp {

ClampAnchor::ClampAnchor() = default;

void ClampAnchor::lock(const std::string& ctx) {
    if (state_.locked) {
        std::cout << "ClampAnchor already locked; updating context to: " << ctx << '\n';
    } else {
        std::cout << "ClampAnchor locking context: " << ctx << '\n';
    }
    state_.locked = true;
    state_.context = ctx;
}

void ClampAnchor::release() {
    if (!state_.locked) {
        std::cout << "ClampAnchor release requested but anchor is not locked.\n";
        return;
    }

    std::cout << "ClampAnchor releasing context: " << state_.context << '\n';
    state_.locked = false;
    state_.context.clear();
}

AnchorState ClampAnchor::status() const {
    return state_;
}

} // namespace clamp
