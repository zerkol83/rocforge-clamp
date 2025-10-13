#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

namespace clamp {

class TemporalAggregator {
public:
    struct Summary {
        double meanStability{0.0};
        double variance{0.0};
        double driftPercentile{0.0};
        std::size_t sessionCount{0};
        double stabilityVariance{0.0};
        double driftIndex{0.0};
        std::string backend;
        std::string deviceName;
    };

    struct SessionDetail {
        std::filesystem::path source;
        Summary metrics;
    };

    TemporalAggregator() = default;
    Summary aggregate(const std::filesystem::path& telemetryDir);
    Summary accumulate(const std::filesystem::path& workspaceRoot);
    Summary loadSummary(const std::filesystem::path& summaryPath) const;
    std::vector<SessionDetail> loadSessions(const std::filesystem::path& telemetryDir) const;
    bool writeSummary(const Summary& summary,
                      const std::filesystem::path& outputPath,
                      const std::string& sourceDirectory) const;
};

} // namespace clamp
