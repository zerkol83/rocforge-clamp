#pragma once

#include <filesystem>
#include <string>

namespace clamp {

class TemporalAggregator {
public:
    struct Summary {
        double stabilityMean{0.0};
        double stabilityVariance{0.0};
        double durationMean{0.0};
        double durationVariance{0.0};
        double driftMs{0.0};
        std::size_t sampleCount{0};
    };

    TemporalAggregator() = default;
    Summary aggregate(const std::filesystem::path& telemetryDir);
    bool writeSummary(const Summary& summary,
                      const std::filesystem::path& outputPath,
                      const std::string& sourceDirectory) const;

private:
    static Summary combine(const Summary& lhs, const Summary& rhs);
};

} // namespace clamp
