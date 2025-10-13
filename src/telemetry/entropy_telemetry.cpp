#include "clamp/EntropyTelemetry.h"

#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <utility>

namespace clamp {

EntropyTelemetry* EntropyTelemetry::activeTelemetry_ = nullptr;

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

std::filesystem::path resolveDirectory(const std::filesystem::path& directory) {
    if (directory.empty()) {
        return std::filesystem::current_path() / "telemetry";
    }
    if (directory.is_absolute()) {
        return directory;
    }
    return std::filesystem::current_path() / directory;
}

} // namespace

std::size_t EntropyTelemetry::recordAcquire(const std::string& context, std::uint64_t seed) {
    AnchorTelemetryRecord record;
    record.context = context;
    record.seed = seed;
    record.threadId = threadIdToString(std::this_thread::get_id());
    record.acquiredAt = std::chrono::system_clock::now();

    setActiveInstance(this);
    std::lock_guard<std::mutex> lock(mutex_);
    if (backend_.empty()) {
        backend_ = "CPU";
    }
    if (deviceName_.empty()) {
        deviceName_ = "host";
    }
    record.backend = backend_;
    record.deviceName = deviceName_;
    records_.push_back(record);
    return records_.size() - 1;
}

void EntropyTelemetry::recordRelease(std::size_t recordId,
                                     const std::string& context,
                                     std::uint64_t seed,
                                     double stabilityScore) {
    const auto now = std::chrono::system_clock::now();

    std::lock_guard<std::mutex> lock(mutex_);
    if (recordId >= records_.size()) {
        return;
    }

    auto& record = records_[recordId];
    record.releasedAt = now;
    record.durationMs = std::chrono::duration<double, std::milli>(now - record.acquiredAt).count();
    record.stabilityScore = stabilityScore;
    record.backend = backend_;
    record.deviceName = deviceName_;
    if (record.context.empty()) {
        record.context = context;
    }
    if (record.seed == 0) {
        record.seed = seed;
    }
}

std::string EntropyTelemetry::toJson() const {
    std::lock_guard<std::mutex> lock(mutex_);

    double scoreSum = 0.0;
    for (const auto& record : records_) {
        scoreSum += record.stabilityScore;
    }
    const double averageScore = records_.empty() ? 0.0 : scoreSum / static_cast<double>(records_.size());

    std::ostringstream oss;
    oss << "{";
    oss << "\"backend\":\"" << escapeJson(backend_) << "\",";
    oss << "\"deviceName\":\"" << escapeJson(deviceName_) << "\",";
    oss << "\"device_name\":\"" << escapeJson(deviceName_) << "\",";
    oss << "\"stability_score\":" << std::fixed << std::setprecision(6) << averageScore << ",";
    oss << std::defaultfloat;
    oss << "\"records\": [";
    for (std::size_t i = 0; i < records_.size(); ++i) {
        if (i > 0) {
            oss << ", ";
        }
        const auto& record = records_[i];
        oss << "{";
        oss << "\"context\":\"" << escapeJson(record.context) << "\",";
        oss << "\"seed\":" << record.seed << ",";
        oss << "\"backend\":\"" << escapeJson(record.backend) << "\",";
        oss << "\"deviceName\":\"" << escapeJson(record.deviceName) << "\",";
        oss << "\"device_name\":\"" << escapeJson(record.deviceName) << "\",";
        oss << "\"thread_id\":\"" << escapeJson(record.threadId) << "\",";
        oss << "\"acquired_at\":\"" << escapeJson(formatTime(record.acquiredAt)) << "\",";
        if (record.releasedAt) {
            oss << "\"released_at\":\"" << escapeJson(formatTime(*record.releasedAt)) << "\",";
        } else {
            oss << "\"released_at\":null,";
        }
        oss << "\"duration_ms\":" << std::fixed << std::setprecision(3) << record.durationMs << ",";
        oss << std::defaultfloat;
        oss << "\"stability_score\":" << record.stabilityScore;
        oss << "}";
    }
    oss << "] }";
    return oss.str();
}

std::vector<AnchorTelemetryRecord> EntropyTelemetry::records() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return records_;
}

void EntropyTelemetry::merge(const EntropyTelemetry& other) {
    if (!other.backend().empty() || !other.deviceName().empty()) {
        setBackendMetadata(other.backend(), other.deviceName());
    }
    mergeRecords(other.records());
}

