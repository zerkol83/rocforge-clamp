#pragma once

#include "clamp/TemporalAggregator.h"

#include <filesystem>
#include <vector>

namespace clamp {

class TelemetryComparator {
public:
    struct Entry {
        std::filesystem::path path;
        TemporalAggregator::Summary summary;
        double meanDelta{0.0};
        double driftSkew{0.0};
        double varianceRatio{1.0};
        bool driftSignificant{false};
    };

    struct Result {
        std::string baselineBackend;
        std::vector<Entry> entries;
        bool wroteOutput{false};
    };

    Result compare(const std::vector<std::filesystem::path>& summaryPaths,
                   const std::filesystem::path& outputPath) const;
};

} // namespace clamp
