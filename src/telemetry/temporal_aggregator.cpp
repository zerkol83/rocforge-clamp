#include "clamp/TemporalAggregator.h"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <limits>
#include <numeric>
#include <sstream>
#include <stdexcept>

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
    double timestampMs{std::numeric_limits<double>::quiet_NaN()};
};

double parseIsoTimestampMs(const std::string& value) {
    using namespace std::chrono;
    std::istringstream stream(value);
    sys_time<milliseconds> timePoint{};
    stream >> std::chrono::parse("%FT%TZ", timePoint);
    if (!stream.fail()) {
        return static_cast<double>(timePoint.time_since_epoch().count());
    }

    stream.clear();
    stream.str(value);
    stream >> std::chrono::parse("%FT%T", timePoint);
    if (!stream.fail()) {
        return static_cast<double>(timePoint.time_since_epoch().count());
    }

    return std::numeric_limits<double>::quiet_NaN();
}

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
        if (entry.contains("acquired_at") && entry["acquired_at"].is_string()) {
            record.timestampMs = parseIsoTimestampMs(entry["acquired_at"].get<std::string>());
        }
        if (!std::isfinite(record.timestampMs)) {
            record.timestampMs = static_cast<double>(parsed.size());
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
        auto keyPos = trimmed.find("\"stability_score\"");
        if (keyPos != std::string::npos) {
            const auto pos = trimmed.find(":", keyPos + std::strlen("\"stability_score\""));
            if (pos != std::string::npos) {
                auto token = trimmed.substr(pos + 1);
                std::size_t begin = 0;
                while (begin < token.size() && std::isspace(static_cast<unsigned char>(token[begin]))) {
                    ++begin;
                }
                std::size_t end = token.size();
                while (end > begin && (std::isspace(static_cast<unsigned char>(token[end - 1])) ||
                                       token[end - 1] == ',' || token[end - 1] == '}' || token[end - 1] == ']')) {
                    --end;
                }
                auto cleaned = token.substr(begin, end - begin);
                if (cleaned.empty() || (!std::isdigit(static_cast<unsigned char>(cleaned.front())) &&
                                        cleaned.front() != '-' && cleaned.front() != '+')) {
                    throw std::invalid_argument("Invalid numeric field in telemetry input: '" + token + "'");
                }
                record.stabilityScore = std::stod(cleaned);
            }
        }
        keyPos = trimmed.find("\"duration_ms\"");
        if (keyPos != std::string::npos) {
            const auto pos = trimmed.find(":", keyPos + std::strlen("\"duration_ms\""));
            if (pos != std::string::npos) {
                auto token = trimmed.substr(pos + 1);
                std::size_t begin = 0;
                while (begin < token.size() && std::isspace(static_cast<unsigned char>(token[begin]))) {
                    ++begin;
                }
                std::size_t end = token.size();
                while (end > begin && (std::isspace(static_cast<unsigned char>(token[end - 1])) ||
                                       token[end - 1] == ',' || token[end - 1] == '}' || token[end - 1] == ']')) {
                    --end;
                }
                auto cleaned = token.substr(begin, end - begin);
                if (cleaned.empty() || (!std::isdigit(static_cast<unsigned char>(cleaned.front())) &&
                                        cleaned.front() != '-' && cleaned.front() != '+')) {
                    throw std::invalid_argument("Invalid numeric field in telemetry input: '" + token + "'");
                }
                record.durationMs = std::stod(cleaned);
            }
        }
        if (trimmed.find("}") != std::string::npos && inRecord) {
            inRecord = false;
            record.timestampMs = static_cast<double>(parsed.size());
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

struct RunningStats {
    void add(double value) {
        ++count;
        const double delta = value - mean;
        mean += delta / static_cast<double>(count);
        const double delta2 = value - mean;
        m2 += delta * delta2;
    }

    double variance() const {
        if (count < 2) {
            return 0.0;
        }
        return m2 / static_cast<double>(count - 1);
    }

    double mean{0.0};
    double m2{0.0};
    std::size_t count{0};
};

std::string summaryToJson(const TemporalAggregator::Summary& summary,
                          const std::string& sourceDirectory) {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(6);
    oss << "{";
    oss << "\"source_directory\":\"" << sourceDirectory << "\",";
    oss << "\"session_count\":" << summary.sessionCount << ",";
    oss << "\"mean_stability\":" << summary.meanStability << ",";
    oss << "\"stability_variance\":" << summary.stabilityVariance << ",";
    oss << "\"drift_index\":" << summary.driftIndex;
    oss << "}";
    return oss.str();
}

} // namespace

TemporalAggregator::Summary TemporalAggregator::aggregate(const std::filesystem::path& telemetryDir) {
    Summary summary;
    if (!std::filesystem::exists(telemetryDir)) {
        return summary;
    }

    RunningStats stats;
    double minTimestamp = std::numeric_limits<double>::infinity();
    double maxTimestamp = -std::numeric_limits<double>::infinity();
    double sequentialIndex = 0.0;

    for (const auto& entry : std::filesystem::directory_iterator(telemetryDir)) {
        if (!entry.is_regular_file()) {
            continue;
        }

        const auto records = parseTelemetryFile(entry.path());
        for (const auto& record : records) {
            stats.add(record.stabilityScore);

            double timestamp = record.timestampMs;
            if (!std::isfinite(timestamp)) {
                timestamp = sequentialIndex;
            }

            minTimestamp = std::min(minTimestamp, timestamp);
            maxTimestamp = std::max(maxTimestamp, timestamp);
            sequentialIndex += 1.0;
        }
    }

    summary.sessionCount = stats.count;
    if (stats.count == 0) {
        summary.meanStability = 0.0;
        summary.stabilityVariance = 0.0;
        summary.driftIndex = 0.0;
        return summary;
    }

    summary.meanStability = stats.mean;
    summary.stabilityVariance = stats.variance();
    summary.driftIndex = (stats.count > 1 && std::isfinite(minTimestamp) && std::isfinite(maxTimestamp))
                            ? (maxTimestamp - minTimestamp)
                            : 0.0;

    return summary;
}

bool TemporalAggregator::writeSummary(const Summary& summary,
                                      const std::filesystem::path& outputPath,
                                      const std::string& sourceDirectory) const {
    std::error_code ec;
    const auto parent = outputPath.parent_path();
    if (!parent.empty()) {
        std::filesystem::create_directories(parent, ec);
    }
    std::ofstream out(outputPath);
    if (!out.is_open()) {
        return false;
    }
    out << summaryToJson(summary, sourceDirectory);
    return out.good();
}

} // namespace clamp
