#include "clamp/TemporalAggregator.h"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <optional>
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
    double stabilityScore{std::numeric_limits<double>::quiet_NaN()};
    double timestampMs{std::numeric_limits<double>::quiet_NaN()};
};

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

double parseIsoTimestampMs(const std::string& value) {
    using namespace std::chrono;
    std::istringstream stream(value);
    sys_time<milliseconds> tp{};
    stream >> std::chrono::parse("%FT%TZ", tp);
    if (!stream.fail()) {
        return static_cast<double>(tp.time_since_epoch().count());
    }
    stream.clear();
    stream.str(value);
    stream >> std::chrono::parse("%FT%T", tp);
    if (!stream.fail()) {
        return static_cast<double>(tp.time_since_epoch().count());
    }
    return std::numeric_limits<double>::quiet_NaN();
}

#if CLAMP_HAS_NLOHMANN_JSON
std::vector<ParsedRecord> parseWithNlohmann(std::istream& stream) {
    nlohmann::json data = nlohmann::json::parse(stream, nullptr, false);
    if (data.is_discarded()) {
        return {};
    }
    const auto* records = data.contains("records") ? data["records"].get_ptr<const nlohmann::json::array_t*>() : nullptr;
    if (records == nullptr) {
        return {};
    }
    std::vector<ParsedRecord> parsed;
    parsed.reserve(records->size());
    for (const auto& entry : *records) {
        ParsedRecord record;
        if (entry.contains("stability_score")) {
            record.stabilityScore = entry["stability_score"].get<double>();
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

std::vector<ParsedRecord> parseFallback(std::istream& stream) {
    std::vector<ParsedRecord> parsed;
    std::string line;
    ParsedRecord record;
    bool inRecord = false;
    while (std::getline(stream, line)) {
        auto trimmed = line;
        trimmed.erase(std::remove_if(trimmed.begin(), trimmed.end(), [](unsigned char ch) {
            return std::isspace(ch);
        }), trimmed.end());
        if (trimmed.find('{') != std::string::npos) {
            inRecord = true;
            record = ParsedRecord{};
        }
        auto keyPos = trimmed.find("\"stability_score\"");
        if (keyPos != std::string::npos) {
            const auto colon = trimmed.find(':', keyPos + std::strlen("\"stability_score\""));
            if (colon != std::string::npos) {
                auto token = trimmed.substr(colon + 1);
                std::size_t begin = 0;
                while (begin < token.size() && std::isspace(static_cast<unsigned char>(token[begin]))) {
                    ++begin;
                }
                std::size_t end = token.size();
                while (end > begin && (std::isspace(static_cast<unsigned char>(token[end - 1])) ||
                                        token[end - 1] == ',' || token[end - 1] == '}' || token[end - 1] == ']')) {
                    --end;
                }
                if (begin < end) {
                    try {
                        record.stabilityScore = std::stod(token.substr(begin, end - begin));
                    } catch (...) {
                    }
                }
            }
        }
        keyPos = trimmed.find("\"acquired_at\"");
        if (keyPos != std::string::npos) {
            const auto colon = trimmed.find(':', keyPos + std::strlen("\"acquired_at\""));
            if (colon != std::string::npos) {
                auto firstQuote = trimmed.find('"', colon);
                auto secondQuote = trimmed.find('"', firstQuote + 1);
                if (firstQuote != std::string::npos && secondQuote != std::string::npos) {
                    record.timestampMs = parseIsoTimestampMs(trimmed.substr(firstQuote + 1, secondQuote - firstQuote - 1));
                }
            }
        }
        if (trimmed.find('}') != std::string::npos && inRecord) {
            inRecord = false;
            if (!std::isfinite(record.timestampMs)) {
                record.timestampMs = static_cast<double>(parsed.size());
            }
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
    return parseWithNlohmann(in);
#else
    return parseFallback(in);
#endif
}

struct BuildInfo {
    std::string image;
    std::string digest;
    std::string resolvedAt;
    std::string policyMode;
    std::string signer;
};

std::optional<BuildInfo> loadBuildInfo(const std::filesystem::path& snapshotPath) {
    if (snapshotPath.empty() || !std::filesystem::exists(snapshotPath)) {
        return std::nullopt;
    }
    std::ifstream in(snapshotPath);
    if (!in.is_open()) {
        return std::nullopt;
    }
#if CLAMP_HAS_NLOHMANN_JSON
    nlohmann::json data = nlohmann::json::parse(in, nullptr, false);
    if (data.is_discarded()) {
        return std::nullopt;
    }
    BuildInfo info;
    info.image = data.value("image", "");
    info.digest = data.value("digest", "");
    info.resolvedAt = data.value("resolved_at", "");
    info.policyMode = data.value("policy_mode", "");
    info.signer = data.value("signer", "");
    if (info.image.empty() && info.digest.empty()) {
        return std::nullopt;
    }
    return info;
#else
    std::string json((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    auto readString = [&json](const std::string& key) -> std::string {
        const auto pos = json.find(key);
        if (pos == std::string::npos) {
            return {};
        }
        const auto colon = json.find(':', pos);
        if (colon == std::string::npos) {
            return {};
        }
        auto firstQuote = json.find('"', colon);
        if (firstQuote == std::string::npos) {
            return {};
        }
        auto secondQuote = json.find('"', firstQuote + 1);
        if (secondQuote == std::string::npos) {
            return {};
        }
        return json.substr(firstQuote + 1, secondQuote - firstQuote - 1);
    };
    BuildInfo info;
    info.image = readString("\"image\"");
    info.digest = readString("\"digest\"");
    info.resolvedAt = readString("\"resolved_at\"");
    info.policyMode = readString("\"policy_mode\"");
    info.signer = readString("\"signer\"");
    if (info.image.empty() && info.digest.empty()) {
        return std::nullopt;
    }
    return info;
#endif
}

std::filesystem::path resolveSnapshotPath(const std::filesystem::path& overridePath) {
    if (!overridePath.empty()) {
        return overridePath;
    }
#ifdef CLAMP_ROCM_SNAPSHOT_JSON
    return std::filesystem::path(CLAMP_ROCM_SNAPSHOT_JSON);
#else
    return {};
#endif
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

    for (const auto& entry : std::filesystem::directory_iterator(telemetryDir)) {
        if (!entry.is_regular_file() || entry.path().extension() != ".json") {
            continue;
        }
        auto records = parseTelemetryFile(entry.path());
        for (const auto& record : records) {
            if (std::isfinite(record.stabilityScore)) {
                stats.add(record.stabilityScore);
            }
            if (std::isfinite(record.timestampMs)) {
                minTimestamp = std::min(minTimestamp, record.timestampMs);
                maxTimestamp = std::max(maxTimestamp, record.timestampMs);
            }
        }
    }

    summary.sessionCount = stats.count;
    summary.meanStability = stats.mean;
    summary.stabilityVariance = stats.variance();
    if (stats.count > 1 && std::isfinite(minTimestamp) && std::isfinite(maxTimestamp)) {
        summary.driftIndex = maxTimestamp - minTimestamp;
    }
    return summary;
}

bool TemporalAggregator::writeSummary(const Summary& summary,
                                      const std::filesystem::path& outputPath,
                                      const std::string& sourceDirectory,
                                      const std::filesystem::path& snapshotPath) const {
    std::error_code ec;
    const auto parent = outputPath.parent_path();
    if (!parent.empty()) {
        std::filesystem::create_directories(parent, ec);
    }

    const auto buildInfo = loadBuildInfo(resolveSnapshotPath(snapshotPath));

    std::ofstream out(outputPath);
    if (!out.is_open()) {
        return false;
    }

    out << std::fixed << std::setprecision(6);
    out << "{";
    out << "\"source_directory\":\"" << sourceDirectory << "\",";
    out << "\"session_count\":" << summary.sessionCount << ",";
    out << "\"mean_stability\":" << summary.meanStability << ",";
    out << "\"stability_variance\":" << summary.stabilityVariance << ",";
    out << "\"drift_index\":" << summary.driftIndex;

    if (buildInfo) {
        out << ",\"build_info\":{";
        out << "\"image\":\"" << buildInfo->image << "\"";
        if (!buildInfo->digest.empty()) {
            out << ",\"digest\":\"" << buildInfo->digest << "\"";
        }
        if (!buildInfo->resolvedAt.empty()) {
            out << ",\"resolved_at\":\"" << buildInfo->resolvedAt << "\"";
        }
        if (!buildInfo->policyMode.empty()) {
            out << ",\"policy_mode\":\"" << buildInfo->policyMode << "\"";
        }
        if (!buildInfo->signer.empty()) {
            out << ",\"signer\":\"" << buildInfo->signer << "\"";
        }
        out << "}";
    }

    out << "}\n";
    return out.good();
}

} // namespace clamp
