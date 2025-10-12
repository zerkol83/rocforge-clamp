#pragma once

#include "clamp/EntropyTelemetry.h"

#include <string>
#include <vector>

namespace clamp {

struct TemporalScoringResult {
    double stabilityScore{0.0};
    double entropyVariance{0.0};
    double durationVariance{0.0};
    double driftMs{0.0};
    std::size_t sampleCount{0};

    std::string toJson() const;
    std::string toText() const;
};

class TemporalScoring {
public:
    TemporalScoringResult evaluate(const std::vector<AnchorTelemetryRecord>& records) const;
    TemporalScoringResult evaluateAggregated(const std::vector<std::vector<AnchorTelemetryRecord>>& groupedRecords) const;
};

} // namespace clamp
