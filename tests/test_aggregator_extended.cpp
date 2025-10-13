#include "clamp/TemporalAggregator.h"

#include <cassert>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <initializer_list>
#include <iterator>
#include <string>
#include <utility>

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
            << "      \"stability_score\": " << stability << ",\n"
            << "      \"duration_ms\": " << duration << "\n"
            << "    }";
    }
    out << "\n  ]\n}\n";
}

void writeMalformedTelemetry(const std::filesystem::path& path) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path);
    out << "{ \"records\": [ { \"stability_score\": \"oops\" } ] ";
}

std::string slurpFile(const std::filesystem::path& path) {
    std::ifstream in(path);
    return std::string((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
}

} // namespace

int main() {
    const auto workspace = std::filesystem::current_path();
    const auto buildDir = workspace / "build";
    const auto telemetryDir = buildDir / "telemetry";
    const auto summaryPath = buildDir / "telemetry_summary.json";

    std::error_code ec;
    std::filesystem::remove_all(buildDir, ec);

    writeTelemetryFile(telemetryDir / "session_a.json", {{0.5, 10.0}, {0.7, 20.0}});
    writeTelemetryFile(telemetryDir / "session_b.json", {{0.9, 50.0}});
    writeMalformedTelemetry(telemetryDir / "session_bad.json");
    std::ofstream(telemetryDir / "readme.txt") << "not json";

    clamp::TemporalAggregator aggregator;
    const auto summary = aggregator.accumulate(workspace);

    const double expectedMean = (0.5 + 0.7 + 0.9) / 3.0;
    assert(summary.sessionCount == 3);
    assert(std::abs(summary.meanStability - expectedMean) < 1e-9);
    assert(summary.variance > 0.0);
    assert(summary.stabilityVariance == summary.variance);
    assert(summary.driftPercentile >= 0.0);
    assert(summary.driftIndex == summary.driftPercentile);
    assert(summary.backend == "unknown");
    assert(summary.deviceName == "unspecified");

    assert(std::filesystem::exists(summaryPath));
    const auto firstSnapshot = slurpFile(summaryPath);
    assert(firstSnapshot.find("\"meanStability\"") != std::string::npos);
    assert(firstSnapshot.find("\"variance\"") != std::string::npos);
    assert(firstSnapshot.find("\"sessionCount\"") != std::string::npos);
    assert(firstSnapshot.find("\"mean_stability\"") != std::string::npos);
    assert(firstSnapshot.find("\"backend\"") != std::string::npos);

    const auto repeated = aggregator.accumulate(workspace);
    const auto secondSnapshot = slurpFile(summaryPath);
    assert(secondSnapshot == firstSnapshot);
    assert(std::abs(repeated.meanStability - summary.meanStability) < 1e-12);
    assert(repeated.sessionCount == summary.sessionCount);

    return 0;
}
