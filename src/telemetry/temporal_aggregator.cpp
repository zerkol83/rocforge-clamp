#include "clamp/TemporalAggregator.h"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iterator>
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
    bool hasStability{false};
    bool hasDuration{false};
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
            try {
                if (entry["stability_score"].is_number()) {
                    record.stabilityScore = entry["stability_score"].get<double>();
                    record.hasStability = true;
                } else if (entry["stability_score"].is_string()) {
                    record.stabilityScore = std::stod(entry["stability_score"].get<std::string>());
                    record.hasStability = true;
                }
            } catch (const std::exception&) {
                record.hasStability = false;
            }
        }
        if (entry.contains("duration_ms")) {
            try {
                if (entry["duration_ms"].is_number()) {
                    record.durationMs = entry["duration_ms"].get<double>();
                    record.hasDuration = true;
                } else if (entry["duration_ms"].is_string()) {
                    record.durationMs = std::stod(entry["duration_ms"].get<std::string>());
                    record.hasDuration = true;
                }
            } catch (const std::exception&) {
                record.hasDuration = false;
            }
        }
        if (entry.contains("acquired_at") && entry["acquired_at"].is_string()) {
            record.timestampMs = parseIsoTimestampMs(entry["acquired_at"].get<std::string>());
        }
        if (!std::isfinite(record.timestampMs)) {
            record.timestampMs = static_cast<double>(parsed.size());
        }
        if (record.hasStability) {
            parsed.push_back(record);
        }
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
                try {
                    record.stabilityScore = std::stod(cleaned);
                    record.hasStability = true;
                } catch (const std::exception&) {
                    record.hasStability = false;
                }
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
                try {
                    record.durationMs = std::stod(cleaned);
                    record.hasDuration = true;
                } catch (const std::exception&) {
                    record.hasDuration = false;
                }
            }
        }
        if (trimmed.find("}") != std::string::npos && inRecord) {
            inRecord = false;
            record.timestampMs = static_cast<double>(parsed.size());
            if (record.hasStability) {
                parsed.push_back(record);
            }
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
        if (!std::isfinite(value)) {
            return;
        }
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
    oss << "\"sourceDirectory\":\"" << sourceDirectory << "\",";
    oss << "\"source_directory\":\"" << sourceDirectory << "\",";
    oss << "\"sessionCount\":" << summary.sessionCount << ",";
    oss << "\"meanStability\":" << summary.meanStability << ",";
    oss << "\"variance\":" << summary.variance << ",";
    oss << "\"driftPercentile\":" << summary.driftPercentile << ",";
    oss << "\"session_count\":" << summary.sessionCount << ",";
    oss << "\"mean_stability\":" << summary.meanStability << ",";
    oss << "\"stability_variance\":" << summary.stabilityVariance << ",";
    oss << "\"drift_index\":" << summary.driftIndex;
    oss << "}";
    return oss.str();
}

double computePercentile(std::vector<double>& values, double percentile) {
    if (values.empty()) {
        return 0.0;
    }
    const double clamped = std::clamp(percentile, 0.0, 1.0);
    if (values.size() == 1) {
        return values.front();
    }
    const double scaledIndex = clamped * static_cast<double>(values.size() - 1);
    const auto index = static_cast<std::size_t>(std::floor(scaledIndex));
    auto nth = values.begin() + static_cast<std::ptrdiff_t>(index);
    std::nth_element(values.begin(), nth, values.end());
    return *nth;
}

} // namespace

TemporalAggregator::Summary TemporalAggregator::aggregate(const std::filesystem::path& telemetryDir) {
    Summary summary;
    if (!std::filesystem::exists(telemetryDir)) {
        return summary;
    }

    RunningStats stats;
    std::vector<double> durations;
    durations.reserve(64);

    for (const auto& entry : std::filesystem::directory_iterator(telemetryDir)) {
        if (!entry.is_regular_file()) {
            continue;
        }
        if (entry.path().extension() != ".json") {
            continue;
        }

        std::vector<ParsedRecord> records;
        try {
            records = parseTelemetryFile(entry.path());
        } catch (const std::exception&) {
            continue;
        }

        for (const auto& record : records) {
            if (!record.hasStability || !std::isfinite(record.stabilityScore)) {
                continue;
            }
            stats.add(record.stabilityScore);
            if (record.hasDuration && std::isfinite(record.durationMs) && record.durationMs >= 0.0) {
                durations.push_back(record.durationMs);
            }
        }
    }

    summary.sessionCount = stats.count;
    summary.meanStability = stats.mean;
    summary.variance = stats.variance();
    summary.stabilityVariance = summary.variance;
    summary.driftPercentile = computePercentile(durations, 0.95);
    summary.driftIndex = summary.driftPercentile;

    return summary;
}

