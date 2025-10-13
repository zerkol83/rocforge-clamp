#include "clamp/TelemetryComparator.h"

#include <cassert>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace {

void writeSummary(const std::filesystem::path& path,
                  const std::string& backend,
                  const std::string& device,
                  double mean,
                  double variance,
                  double drift,
                  std::size_t sessions) {
    std::ofstream out(path);
    out << "{"
        << "\"sourceDirectory\":\"build/telemetry\","
        << "\"source_directory\":\"build/telemetry\","
        << "\"backend\":\"" << backend << "\","
        << "\"deviceName\":\"" << device << "\","
        << "\"device_name\":\"" << device << "\","
        << "\"sessionCount\":" << sessions << ","
        << "\"meanStability\":" << mean << ","
        << "\"variance\":" << variance << ","
        << "\"driftPercentile\":" << drift << ","
        << "\"session_count\":" << sessions << ","
        << "\"mean_stability\":" << mean << ","
        << "\"stability_variance\":" << variance << ","
        << "\"drift_index\":" << drift
        << "}";
}

} // namespace

int main() {
    const auto buildDir = std::filesystem::current_path() / "build";
    std::filesystem::create_directories(buildDir);

    const auto cpuPath = buildDir / "telemetry_summary_cpu.json";
    const auto hipPath = buildDir / "telemetry_summary_hip.json";
    const auto outputPath = buildDir / "telemetry_comparison.json";

    writeSummary(cpuPath, "CPU", "host", 0.80, 0.04, 20.0, 10);
    writeSummary(hipPath, "HIP", "gfx1100", 0.78, 0.05, 27.0, 10);

    clamp::TelemetryComparator comparator;
    const auto result = comparator.compare({cpuPath, hipPath}, outputPath);

    assert(result.entries.size() == 2);
    assert(result.entries[0].summary.backend == "CPU");
    assert(result.entries[1].summary.backend == "HIP");
    assert(std::fabs(result.entries[1].meanDelta - (-0.02)) < 1e-9);
    assert(std::fabs(result.entries[1].driftSkew - 7.0) < 1e-9);
    assert(result.entries[1].varianceRatio > 1.0);
    assert(result.entries[1].driftSignificant);
    assert(result.wroteOutput);
    assert(std::filesystem::exists(outputPath));

    std::ifstream in(outputPath);
    std::string comparisonJson((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    assert(comparisonJson.find("\"meanDelta\":-0.02") != std::string::npos);
    assert(comparisonJson.find("\"driftSignificant\":true") != std::string::npos);

    return 0;
}
