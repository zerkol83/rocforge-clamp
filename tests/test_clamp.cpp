#include "clamp.h"

#include <cassert>
#include <string>

int main() {
    clamp::ClampAnchor anchor;

    const std::string context{"unit-test"};
    anchor.lock(context);

    auto lockedState = anchor.status();
    assert(lockedState.locked);
    assert(lockedState.context == context);

    anchor.release();

    auto releasedState = anchor.status();
    assert(!releasedState.locked);
    assert(releasedState.context.empty());

    return 0;
}
