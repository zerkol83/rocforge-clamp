#pragma once

#include <cstdint>
#include <string>

namespace clamp {

struct AnchorState {
    bool locked{false};
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
    AnchorState status() const;
    std::uint64_t entropySeed() const;

private:
    void release_internal();

    AnchorState state_;
    EntropyTracker tracker_;
};

} // namespace clamp
