#pragma once

#include <chrono>
#include <cstdint>
#include <filesystem>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
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

struct AnchorTelemetryRecord {
    std::uint64_t seed{0};
    std::string context;
    std::string threadId;
    std::chrono::system_clock::time_point acquiredAt{};
    std::optional<std::chrono::system_clock::time_point> releasedAt;
    AnchorState finalState{AnchorState::Unlocked};
    double durationMs{0.0};
};

class EntropyTracker {
public:
    std::uint64_t generateSeed() const;
};

class EntropyTelemetry {
public:
    std::size_t recordAcquire(const AnchorStatus& status, const std::string& ctx);
    void recordRelease(std::size_t recordId, const AnchorStatus& status, const std::string& ctx);
    std::string toJson() const;
    std::vector<AnchorTelemetryRecord> records() const;
    void merge(const EntropyTelemetry& other);
    void mergeRecords(const std::vector<AnchorTelemetryRecord>& externalRecords);
    void alignToReference(const std::chrono::system_clock::time_point& reference);
    bool writeJson(const std::filesystem::path& directory = "/tmp/clamp_telemetry",
                   const std::string& filenameHint = "telemetry") const;

private:
    static std::string formatTime(const std::chrono::system_clock::time_point& tp);
    static std::string threadIdToString(const std::thread::id& threadId);
    static std::string makeFilename(const std::string& hint);

    mutable std::mutex mutex_;
    std::vector<AnchorTelemetryRecord> records_;
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
