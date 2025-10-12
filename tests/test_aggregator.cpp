#include "clamp/TemporalAggregator.h"

#include <cassert>
#include <chrono>
#include <filesystem>
#include <fstream>

namespace {

std::string makeRecord(double stability, double duration) {
    return "{ \"context\": \"test\", \"seed\": 1, \"thread_id\": \"0\", "
           "\"acquired_at\": \"2025-01-01T00:00:00Z\", "
           "\"released_at\": \"2025-01-01T00:00:01Z\", "
           "\"duration_ms\": " + std::to_string(duration) + ", "
           "\"stability_score\": " + std::to_string(stability) + " }";
}

void writeTelemetryFile(const std::filesystem::path& path,
                        std::initializer_list<std::pair<double, double>> values) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path);
    out << "{ \"records\": [";
    bool first = true;
    for (const auto& [stability, duration] : values) {
        if (!first) {
            out << ", ";
        }
        first = false;
        out << makeRecord(stability, duration);
    }
    out << "] }";
}

} // namespace

int main() {
    const auto baseDir = std::filesystem::current_path() / "telemetry";
    std::error_code ec;
    std::filesystem::remove_all(baseDir, ec);

    writeTelemetryFile(baseDir / "sample_a.json", {{1.0, 5.0}, {0.8, 6.0}});
    writeTelemetryFile(baseDir / "sample_b.json", {{0.6, 4.0}});

    clamp::TemporalAggregator aggregator;
    const auto summary = aggregator.aggregate(baseDir);
    assert(summary.sampleCount == 3);
    assert(summary.stabilityMean > 0.7);
    assert(summary.durationMean > 4.0);

    const auto outputPath = std::filesystem::current_path() / "telemetry_summary.json";
    assert(aggregator.writeSummary(summary, outputPath, baseDir.string()));
    assert(std::filesystem::exists(outputPath));

    std::ifstream in(outputPath);
    assert(in.is_open());
    std::string contents((std::istreambuf_iterator<char>(in)),
                         std::istreambuf_iterator<char>());
    assert(contents.find("\"sample_count\"") != std::string::npos);
    assert(contents.find("\"stability_mean\"") != std::string::npos);

    return 0;
}
