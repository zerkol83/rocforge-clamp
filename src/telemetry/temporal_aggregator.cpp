#include "clamp/TemporalAggregator.h"

#include "clamp/EntropyTelemetry.h"

#include <algorithm>
#include <fstream>
#include <limits>
#include <numeric>
#include <sstream>

#if __has_include(<nlohmann/json.hpp>)
#include <nlohmann/json.hpp>
#define CLAMP_HAS_NLOHMANN_JSON 1
#else
#define CLAMP_HAS_NLOHMANN_JSON 0
#endif

namespace clamp {

namespace {

struct ParsedRecord {
    double stabilityScore{0.0};
    double durationMs{0.0};
    double acquiredMs{0.0};
};

#if CLAMP_HAS_NLOHMANN_JSON

std::vector<ParsedRecord> parseJsonWithNlohmann(std::istream& stream) {
    nlohmann::json data = nlohmann::json::parse(stream, nullptr, false);
    if (data.is_discarded()) {
        return {};
    }

    std::vector<ParsedRecord> parsed;
    if (!data.contains("records") || !data["records"].is_array()) {
        return parsed;
    }

    for (const auto& entry : data["records"]) {
        ParsedRecord record;
        if (entry.contains("stability_score")) {
            record.stabilityScore = entry["stability_score"].get<double>();
        }
        if (entry.contains("duration_ms")) {
            record.durationMs = entry["duration_ms"].get<double>();
        }
        if (entry.contains("acquired_at")) {
            // attempt to parse ISO string into milliseconds by relying on order
            // this will be refined later with a dedicated parser
            record.acquiredMs = static_cast<double>(parsed.size());
        }
        parsed.push_back(record);
    }
    return parsed;
}

#endif

std::vector<ParsedRecord> parseJsonFallback(std::istream& stream) {
    std::vector<ParsedRecord> parsed;
    std::string line;
    ParsedRecord record;
    bool inRecord = false;
    while (std::getline(stream, line)) {
        auto trimmed = line;
        trimmed.erase(std::remove_if(trimmed.begin(), trimmed.end(), ::isspace), trimmed.end());
        if (trimmed.find("{") != std::string::npos) {
            inRecord = true;
            record = ParsedRecord{};
        }
        if (trimmed.find("\"stability_score\"") != std::string::npos) {
            const auto pos = trimmed.find(":");
            if (pos != std::string::npos) {
                record.stabilityScore = std::stod(trimmed.substr(pos + 1));
            }
        }
        if (trimmed.find("\"duration_ms\"") != std::string::npos) {
            const auto pos = trimmed.find(":");
            if (pos != std::string::npos) {
                record.durationMs = std::stod(trimmed.substr(pos + 1));
            }
        }
        if (trimmed.find("}") != std::string::npos && inRecord) {
            inRecord = false;
            parsed.push_back(record);
        }
    }
    return parsed;
}

std::vector<ParsedRecord> parseTelemetryFile(const std::filesystem::path& path) {
    std::ifstream in(path);
    if (!in.is_open()) {
        return {};
    }
#if CLAMP_HAS_NLOHMANN_JSON
    return parseJsonWithNlohmann(in);
#else
    return parseJsonFallback(in);
#endif
}

double computeMean(const std::vector<double>& values) {
    if (values.empty()) {
        return 0.0;
    }
    return std::accumulate(values.begin(), values.end(), 0.0) / static_cast<double>(values.size());
}

double computeVariance(const std::vector<double>& values, double mean) {
    if (values.size() < 2) {
        return 0.0;
    }
    double variance = 0.0;
    for (const double value : values) {
        const double diff = value - mean;
        variance += diff * diff;
    }
    return variance / static_cast<double>(values.size() - 1);
}

double computeDrift(const std::vector<ParsedRecord>& records) {
    if (records.size() < 2) {
        return 0.0;
    }
    double minIndex = std::numeric_limits<double>::max();
    double maxIndex = std::numeric_limits<double>::lowest();
    for (std::size_t i = 0; i < records.size(); ++i) {
        const double value = static_cast<double>(i);
        minIndex = std::min(minIndex, value);
        maxIndex = std::max(maxIndex, value);
    }
    return maxIndex - minIndex;
}

TemporalAggregator::Summary makeSummary(const std::vector<ParsedRecord>& records) {
    TemporalAggregator::Summary summary;
    if (records.empty()) {
        return summary;
    }

    std::vector<double> stability;
    std::vector<double> duration;
    stability.reserve(records.size());
    duration.reserve(records.size());

    for (const auto& record : records) {
        stability.push_back(record.stabilityScore);
        duration.push_back(record.durationMs);
    }

    summary.stabilityMean = computeMean(stability);
    summary.stabilityVariance = computeVariance(stability, summary.stabilityMean);
    summary.durationMean = computeMean(duration);
    summary.durationVariance = computeVariance(duration, summary.durationMean);
    summary.driftMs = computeDrift(records);
    summary.sampleCount = records.size();
    return summary;
}

std::string summaryToJson(const TemporalAggregator::Summary& summary,
                          const std::string& sourceDirectory) {
    std::ostringstream oss;
    oss << "{";
    oss << "\"source_directory\":\"" << sourceDirectory << "\",";
    oss << "\"sample_count\":" << summary.sampleCount << ",";
    oss << "\"stability_mean\":" << summary.stabilityMean << ",";
    oss << "\"stability_variance\":" << summary.stabilityVariance << ",";
    oss << "\"duration_mean\":" << summary.durationMean << ",";
    oss << "\"duration_variance\":" << summary.durationVariance << ",";
    oss << "\"drift_ms\":" << summary.driftMs;
    oss << "}";
    return oss.str();
}

} // namespace

TemporalAggregator::Summary TemporalAggregator::combine(const Summary& lhs, const Summary& rhs) {
    Summary combined;
    combined.sampleCount = lhs.sampleCount + rhs.sampleCount;
    if (combined.sampleCount == 0) {
        return combined;
    }

    const double lhsWeight = static_cast<double>(lhs.sampleCount);
    const double rhsWeight = static_cast<double>(rhs.sampleCount);

    combined.stabilityMean = (lhs.stabilityMean * lhsWeight + rhs.stabilityMean * rhsWeight) /
                             static_cast<double>(combined.sampleCount);
    combined.durationMean = (lhs.durationMean * lhsWeight + rhs.durationMean * rhsWeight) /
                            static_cast<double>(combined.sampleCount);

    combined.stabilityVariance = lhs.stabilityVariance + rhs.stabilityVariance;
    combined.durationVariance = lhs.durationVariance + rhs.durationVariance;
    combined.driftMs = std::max(lhs.driftMs, rhs.driftMs);

    return combined;
}

TemporalAggregator::Summary TemporalAggregator::aggregate(const std::filesystem::path& telemetryDir) {
    Summary summary;
    summary.sampleCount = 0;

    if (!std::filesystem::exists(telemetryDir)) {
        return summary;
    }

    for (const auto& entry : std::filesystem::directory_iterator(telemetryDir)) {
        if (!entry.is_regular_file()) {
            continue;
        }
        const auto records = parseTelemetryFile(entry.path());
        const auto localSummary = makeSummary(records);
        summary = combine(summary, localSummary);
    }

    return summary;
}

bool TemporalAggregator::writeSummary(const Summary& summary,
                                      const std::filesystem::path& outputPath,
                                      const std::string& sourceDirectory) const {
    std::error_code ec;
    std::filesystem::create_directories(outputPath.parent_path(), ec);
    std::ofstream out(outputPath);
    if (!out.is_open()) {
        return false;
    }
    out << summaryToJson(summary, sourceDirectory);
    return out.good();
}

} // namespace clamp
