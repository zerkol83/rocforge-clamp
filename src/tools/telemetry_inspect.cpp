#include "clamp/TelemetryComparator.h"
#include "clamp/TemporalAggregator.h"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

using clamp::TemporalAggregator;
using clamp::TelemetryComparator;

namespace {

struct InspectOptions {
    bool summaryOnly{false};
    bool sessionsOnly{false};
    std::string comparePattern;
};

InspectOptions parseArgs(int argc, char* argv[]) {
    InspectOptions options;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--summary") {
            options.summaryOnly = true;
        } else if (arg == "--sessions") {
            options.sessionsOnly = true;
        } else if (arg == "--compare" && i + 1 < argc) {
            options.comparePattern = argv[++i];
        }
    }
    return options;
}

bool wildcardMatch(const std::string& pattern, const std::string& value) {
    std::size_t patternIndex = 0;
    std::size_t valueIndex = 0;
    std::size_t star = std::string::npos;
    std::size_t match = 0;

    while (valueIndex < value.size()) {
        if (patternIndex < pattern.size() &&
            (pattern[patternIndex] == '?' || pattern[patternIndex] == value[valueIndex])) {
            ++patternIndex;
            ++valueIndex;
        } else if (patternIndex < pattern.size() && pattern[patternIndex] == '*') {
            star = patternIndex++;
            match = valueIndex;
        } else if (star != std::string::npos) {
            patternIndex = star + 1;
            valueIndex = ++match;
        } else {
            return false;
        }
    }

    while (patternIndex < pattern.size() && pattern[patternIndex] == '*') {
        ++patternIndex;
    }

    return patternIndex == pattern.size();
}

std::vector<std::filesystem::path> expandPattern(const std::string& pattern) {
    std::vector<std::filesystem::path> paths;
    if (pattern.empty()) {
        return paths;
    }

    std::filesystem::path patternPath(pattern);
    auto directory = patternPath.parent_path();
    std::string filenamePattern = patternPath.filename().string();

    const bool hasWildcard = filenamePattern.find_first_of("*") != std::string::npos ||
                             filenamePattern.find_first_of('?') != std::string::npos;

    std::filesystem::path baseDir;
    if (directory.empty()) {
        baseDir = std::filesystem::current_path();
    } else if (directory.is_absolute()) {
        baseDir = directory;
    } else {
        baseDir = std::filesystem::current_path() / directory;
    }

    if (!hasWildcard) {
        const auto candidate = baseDir / filenamePattern;
        if (std::filesystem::exists(candidate)) {
            paths.push_back(std::filesystem::weakly_canonical(candidate));
        }
        return paths;
    }

    if (!std::filesystem::exists(baseDir)) {
        return paths;
    }

    for (const auto& entry : std::filesystem::directory_iterator(baseDir)) {
        if (!entry.is_regular_file()) {
            continue;
        }
        const auto name = entry.path().filename().string();
        if (wildcardMatch(filenamePattern, name)) {
            paths.push_back(std::filesystem::weakly_canonical(entry.path()));
        }
    }
    std::sort(paths.begin(), paths.end());
    return paths;
}

std::string formatDouble(double value, int precision) {
    std::ostringstream oss;
    if (std::isfinite(value)) {
        oss << std::fixed << std::setprecision(precision) << value;
    } else {
        oss << "inf";
    }
    return oss.str();
}

void printComparison(const TelemetryComparator::Result& result) {
    if (result.entries.empty()) {
        std::cout << "No comparison entries loaded.\n";
        return;
    }

    double bestMean = 0.0;
    for (const auto& entry : result.entries) {
        bestMean = std::max(bestMean, entry.summary.meanStability);
    }

    std::cout << "Comparison (baseline: " << result.baselineBackend << ")\n";
    std::cout << "+----------------+---------+---------+-----------+---------+---------+---------+-------+\n";
    std::cout << "| Backend        | Mean    | ΔMean   | Drift p95 | Drift Δ | Var     | Var x   | Trend |\n";
    std::cout << "+----------------+---------+---------+-----------+---------+---------+---------+-------+\n";

    for (const auto& entry : result.entries) {
        const bool isBest = entry.summary.meanStability >= bestMean - 1e-9;
        const char* arrow = isBest ? "\u2191" : "\u2193";
        std::string driftDelta = formatDouble(entry.driftSkew, 4);
        if (entry.driftSignificant) {
            driftDelta += '*';
        }
        std::string backendLabel = entry.summary.backend + "/" + entry.summary.deviceName;
        if (backendLabel.size() > 14) {
            backendLabel.resize(14);
        }
        std::cout << "| " << std::left << std::setw(14)
                  << backendLabel << " | "
                  << std::right << std::setw(7) << formatDouble(entry.summary.meanStability, 4) << " | "
                  << std::setw(7) << formatDouble(entry.meanDelta, 4) << " | "
                  << std::setw(9) << formatDouble(entry.summary.driftPercentile, 4) << " | "
                  << std::setw(7) << driftDelta << " | "
                  << std::setw(7) << formatDouble(entry.summary.variance, 4) << " | "
                  << std::setw(7) << formatDouble(entry.varianceRatio, 2) << " | "
                  << std::setw(5) << arrow << " |\n";
    }
    std::cout << "+----------------+---------+---------+-----------+---------+---------+---------+-------+\n";
    std::cout << "(*) drift delta exceeds ±5 ms threshold\n";
}

void printSummary(const TemporalAggregator::Summary& summary) {
    std::cout << "Backend: " << summary.backend
              << "  Device: " << summary.deviceName << "\n";
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
        std::cout << session.source.string() << " [" << session.metrics.backend << " | "
                  << session.metrics.deviceName << "] mean=" << std::fixed << std::setprecision(4)
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

    if (!options.comparePattern.empty()) {
        const auto comparePaths = expandPattern(options.comparePattern);
        if (comparePaths.empty()) {
            std::cout << "No files matched pattern '" << options.comparePattern << "'.\n";
        } else {
            TelemetryComparator comparator;
            const auto comparisonOutput = buildDir / "telemetry_comparison.json";
            const auto result = comparator.compare(comparePaths, comparisonOutput);
            printComparison(result);
            if (result.wroteOutput) {
                std::cout << "Comparison written to " << comparisonOutput << "\n";
            }
        }
    }

    return 0;
}
