#include "clamp/TemporalScoring.h"

#include <cassert>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace {

clamp::AnchorTelemetryRecord makeRecord(std::uint64_t seed,
                                        const std::string& context,
                                        std::chrono::milliseconds offset,
                                        double durationMs) {
    clamp::AnchorTelemetryRecord record;
    record.seed = seed;
    record.context = context;
    record.threadId = context;
    const auto base = std::chrono::system_clock::time_point{} + std::chrono::hours(1);
    record.acquiredAt = base + offset;
    record.releasedAt = record.acquiredAt + std::chrono::milliseconds(static_cast<long long>(durationMs));
    record.finalState = clamp::AnchorState::Unlocked;
    record.durationMs = durationMs;
    return record;
}

} // namespace

int main() {
    clamp::EntropyTelemetry telemetryA;
    std::vector<clamp::AnchorTelemetryRecord> recordsA{
        makeRecord(10, "node-0", std::chrono::milliseconds(0), 5.0),
        makeRecord(10, "node-0", std::chrono::milliseconds(1), 5.0),
        makeRecord(10, "node-0", std::chrono::milliseconds(2), 5.0)};
    telemetryA.mergeRecords(recordsA);

    clamp::EntropyTelemetry telemetryB;
    std::vector<clamp::AnchorTelemetryRecord> recordsB{
        makeRecord(12, "node-1", std::chrono::milliseconds(0), 7.0),
        makeRecord(13, "node-1", std::chrono::milliseconds(3), 7.5)};
    telemetryB.mergeRecords(recordsB);

    const auto reference = std::chrono::system_clock::time_point{} + std::chrono::hours(2);
    telemetryA.alignToReference(reference);
    telemetryB.alignToReference(reference + std::chrono::milliseconds(5));

    const auto outputDir = std::filesystem::current_path() / "telemetry";
    assert(telemetryA.writeJson(outputDir, "unit_a"));
    assert(telemetryB.writeJson(outputDir, "unit_b"));

    clamp::TemporalScoring scoring;
    const auto resultA = scoring.evaluate(telemetryA.records());
    assert(resultA.sampleCount == recordsA.size());
    assert(resultA.entropyVariance == 0.0);
    assert(resultA.stabilityScore > 0.9);

    const auto aggregated = scoring.evaluateAggregated({telemetryA.records(), telemetryB.records()});
    assert(aggregated.sampleCount == recordsA.size() + recordsB.size());
    assert(aggregated.stabilityScore <= 1.0 && aggregated.stabilityScore >= 0.0);

    const std::string jsonSummary = aggregated.toJson();
    assert(jsonSummary.find("stability_score") != std::string::npos);
    assert(jsonSummary.find("samples") != std::string::npos);

    const std::string textSummary = aggregated.toText();
    assert(textSummary.find("Entropy variance") != std::string::npos);

    telemetryA.merge(telemetryB);
    const auto mergedResult = scoring.evaluate(telemetryA.records());
    assert(mergedResult.sampleCount == telemetryA.records().size());

    const std::string repeatJson = aggregated.toJson();
    assert(repeatJson == jsonSummary);

    return 0;
}
