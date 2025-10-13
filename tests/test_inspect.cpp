#include "clamp/TemporalAggregator.h"

#include <cassert>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>

namespace {

void writeTelemetry(const std::filesystem::path& path, const std::string& payload) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path);
    out << payload;
}

std::string readFile(const std::filesystem::path& path) {
    std::ifstream in(path);
    return std::string((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
}

void ensureCommand(const std::string& command) {
    const int rc = std::system(command.c_str());
    assert(rc == 0);
}

} // namespace

int main() {
    const auto root = std::filesystem::current_path();
    const auto buildDir = root / "build";
    const auto telemetryDir = buildDir / "telemetry";
    const auto summaryPath = buildDir / "telemetry_summary.json";
    const auto summaryDump = buildDir / "inspect_summary.txt";
    const auto sessionsDump = buildDir / "inspect_sessions.txt";

    std::error_code ec;
    std::filesystem::remove_all(telemetryDir, ec);
    std::filesystem::remove(summaryPath, ec);
    std::filesystem::remove(summaryDump, ec);
    std::filesystem::remove(sessionsDump, ec);

    writeTelemetry(telemetryDir / "session_a.json",
                   "{\n"
                   "  \"records\": [\n"
                   "    {\"stability_score\": 0.6, \"duration_ms\": 10.0},\n"
                   "    {\"stability_score\": 0.8, \"duration_ms\": 20.0}\n"
                   "  ]\n"
                   "}\n");
    writeTelemetry(telemetryDir / "session_b.json",
                   "{\n"
                   "  \"records\": [\n"
                   "    {\"stability_score\": 1.0, \"duration_ms\": 30.0},\n"
                   "    {\"context\": \"extra\"}\n"
                   "  ]\n"
                   "}\n");
    writeTelemetry(telemetryDir / "session_bad.json",
                   "{\n"
                   "  \"records\": [\n"
                   "    {\"stability_score\": \"oops\", \"duration_ms\": 15.0}\n"
                   "  ]\n"
                   "}\n");
    writeTelemetry(telemetryDir / "notes.txt", "not json");

    clamp::TemporalAggregator aggregator;
    const auto summary = aggregator.accumulate(root);
    assert(summary.sessionCount == 3);
    assert(std::abs(summary.meanStability - 0.8) < 1e-9);

    ensureCommand("./telemetry_inspect --summary > build/inspect_summary.txt");
    const auto summaryOutput = readFile(summaryDump);
    assert(summaryOutput.find("Backend: unknown  Device: unspecified") != std::string::npos);
    assert(summaryOutput.find("0.8000") != std::string::npos);
    assert(summaryOutput.find("0.0400") != std::string::npos);
    assert(summaryOutput.find("20.0000") != std::string::npos);

    ensureCommand("./telemetry_inspect --sessions > build/inspect_sessions.txt");
    const auto sessionsOutput = readFile(sessionsDump);
    assert(sessionsOutput.find("session_a.json [unknown | unspecified]") != std::string::npos);
    assert(sessionsOutput.find("mean=0.7000") != std::string::npos);

    writeTelemetry(summaryPath, "{ \"meanStability\": 0.75 }");
    ensureCommand("./telemetry_inspect --summary > build/inspect_summary.txt");

    return 0;
}
