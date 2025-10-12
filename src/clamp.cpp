#include "clamp.h"

#include <cassert>
#include <chrono>
#include <ctime>
#include <functional>
#include <iomanip>
#include <iostream>
#include <thread>
#include <utility>

namespace clamp {

namespace {
std::tm toLocalTime(const std::chrono::system_clock::time_point& tp) {
    const std::time_t rawTime = std::chrono::system_clock::to_time_t(tp);
    std::tm result{};
#if defined(_WIN32)
    localtime_s(&result, &rawTime);
#else
    localtime_r(&rawTime, &result);
#endif
    return result;
}
} // namespace

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
    release_internal("~ClampAnchor");
}

ClampAnchor::ClampAnchor(ClampAnchor&& other) noexcept
    : state_(std::move(other.state_)) {
    other.state_ = {};
}

ClampAnchor& ClampAnchor::operator=(ClampAnchor&& other) noexcept {
    if (this != &other) {
        release_internal("operator=");
        state_ = std::move(other.state_);
        other.state_ = {};
    }
    return *this;
}

void ClampAnchor::lock(const std::string& ctx) {
    if (state_.state == AnchorState::Locked) {
        setState(AnchorState::Error, "Double-lock attempt for context '" + ctx + '\'');
        assert(false && "ClampAnchor double-lock detected");
        return;
    }

    if (state_.state == AnchorState::Error) {
        assert(false && "ClampAnchor is in error state and cannot be locked");
        return;
    }

    state_.context = ctx;
    state_.entropySeed = tracker_.generateSeed();
    setState(AnchorState::Locked,
             "Lock acquired for context '" + ctx + "', seed " + std::to_string(state_.entropySeed));
}

void ClampAnchor::release() {
    if (state_.state != AnchorState::Locked) {
        setState(AnchorState::Error, "Release attempted while not locked");
        assert(false && "ClampAnchor release called when not locked");
        return;
    }
    release_internal("release()");
}

void ClampAnchor::release_internal(const char* sourceTag) {
    if (state_.state != AnchorState::Locked) {
        return;
    }

    const std::string ctx = state_.context;
    setState(AnchorState::Released,
             std::string(sourceTag) + " releasing context '" + ctx + '\'');
    state_.context.clear();
    state_.entropySeed = 0;
    setState(AnchorState::Unlocked,
             std::string(sourceTag) + " anchor reset to unlocked");
}

AnchorStatus ClampAnchor::status() const {
    return state_;
}

std::uint64_t ClampAnchor::entropySeed() const {
    return state_.entropySeed;
}

void ClampAnchor::setState(AnchorState newState, const std::string& reason) {
    if (newState == state_.state) {
        return;
    }

    const auto now = std::chrono::system_clock::now();
    const std::tm local = toLocalTime(now);

    std::cout << "[ClampAnchor] " << stateToString(state_.state)
              << " -> " << stateToString(newState)
              << " @ " << std::put_time(&local, "%F %T")
              << " | " << reason << '\n';

    state_.state = newState;
}

const char* ClampAnchor::stateToString(AnchorState state) {
    switch (state) {
    case AnchorState::Unlocked:
        return "Unlocked";
    case AnchorState::Locked:
        return "Locked";
    case AnchorState::Released:
        return "Released";
    case AnchorState::Error:
        return "Error";
    default:
        return "Unknown";
    }
}

} // namespace clamp
