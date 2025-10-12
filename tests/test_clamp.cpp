#include "clamp.h"

#include <cassert>
#include <string>
#include <utility>

int main() {
    {
        clamp::ClampAnchor scopedAnchor("scoped-context");
        auto scopedState = scopedAnchor.status();
        assert(scopedState.locked);
        assert(scopedState.context == "scoped-context");
        auto scopedSeed = scopedAnchor.entropySeed();
        assert(scopedSeed != 0);
        assert(scopedSeed == scopedState.entropySeed);
    }

    clamp::ClampAnchor anchor;

    const std::string context{"unit-test"};
    anchor.lock(context);

    auto lockedState = anchor.status();
    assert(lockedState.locked);
    assert(lockedState.context == context);
    assert(anchor.entropySeed() == lockedState.entropySeed);
    assert(anchor.entropySeed() != 0);

    clamp::ClampAnchor movedAnchor = std::move(anchor);
    auto movedState = movedAnchor.status();
    assert(movedState.locked);
    assert(movedState.context == context);
    assert(movedAnchor.entropySeed() == movedState.entropySeed);

    auto originalState = anchor.status();
    assert(!originalState.locked);
    assert(originalState.context.empty());
    assert(anchor.entropySeed() == 0);

    movedAnchor.release();

    auto releasedState = movedAnchor.status();
    assert(!releasedState.locked);
    assert(releasedState.context.empty());
    assert(movedAnchor.entropySeed() == 0);

    return 0;
}
