#pragma once

#include <chrono>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

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

class EntropyTelemetry;

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
    void attachTelemetry(EntropyTelemetry* telemetry);
    const EntropyTelemetry* telemetry() const;

private:
    void release_internal(const char* sourceTag);
    void setState(AnchorState newState, const std::string& reason);

    AnchorStatus state_;
    EntropyTracker tracker_;
    EntropyTelemetry* telemetry_{nullptr};
    std::optional<std::size_t> activeTelemetryRecord_;
};

bool runHipEntropyMirror(const std::vector<std::uint64_t>& seeds, const std::vector<int>& states);
const char* anchorStateName(AnchorState state);

} // namespace clamp