TemporalAggregator::Summary TemporalAggregator::accumulate(const std::filesystem::path& workspaceRoot) {
    const auto telemetryDir = workspaceRoot / "build" / "telemetry";
    Summary summary = aggregate(telemetryDir);
    const auto summaryPath = workspaceRoot / "build" / "telemetry_summary.json";
    writeSummary(summary, summaryPath, telemetryDir.string());
    return summary;
}

TemporalAggregator::Summary TemporalAggregator::loadSummary(const std::filesystem::path& summaryPath) const {
    Summary summary;
    std::ifstream in(summaryPath);
    if (!in.is_open()) {
        return summary;
    }
    std::string json((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    auto readValue = [&json](const std::string& key, double& out) {
        const auto keyPos = json.find(key);
        if (keyPos == std::string::npos) {
            return;
        }
        const auto colon = json.find(':', keyPos);
        if (colon == std::string::npos) {
            return;
        }
        const auto end = json.find_first_of(",}", colon + 1);
        const std::string token = json.substr(colon + 1, end != std::string::npos ? end - colon - 1 : std::string::npos);
        try {
            out = std::stod(token);
        } catch (...) {
        }
    };
    readValue("\"meanStability\"", summary.meanStability);
    if (summary.meanStability == 0.0) {
        readValue("\"mean_stability\"", summary.meanStability);
    }
    readValue("\"variance\"", summary.variance);
    if (summary.variance == 0.0) {
        readValue("\"stability_variance\"", summary.variance);
    }
    summary.stabilityVariance = summary.variance;
    readValue("\"driftPercentile\"", summary.driftPercentile);
    if (summary.driftPercentile == 0.0) {
        readValue("\"drift_index\"", summary.driftPercentile);
    }
    summary.driftIndex = summary.driftPercentile;
    double sessionCount = 0.0;
    readValue("\"sessionCount\"", sessionCount);
    if (sessionCount == 0.0) {
        readValue("\"session_count\"", sessionCount);
    }
    summary.sessionCount = static_cast<std::size_t>(sessionCount);
    return summary;
}

std::vector<TemporalAggregator::SessionDetail> TemporalAggregator::loadSessions(const std::filesystem::path& telemetryDir) const {
    std::vector<SessionDetail> sessions;
    if (!std::filesystem::exists(telemetryDir)) {
        return sessions;
    }
    for (const auto& entry : std::filesystem::directory_iterator(telemetryDir)) {
        if (!entry.is_regular_file() || entry.path().extension() != ".json") {
            continue;
        }
        Summary summary;
        RunningStats stats;
        std::vector<double> durations;
        durations.reserve(16);
        std::vector<ParsedRecord> records;
        try {
            records = parseTelemetryFile(entry.path());
        } catch (const std::exception&) {
            continue;
        }
        for (const auto& record : records) {
            if (!record.hasStability || !std::isfinite(record.stabilityScore)) {
                continue;
            }
            stats.add(record.stabilityScore);
            if (record.hasDuration && std::isfinite(record.durationMs) && record.durationMs >= 0.0) {
                durations.push_back(record.durationMs);
            }
        }
        if (stats.count == 0) {
            continue;
        }
        summary.sessionCount = stats.count;
        summary.meanStability = stats.mean;
        summary.variance = stats.variance();
        summary.stabilityVariance = summary.variance;
        summary.driftPercentile = computePercentile(durations, 0.95);
        summary.driftIndex = summary.driftPercentile;
        sessions.push_back(SessionDetail{entry.path().filename(), summary});
    }
    std::sort(sessions.begin(), sessions.end(),
              [](const SessionDetail& lhs, const SessionDetail& rhs) { return lhs.source < rhs.source; });
    return sessions;
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
