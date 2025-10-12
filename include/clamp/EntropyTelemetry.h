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

struct AnchorTelemetryRecord {
    std::string context;
    std::uint64_t seed{0};
    std::string threadId;
    std::chrono::system_clock::time_point acquiredAt{};
    std::optional<std::chrono::system_clock::time_point> releasedAt;
    double durationMs{0.0};
    double stabilityScore{0.0};
};

class EntropyTelemetry {
public:
    std::size_t recordAcquire(const std::string& context, std::uint64_t seed);
    void recordRelease(std::size_t recordId,
                       const std::string& context,
                       std::uint64_t seed,
                       double stabilityScore);

    std::string toJson() const;
    std::vector<AnchorTelemetryRecord> records() const;

    void merge(const EntropyTelemetry& other);
    void mergeRecords(const std::vector<AnchorTelemetryRecord>& externalRecords);
    void alignToReference(const std::chrono::system_clock::time_point& reference);

    bool writeJSON(const std::filesystem::path& directory = std::filesystem::path{"telemetry"},
                   const std::string& filenameHint = "clamp_run") const;
    bool writeJson(const std::filesystem::path& directory = std::filesystem::path{"telemetry"},
                   const std::string& filenameHint = "clamp_run") const {
        return writeJSON(directory, filenameHint);
    }

private:
    static std::string formatTime(const std::chrono::system_clock::time_point& tp);
    static std::string threadIdToString(const std::thread::id& threadId);
    static std::string makeFilename(const std::string& hint);

    mutable std::mutex mutex_;
    std::vector<AnchorTelemetryRecord> records_;
};

} // namespace clamp
