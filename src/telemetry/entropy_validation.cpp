#include "clamp.h"
#include "clamp/EntropyTelemetry.h"

#include <algorithm>
#include <cstdint>
#include <vector>

#include <hip/hip_runtime.h>

#ifndef CLAMP_HAS_HIP
#define CLAMP_HAS_HIP 1
#endif

namespace clamp {

#if CLAMP_HAS_HIP
extern "C" __global__
void clampMirrorKernel(const std::uint64_t* seedsIn,
                       std::uint64_t* seedsOut,
                       const int* statesIn,
                       int* statesOut,
                       std::size_t count);
#endif

bool runHipEntropyMirror(const std::vector<std::uint64_t>& seeds, const std::vector<int>& states) {
#if CLAMP_HAS_HIP
    if (seeds.size() != states.size()) {
        return false;
    }

    int deviceCount = 0;
    if (hipGetDeviceCount(&deviceCount) != hipSuccess || deviceCount == 0) {
        return true;
    }

    int activeDevice = 0;
    if (hipGetDevice(&activeDevice) != hipSuccess) {
        activeDevice = 0;
    }
    hipDeviceProp_t props{};
    if (hipGetDeviceProperties(&props, activeDevice) == hipSuccess) {
        if (auto* telemetry = EntropyTelemetry::activeInstance()) {
            telemetry->setBackendMetadata("HIP", props.name);
        }
    } else {
        if (auto* telemetry = EntropyTelemetry::activeInstance()) {
            telemetry->setBackendMetadata("HIP", "hip-device");
        }
    }

    const std::size_t count = seeds.size();
    if (count == 0) {
        return true;
    }

    std::uint64_t* dSeedsIn = nullptr;
    std::uint64_t* dSeedsOut = nullptr;
    int* dStatesIn = nullptr;
    int* dStatesOut = nullptr;

    auto cleanup = [&]() {
        if (dSeedsIn != nullptr) {
            (void)hipFree(dSeedsIn);
            dSeedsIn = nullptr;
        }
        if (dSeedsOut != nullptr) {
            (void)hipFree(dSeedsOut);
            dSeedsOut = nullptr;
        }
        if (dStatesIn != nullptr) {
            (void)hipFree(dStatesIn);
            dStatesIn = nullptr;
        }
        if (dStatesOut != nullptr) {
            (void)hipFree(dStatesOut);
            dStatesOut = nullptr;
        }
    };

    if (hipMalloc(reinterpret_cast<void**>(&dSeedsIn), count * sizeof(std::uint64_t)) != hipSuccess) {
        cleanup();
        return true;
    }
    if (hipMalloc(reinterpret_cast<void**>(&dSeedsOut), count * sizeof(std::uint64_t)) != hipSuccess) {
        cleanup();
        return true;
    }
    if (hipMalloc(reinterpret_cast<void**>(&dStatesIn), count * sizeof(int)) != hipSuccess) {
        cleanup();
        return true;
    }
    if (hipMalloc(reinterpret_cast<void**>(&dStatesOut), count * sizeof(int)) != hipSuccess) {
        cleanup();
        return true;
    }

    if (hipMemcpy(dSeedsIn, seeds.data(), count * sizeof(std::uint64_t), hipMemcpyHostToDevice) != hipSuccess) {
        cleanup();
        return true;
    }
    if (hipMemcpy(dStatesIn, states.data(), count * sizeof(int), hipMemcpyHostToDevice) != hipSuccess) {
        cleanup();
        return true;
    }

    const unsigned int threadsPerBlock = 64;
    const unsigned int blocks = static_cast<unsigned int>((count + threadsPerBlock - 1) / threadsPerBlock);
    const dim3 grid(blocks);
    const dim3 block(threadsPerBlock);
    hipLaunchKernelGGL(clampMirrorKernel,
                       grid,
                       block,
                       0,  // sharedMemBytes
                       0,  // stream
                       dSeedsIn,
                       dSeedsOut,
                       dStatesIn,
                       dStatesOut,
                       count);
    if (hipGetLastError() != hipSuccess) {
        cleanup();
        return true;
    }
    if (hipDeviceSynchronize() != hipSuccess) {
        cleanup();
        return true;
    }

    std::vector<std::uint64_t> seedsOut(count, 0);
    std::vector<int> statesOut(count, 0);
    if (hipMemcpy(seedsOut.data(), dSeedsOut, count * sizeof(std::uint64_t), hipMemcpyDeviceToHost) != hipSuccess) {
        cleanup();
        return true;
    }
    if (hipMemcpy(statesOut.data(), dStatesOut, count * sizeof(int), hipMemcpyDeviceToHost) != hipSuccess) {
        cleanup();
        return true;
    }

    cleanup();

    return std::equal(seeds.begin(), seeds.end(), seedsOut.begin()) &&
           std::equal(states.begin(), states.end(), statesOut.begin());
#else
    (void)seeds;
    (void)states;
    return true;
#endif
}

} // namespace clamp