void EntropyTelemetry::mergeRecords(const std::vector<AnchorTelemetryRecord>& externalRecords) {
    if (externalRecords.empty()) {
        return;
    }

    std::lock_guard<std::mutex> lock(mutex_);
    records_.insert(records_.end(), externalRecords.begin(), externalRecords.end());
}

void EntropyTelemetry::alignToReference(const std::chrono::system_clock::time_point& reference) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (records_.empty()) {
        return;
    }

    std::optional<std::chrono::system_clock::time_point> minTime;
    for (const auto& record : records_) {
        if (record.acquiredAt.time_since_epoch().count() == 0) {
            continue;
        }
        if (!minTime || record.acquiredAt < *minTime) {
            minTime = record.acquiredAt;
        }
    }

    if (!minTime) {
        return;
    }

    const auto delta = reference - *minTime;
    for (auto& record : records_) {
        if (record.acquiredAt.time_since_epoch().count() != 0) {
            record.acquiredAt += delta;
        }
        if (record.releasedAt) {
            record.releasedAt = *record.releasedAt + delta;
        }
    }
}

bool EntropyTelemetry::writeJSON(const std::filesystem::path& directory,
                                 const std::string& filenameHint) const {
    const std::string payload = toJson();
    const auto resolvedDir = resolveDirectory(directory);

    std::error_code ec;
    std::filesystem::create_directories(resolvedDir, ec);
    if (ec) {
        return false;
    }

    const auto filename = makeFilename(filenameHint);
    const auto fullPath = resolvedDir / filename;
    std::ofstream out(fullPath);
    if (!out) {
        return false;
    }
    out << payload;
    return out.good();
}

void EntropyTelemetry::setBackendMetadata(std::string backend, std::string deviceName) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!backend.empty()) {
        backend_ = std::move(backend);
    }
    if (!deviceName.empty()) {
        deviceName_ = std::move(deviceName);
    }
    for (auto& record : records_) {
        record.backend = backend_;
        record.deviceName = deviceName_;
    }
}

void EntropyTelemetry::ensureBackendTag(const std::string& backend, const std::string& deviceName) {
    std::lock_guard<std::mutex> lock(mutex_);
    bool changed = false;
    if (!backend.empty() && backend_ != backend) {
        backend_ = backend;
        changed = true;
    }
    if (!deviceName.empty() && deviceName_ != deviceName) {
        deviceName_ = deviceName;
        changed = true;
    }
    if (changed) {
        for (auto& record : records_) {
            record.backend = backend_;
            record.deviceName = deviceName_;
        }
    }
}

const std::string& EntropyTelemetry::backend() const {
    return backend_;
}

const std::string& EntropyTelemetry::deviceName() const {
    return deviceName_;
}

void EntropyTelemetry::setActiveInstance(EntropyTelemetry* telemetry) {
    activeTelemetry_ = telemetry;
}

EntropyTelemetry* EntropyTelemetry::activeInstance() {
    return activeTelemetry_;
}

std::string EntropyTelemetry::formatTime(const std::chrono::system_clock::time_point& tp) {
    if (tp.time_since_epoch().count() == 0) {
        return "";
    }
    const std::time_t rawTime = std::chrono::system_clock::to_time_t(tp);
    std::tm result{};
#if defined(_WIN32)
    gmtime_s(&result, &rawTime);
#else
    gmtime_r(&rawTime, &result);
#endif

    std::ostringstream oss;
    oss << std::put_time(&result, "%FT%TZ");
    return oss.str();
}

std::string EntropyTelemetry::threadIdToString(const std::thread::id& threadId) {
    std::ostringstream oss;
    oss << threadId;
    return oss.str();
}

std::string EntropyTelemetry::makeFilename(const std::string& hint) {
    const auto now = std::chrono::system_clock::now();
    const std::time_t rawTime = std::chrono::system_clock::to_time_t(now);
    std::tm result{};
#if defined(_WIN32)
    gmtime_s(&result, &rawTime);
#else
    gmtime_r(&rawTime, &result);
#endif

    std::ostringstream oss;
    oss << hint << '_'
        << std::put_time(&result, "%Y%m%dT%H%M%SZ")
        << ".json";
    return oss.str();
}

} // namespace clamp
