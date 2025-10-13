#pragma once

#include <cstddef>
#include <filesystem>
#include <string>

namespace clamp {

class TemporalAggregator {
public:
    struct Summary {
        double meanStability{0.0};
        double stabilityVariance{0.0};
        double driftIndex{0.0};
        std::size_t sessionCount{0};
    };

    TemporalAggregator() = default;
    Summary aggregate(const std::filesystem::path& telemetryDir);
    bool writeSummary(const Summary& summary,
                      const std::filesystem::path& outputPath,
                      const std::string& sourceDirectory) const;
};

} // namespace clamp
