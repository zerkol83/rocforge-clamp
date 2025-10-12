#include "clamp.h"

#include <chrono>
#include <functional>
#include <iostream>
#include <thread>
#include <utility>

namespace clamp {

std::uint64_t EntropyTracker::generateSeed() const {
    const auto now = std::chrono::steady_clock::now().time_since_epoch().count();
    const auto tid = std::this_thread::get_id();

    const std::uint64_t clockHash = std::hash<long long>{}(static_cast<long long>(now));
    const std::uint64_t threadHash = std::hash<std::thread::id>{}(tid);

    return clockHash ^ (threadHash << 1);
}

ClampAnchor::ClampAnchor() = default;

ClampAnchor::ClampAnchor(const std::string& ctx) {
    lock(ctx);
}

ClampAnchor::~ClampAnchor() {
    release_internal();
}

ClampAnchor::ClampAnchor(ClampAnchor&& other) noexcept
    : state_(std::move(other.state_)) {
    other.state_.locked = false;
    other.state_.context.clear();
}

ClampAnchor& ClampAnchor::operator=(ClampAnchor&& other) noexcept {
    if (this != &other) {
        release_internal();
        state_ = std::move(other.state_);
        other.state_.locked = false;
        other.state_.context.clear();
    }
    return *this;
}

void ClampAnchor::lock(const std::string& ctx) {
    if (state_.locked) {
        std::cout << "ClampAnchor already locked; updating context to: " << ctx << '\n';
    } else {
        std::cout << "ClampAnchor locking context: " << ctx << '\n';
    }
    state_.locked = true;
    state_.context = ctx;
    state_.entropySeed = tracker_.generateSeed();
    std::cout << "ClampAnchor entropy seed: " << state_.entropySeed << '\n';
}

void ClampAnchor::release() {
    if (!state_.locked) {
        std::cout << "ClampAnchor release requested but anchor is not locked.\n";
    }
    release_internal();
}

void ClampAnchor::release_internal() {
    if (!state_.locked) {
        return;
    }

    std::cout << "ClampAnchor releasing context: " << state_.context << '\n';
    state_.locked = false;
    state_.context.clear();
    state_.entropySeed = 0;
}

AnchorState ClampAnchor::status() const {
    return state_;
}

std::uint64_t ClampAnchor::entropySeed() const {
    return state_.entropySeed;
}

} // namespace clamp
