#include "clamp/TemporalAggregator.h"

#include <algorithm>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

using clamp::TemporalAggregator;

namespace {

struct InspectOptions {
    bool summaryOnly{false};
    bool sessionsOnly{false};
};

InspectOptions parseArgs(int argc, char* argv[]) {
    InspectOptions options;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--summary") {
            options.summaryOnly = true;
        } else if (arg == "--sessions") {
            options.sessionsOnly = true;
        }
    }
    return options;
}

void printSummary(const TemporalAggregator::Summary& summary) {
    std::cout << "+----------------+-------------+\n";
    std::cout << "| Metric         | Value       |\n";
    std::cout << "+----------------+-------------+\n";
    auto printRow = [](const std::string& label, double value) {
        std::cout << "| " << std::left << std::setw(14) << label << " | " << std::right << std::setw(11)
                  << std::fixed << std::setprecision(4) << value << " |\n";
    };
    printRow("Mean", summary.meanStability);
    printRow("Variance", summary.variance);
    printRow("Drift p95", summary.driftPercentile);
    std::cout << "+----------------+-------------+\n";
    std::cout.unsetf(std::ios::floatfield);
    std::cout << "| Sessions       | " << std::setw(11) << summary.sessionCount << " |\n";
    std::cout << "+----------------+-------------+\n";
}

void printBar(double value, double maxValue) {
    constexpr int width = 30;
    if (maxValue <= 0.0) {
        std::cout << std::string(width, '.');
        return;
    }
    const double ratio = std::clamp(value / maxValue, 0.0, 1.0);
    const int filled = static_cast<int>(ratio * static_cast<double>(width));
    for (int i = 0; i < width; ++i) {
        std::cout << (i < filled ? '#' : '.');
    }
}

void printSessions(const std::vector<TemporalAggregator::SessionDetail>& sessions) {
    if (sessions.empty()) {
        std::cout << "No per-session telemetry detected.\n";
        return;
    }

    double maxMean = 0.0;
    double maxDrift = 0.0;
    for (const auto& session : sessions) {
        maxMean = std::max(maxMean, session.metrics.meanStability);
        maxDrift = std::max(maxDrift, session.metrics.driftPercentile);
    }

    std::cout << "Session breakdown:\n";
    for (const auto& session : sessions) {
        std::cout << session.source.string() << " mean=" << std::fixed << std::setprecision(4)
                  << session.metrics.meanStability << " count=" << session.metrics.sessionCount << '\n';
        std::cout << "  mean  ";
        printBar(session.metrics.meanStability, maxMean);
        std::cout << '\n';
        std::cout << "  drift ";
        printBar(session.metrics.driftPercentile, maxDrift);
        std::cout << " (p95=" << std::fixed << std::setprecision(2) << session.metrics.driftPercentile << ")\n";
    }
}

} // namespace

int main(int argc, char* argv[]) {
    const auto options = parseArgs(argc, argv);

    const std::filesystem::path buildDir = std::filesystem::current_path() / "build";
    const auto summaryPath = buildDir / "telemetry_summary.json";
    const auto telemetryDir = buildDir / "telemetry";

    TemporalAggregator aggregator;
    const auto summary = aggregator.loadSummary(summaryPath);
    const auto sessions = aggregator.loadSessions(telemetryDir);

    if (!options.sessionsOnly) {
        printSummary(summary);
    }
    if (!options.summaryOnly) {
        printSessions(sessions);
    }

    return 0;
}
