#include "clamp.h"

#include <ctime>
#include <iomanip>
#include <sstream>

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

} // namespace

std::size_t EntropyTelemetry::recordAcquire(const AnchorStatus& status, const std::string& ctx) {
    AnchorTelemetryRecord record;
    record.context = ctx;
    record.seed = status.entropySeed;
    record.threadId = threadIdToString(std::this_thread::get_id());
    record.acquiredAt = std::chrono::system_clock::now();
    record.finalState = status.state;

    std::lock_guard<std::mutex> lock(mutex_);
    records_.push_back(record);
    return records_.size() - 1;
}

void EntropyTelemetry::recordRelease(std::size_t recordId, const AnchorStatus& status, const std::string& ctx) {
    const auto now = std::chrono::system_clock::now();

    std::lock_guard<std::mutex> lock(mutex_);
    if (recordId >= records_.size()) {
        return;
    }

    auto& record = records_[recordId];
    record.releasedAt = now;
    record.finalState = status.state;
    record.durationMs = std::chrono::duration<double, std::milli>(now - record.acquiredAt).count();
    if (record.context.empty()) {
        record.context = ctx;
    }
    if (record.seed == 0) {
        record.seed = status.entropySeed;
    }
}

std::string EntropyTelemetry::toJson() const {
    std::lock_guard<std::mutex> lock(mutex_);

    std::ostringstream oss;
    oss << "{ \"records\": [";
    for (std::size_t i = 0; i < records_.size(); ++i) {
        if (i > 0) {
            oss << ", ";
        }
        const auto& record = records_[i];
        oss << "{";
        oss << "\"context\":\"" << escapeJson(record.context) << "\",";
        oss << "\"seed\":" << record.seed << ",";
        oss << "\"thread_id\":\"" << escapeJson(record.threadId) << "\",";
        oss << "\"acquired_at\":\"" << escapeJson(formatTime(record.acquiredAt)) << "\",";
        if (record.releasedAt) {
            oss << "\"released_at\":\"" << escapeJson(formatTime(*record.releasedAt)) << "\",";
        } else {
            oss << "\"released_at\":null,";
        }
        oss << "\"duration_ms\":" << std::fixed << std::setprecision(3) << record.durationMs << ",";
        oss << std::defaultfloat;
        oss << "\"final_state\":\"" << anchorStateName(record.finalState) << "\"";
        oss << "}";
    }
    oss << "] }";
    return oss.str();
}

std::vector<AnchorTelemetryRecord> EntropyTelemetry::records() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return records_;
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

} // namespace clamp
