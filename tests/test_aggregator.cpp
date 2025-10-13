#include "clamp/TemporalAggregator.h"

#include <cassert>
#include <chrono>
#include <filesystem>
#include <fstream>

namespace {

void writeTelemetryFile(const std::filesystem::path& path,
                        std::initializer_list<std::pair<double, double>> values) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path);
    out << "{\n  \"records\": [\n";
    bool first = true;
    for (const auto& [stability, duration] : values) {
        if (!first) {
            out << ",\n";
        }
        first = false;
        out << "    {\n"
            << "      \"context\": \"test\",\n"
            << "      \"seed\": 1,\n"
            << "      \"thread_id\": \"0\",\n"
            << "      \"acquired_at\": \"2025-01-01T00:00:00Z\",\n"
            << "      \"released_at\": \"2025-01-01T00:00:01Z\",\n"
            << "      \"duration_ms\": " << duration << ",\n"
            << "      \"stability_score\": " << stability << "\n"
            << "    }";
    }
    out << "\n  ]\n}\n";
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
    assert(summary.sessionCount == 3);
    assert(summary.meanStability > 0.7);
    assert(summary.stabilityVariance >= 0.0);
    assert(summary.driftIndex >= 0.0);

    const auto outputPath = std::filesystem::current_path() / "telemetry_summary.json";
    assert(aggregator.writeSummary(summary, outputPath, baseDir.string()));
    assert(std::filesystem::exists(outputPath));

    std::ifstream in(outputPath);
    assert(in.is_open());
    std::string contents((std::istreambuf_iterator<char>(in)),
                         std::istreambuf_iterator<char>());
    assert(contents.find("\"session_count\"") != std::string::npos);
    assert(contents.find("\"mean_stability\"") != std::string::npos);
    assert(contents.find("\"drift_index\"") != std::string::npos);

    return 0;
}
