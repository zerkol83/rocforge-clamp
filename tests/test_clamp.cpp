#include "clamp.h"
#include <cassert>
#include <chrono>
#include <cstdint>
#include <mutex>
#include <numeric>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace {

void exercise_basic_anchor(clamp::EntropyTelemetry& telemetry) {
    clamp::ClampAnchor scopedAnchor;
    scopedAnchor.attachTelemetry(&telemetry);
    scopedAnchor.lock("scoped-context");

    auto scopedState = scopedAnchor.status();
    assert(scopedState.state == clamp::AnchorState::Locked);
    assert(scopedState.context == "scoped-context");
    auto scopedSeed = scopedAnchor.entropySeed();
    assert(scopedSeed != 0);
    assert(scopedSeed == scopedState.entropySeed);
}

void exercise_move_semantics(clamp::EntropyTelemetry& telemetry) {
    clamp::ClampAnchor anchor;
    anchor.attachTelemetry(&telemetry);

    const std::string context{"unit-test"};
    anchor.lock(context);

    auto lockedState = anchor.status();
    assert(lockedState.state == clamp::AnchorState::Locked);
    assert(lockedState.context == context);
    assert(anchor.entropySeed() == lockedState.entropySeed);
    assert(anchor.entropySeed() != 0);

    clamp::ClampAnchor movedAnchor = std::move(anchor);
    movedAnchor.attachTelemetry(&telemetry);
    auto movedState = movedAnchor.status();
    assert(movedState.state == clamp::AnchorState::Locked);
    assert(movedState.context == context);
    assert(movedAnchor.entropySeed() == movedState.entropySeed);

    auto originalState = anchor.status();
    assert(originalState.state == clamp::AnchorState::Unlocked);
    assert(originalState.context.empty());
    assert(anchor.entropySeed() == 0);

    movedAnchor.release();

    auto releasedState = movedAnchor.status();
    assert(releasedState.state == clamp::AnchorState::Unlocked);
    assert(releasedState.context.empty());
    assert(movedAnchor.entropySeed() == 0);

    movedAnchor.lock("cycle-test");
    const auto firstSeed = movedAnchor.entropySeed();
    assert(firstSeed != 0);

    movedAnchor.release();
    assert(movedAnchor.entropySeed() == 0);

    std::this_thread::sleep_for(std::chrono::milliseconds(1));

    movedAnchor.lock("cycle-test");
    const auto secondSeed = movedAnchor.entropySeed();
    assert(secondSeed != 0);
    const auto repeatSeed = movedAnchor.entropySeed();
    assert(repeatSeed == secondSeed);
    assert(secondSeed == movedAnchor.entropySeed());

    movedAnchor.release();
    assert(movedAnchor.entropySeed() == 0);
}

void exercise_multithreaded_entropy(clamp::EntropyTelemetry& telemetry,
                                    std::vector<std::uint64_t>& seeds,
                                    std::vector<int>& states) {
    constexpr int threadCount = 4;
    std::vector<std::thread> workers;
    std::mutex collectMutex;
    seeds.clear();
    states.clear();

    for (int i = 0; i < threadCount; ++i) {
        workers.emplace_back([i, &telemetry, &collectMutex, &seeds, &states]() {
            clamp::ClampAnchor anchor;
            anchor.attachTelemetry(&telemetry);
            const std::string ctx = "thread-" + std::to_string(i);
            anchor.lock(ctx);

            auto status = anchor.status();
            assert(status.state == clamp::AnchorState::Locked);
            assert(status.entropySeed != 0);

            {
                std::lock_guard<std::mutex> guard(collectMutex);
                seeds.push_back(status.entropySeed);
                states.push_back(static_cast<int>(status.state));
            }

            std::this_thread::sleep_for(std::chrono::milliseconds(2));
            anchor.release();
            assert(anchor.status().state == clamp::AnchorState::Unlocked);
        });
    }

    for (auto& worker : workers) {
        worker.join();
    }

    assert(seeds.size() == states.size());
    assert(seeds.size() == static_cast<std::size_t>(threadCount));

    const auto seedSum = std::accumulate(seeds.begin(), seeds.end(), std::uint64_t{0});
    assert(seedSum != 0);
}

void validate_telemetry(const clamp::EntropyTelemetry& telemetry) {
    const auto records = telemetry.records();
    assert(!records.empty());
    for (const auto& record : records) {
        assert(!record.context.empty());
        assert(record.seed != 0 || record.finalState == clamp::AnchorState::Unlocked);
        assert(record.acquiredAt.time_since_epoch().count() != 0);
        if (record.releasedAt) {
            assert(record.durationMs >= 0.0);
        }
    }

    const std::string json = telemetry.toJson();
    assert(json.find("\"records\"") != std::string::npos);
    assert(json.find("\"seed\"") != std::string::npos);
}

void validate_hip_mirror(const std::vector<std::uint64_t>& seeds,
                         const std::vector<int>& states) {
    assert(clamp::runHipEntropyMirror(seeds, states));
}

} // namespace

int main() {
    clamp::EntropyTelemetry telemetry;
    std::vector<std::uint64_t> seeds;
    std::vector<int> states;

    exercise_basic_anchor(telemetry);
    exercise_move_semantics(telemetry);
    exercise_multithreaded_entropy(telemetry, seeds, states);

    validate_telemetry(telemetry);
    validate_hip_mirror(seeds, states);

    return 0;
}
