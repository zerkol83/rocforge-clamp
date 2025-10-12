#pragma once

#include <cstdint>
#include <string>

namespace clamp {

enum class AnchorState {
    Unlocked,
    Locked,
    Released,
    Error
};

struct AnchorStatus {
    AnchorState state{AnchorState::Unlocked};
    std::string context;
    std::uint64_t entropySeed{0};
};

class EntropyTracker {
public:
    std::uint64_t generateSeed() const;
};

class ClampAnchor {
public:
    ClampAnchor();
    explicit ClampAnchor(const std::string& ctx);
    ~ClampAnchor();

    ClampAnchor(const ClampAnchor&) = delete;
    ClampAnchor& operator=(const ClampAnchor&) = delete;
    ClampAnchor(ClampAnchor&& other) noexcept;
    ClampAnchor& operator=(ClampAnchor&& other) noexcept;

    void lock(const std::string& ctx);
    void release();
    AnchorStatus status() const;
    std::uint64_t entropySeed() const;

private:
    void release_internal(const char* sourceTag);
    void setState(AnchorState newState, const std::string& reason);
    static const char* stateToString(AnchorState state);

    AnchorStatus state_;
    EntropyTracker tracker_;
};

} // namespace clamp
