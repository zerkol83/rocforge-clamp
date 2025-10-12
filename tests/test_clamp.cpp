#include "clamp.h"

#include <cassert>
#include <chrono>
#include <string>
#include <utility>
#include <thread>

int main() {
    {
        clamp::ClampAnchor scopedAnchor("scoped-context");
        auto scopedState = scopedAnchor.status();
        assert(scopedState.state == clamp::AnchorState::Locked);
        assert(scopedState.context == "scoped-context");
        auto scopedSeed = scopedAnchor.entropySeed();
        assert(scopedSeed != 0);
        assert(scopedSeed == scopedState.entropySeed);
    }

    clamp::ClampAnchor anchor;

    const std::string context{"unit-test"};
    anchor.lock(context);

    auto lockedState = anchor.status();
    assert(lockedState.state == clamp::AnchorState::Locked);
    assert(lockedState.context == context);
    assert(anchor.entropySeed() == lockedState.entropySeed);
    assert(anchor.entropySeed() != 0);

    clamp::ClampAnchor movedAnchor = std::move(anchor);
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

    // Lock/unlock cycle reproducibility.
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

    return 0;
}
