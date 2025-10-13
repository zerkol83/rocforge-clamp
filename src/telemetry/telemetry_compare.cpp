#include "clamp/TelemetryComparator.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <vector>

namespace clamp {

namespace {

std::string escapeJson(const std::string& value) {
    std::ostringstream oss;
    for (const unsigned char ch : value) {
        switch (ch) {
        case '\"':
            oss << "\\\"";
            break;
        case '\\':
            oss << "\\\\";
            break;
        case '\b':
            oss << "\\b";
            break;
        case '\f':
            oss << "\\f";
            break;
        case '\n':
            oss << "\\n";
            break;
        case '\r':
            oss << "\\r";
            break;
        case '\t':
            oss << "\\t";
            break;
        default:
            if (ch < 0x20) {
                oss << "\\u"
                    << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(ch)
                    << std::dec << std::setfill(' ');
            } else {
                oss << static_cast<char>(ch);
            }
            break;
        }
    }
    return oss.str();
}

std::string toLower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return value;
}

bool isCpuBackend(const std::string& backend) {
    const auto lowered = toLower(backend);
    return lowered.find("cpu") != std::string::npos || lowered.find("host") != std::string::npos;
}

constexpr double kDriftSignificanceMs = 5.0;

double computeVarianceRatio(double baselineVariance, double candidateVariance) {
    constexpr double kEpsilon = 1e-12;
    if (baselineVariance <= kEpsilon) {
        if (candidateVariance <= kEpsilon) {
            return 1.0;
        }
        return std::numeric_limits<double>::infinity();
    }
    return candidateVariance / baselineVariance;
}

} // namespace

TelemetryComparator::Result TelemetryComparator::compare(const std::vector<std::filesystem::path>& summaryPaths,
                                                         const std::filesystem::path& outputPath) const {
    Result result;
    if (summaryPaths.empty()) {
        return result;
    }

    TemporalAggregator aggregator;
    std::vector<Entry> entries;
    entries.reserve(summaryPaths.size());

    for (const auto& path : summaryPaths) {
        if (!std::filesystem::is_regular_file(path)) {
            continue;
        }
        Entry entry;
        entry.path = path;
        entry.summary = aggregator.loadSummary(path);
        entries.push_back(entry);
    }

    if (entries.empty()) {
        return result;
    }

    std::size_t baselineIndex = 0;
    for (std::size_t i = 0; i < entries.size(); ++i) {
        if (isCpuBackend(entries[i].summary.backend)) {
            baselineIndex = i;
            break;
        }
    }

    if (baselineIndex != 0) {
        std::swap(entries[0], entries[baselineIndex]);
    }

    const auto baselineSummary = entries[0].summary;
    result.baselineBackend = baselineSummary.backend.empty() ? "unknown" : baselineSummary.backend;

    entries[0].meanDelta = 0.0;
    entries[0].driftSkew = 0.0;
    entries[0].varianceRatio = 1.0;
    entries[0].driftSignificant = false;

    for (std::size_t i = 1; i < entries.size(); ++i) {
        auto& entry = entries[i];
        entry.meanDelta = entry.summary.meanStability - baselineSummary.meanStability;
        entry.driftSkew = entry.summary.driftPercentile - baselineSummary.driftPercentile;
        entry.varianceRatio = computeVarianceRatio(baselineSummary.variance, entry.summary.variance);
        entry.driftSignificant = std::fabs(entry.driftSkew) > kDriftSignificanceMs;
    }

    result.entries = entries;

    if (!outputPath.empty()) {
        std::error_code ec;
        const auto parent = outputPath.parent_path();
        if (!parent.empty()) {
            std::filesystem::create_directories(parent, ec);
        }
        std::ofstream out(outputPath);
        if (out.is_open()) {
            out << "{";
            out << "\"baseline\":{";
            out << "\"backend\":\"" << escapeJson(baselineSummary.backend) << "\",";
            out << "\"deviceName\":\"" << escapeJson(baselineSummary.deviceName) << "\",";
            out << "\"meanStability\":" << baselineSummary.meanStability << ",";
            out << "\"variance\":" << baselineSummary.variance << ",";
            out << "\"driftPercentile\":" << baselineSummary.driftPercentile;
            out << "},";
            out << "\"entries\":[";
            for (std::size_t i = 0; i < entries.size(); ++i) {
                const auto& entry = entries[i];
                if (i > 0) {
                    out << ",";
                }
                out << "{";
                out << "\"path\":\"" << escapeJson(entry.path.string()) << "\",";
                out << "\"backend\":\"" << escapeJson(entry.summary.backend) << "\",";
                out << "\"deviceName\":\"" << escapeJson(entry.summary.deviceName) << "\",";
                out << "\"meanStability\":" << entry.summary.meanStability << ",";
                out << "\"variance\":" << entry.summary.variance << ",";
                out << "\"driftPercentile\":" << entry.summary.driftPercentile << ",";
                out << "\"meanDelta\":" << entry.meanDelta << ",";
                out << "\"driftSkew\":" << entry.driftSkew << ",";
                out << "\"varianceRatio\":" << entry.varianceRatio << ",";
                out << "\"driftSignificant\":" << (entry.driftSignificant ? "true" : "false");
                out << "}";
            }
            out << "]";
            out << "}";
            result.wroteOutput = out.good();
        }
    }

    return result;
}

} // namespace clamp
