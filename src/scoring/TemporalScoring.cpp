#include "clamp/TemporalScoring.h"

#include <algorithm>
#include <cmath>
#include <numeric>
#include <iomanip>
#include <optional>
#include <sstream>

namespace clamp {

namespace {

double computeNormalizedVariance(const std::vector<double>& values) {
    if (values.size() < 2) {
        return 0.0;
    }

    const double mean = std::accumulate(values.begin(), values.end(), 0.0) / static_cast<double>(values.size());
    double sumSq = 0.0;
    for (const double value : values) {
        const double diff = value - mean;
        sumSq += diff * diff;
    }

    const double variance = sumSq / static_cast<double>(values.size() - 1);
    const double scale = std::abs(mean) + 1.0;
    return variance / (scale * scale);
}

double maxDriftMs(const std::vector<AnchorTelemetryRecord>& records) {
    if (records.empty()) {
        return 0.0;
    }

    std::optional<std::chrono::system_clock::time_point> minTs;
    std::optional<std::chrono::system_clock::time_point> maxTs;
    for (const auto& record : records) {
        if (record.acquiredAt.time_since_epoch().count() == 0) {
            continue;
        }
        if (!minTs || record.acquiredAt < *minTs) {
            minTs = record.acquiredAt;
        }
        if (!maxTs || record.acquiredAt > *maxTs) {
            maxTs = record.acquiredAt;
        }
    }
    if (!minTs || !maxTs) {
        return 0.0;
    }
    return std::chrono::duration<double, std::milli>(*maxTs - *minTs).count();
}

double clamp01(double value) {
    if (value < 0.0) {
        return 0.0;
    }
    if (value > 1.0) {
        return 1.0;
    }
    return value;
}

} // namespace

TemporalScoringResult TemporalScoring::evaluate(const std::vector<AnchorTelemetryRecord>& records) const {
    TemporalScoringResult result;
    result.sampleCount = records.size();
    if (records.empty()) {
        result.stabilityScore = 1.0;
        return result;
    }

    std::vector<double> seedValues;
    seedValues.reserve(records.size());
    std::vector<double> durations;
    durations.reserve(records.size());
    for (const auto& record : records) {
        seedValues.push_back(static_cast<double>(record.seed));
        durations.push_back(record.durationMs);
    }

    result.entropyVariance = clamp01(computeNormalizedVariance(seedValues));
    result.durationVariance = clamp01(computeNormalizedVariance(durations));
    result.driftMs = std::abs(maxDriftMs(records));

    const double driftComponent = clamp01(result.driftMs / 1000.0);
    const double penalty = (result.entropyVariance + result.durationVariance + driftComponent) / 3.0;
    result.stabilityScore = clamp01(1.0 - penalty);

    return result;
}

TemporalScoringResult TemporalScoring::evaluateAggregated(
    const std::vector<std::vector<AnchorTelemetryRecord>>& groupedRecords) const {
    TemporalScoringResult aggregate;
    if (groupedRecords.empty()) {
        aggregate.stabilityScore = 1.0;
        return aggregate;
    }

    double stabilitySum = 0.0;
    double entropySum = 0.0;
    double durationSum = 0.0;
    double driftSum = 0.0;

    for (const auto& group : groupedRecords) {
        const auto groupResult = evaluate(group);
        stabilitySum += groupResult.stabilityScore;
        entropySum += groupResult.entropyVariance;
        durationSum += groupResult.durationVariance;
        driftSum += groupResult.driftMs;
        aggregate.sampleCount += groupResult.sampleCount;
    }

    const double count = static_cast<double>(groupedRecords.size());
    aggregate.stabilityScore = stabilitySum / count;
    aggregate.entropyVariance = entropySum / count;
    aggregate.durationVariance = durationSum / count;
    aggregate.driftMs = driftSum / count;

    return aggregate;
}

std::string TemporalScoringResult::toJson() const {
    std::ostringstream oss;
    oss << "{";
    oss << "\"stability_score\":" << std::fixed << std::setprecision(6) << stabilityScore << ",";
    oss << std::defaultfloat;
    oss << "\"entropy_variance\":" << entropyVariance << ","
        << "\"duration_variance\":" << durationVariance << ","
        << "\"drift_ms\":" << driftMs << ","
        << "\"samples\":" << sampleCount
        << "}";
    return oss.str();
}

std::string TemporalScoringResult::toText() const {
    std::ostringstream oss;
    oss << "Samples: " << sampleCount
        << ", Stability score: " << stabilityScore
        << ", Entropy variance: " << entropyVariance
        << ", Duration variance: " << durationVariance
        << ", Drift (ms): " << driftMs;
    return oss.str();
}

} // namespace clamp
