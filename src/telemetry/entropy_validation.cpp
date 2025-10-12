#include "clamp.h"

#include <algorithm>
#include <cstdint>
#include <vector>

#if defined(__has_include)
#  if __has_include(<hip/hip_runtime.h>)
#    define CLAMP_HAS_HIP 1
#    include <hip/hip_runtime.h>
#  endif
#endif

#ifndef CLAMP_HAS_HIP
#  define CLAMP_HAS_HIP 0
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

    const std::size_t count = seeds.size();
    if (count == 0) {
        return true;
    }

    std::uint64_t* dSeedsIn = nullptr;
    std::uint64_t* dSeedsOut = nullptr;
    int* dStatesIn = nullptr;
    int* dStatesOut = nullptr;

    std::vector<std::uint64_t> seedsOut(count, 0);
    std::vector<int> statesOut(count, 0);

    hipError_t status = hipSuccess;
    status = hipMalloc(reinterpret_cast<void**>(&dSeedsIn), count * sizeof(std::uint64_t));
    if (status != hipSuccess) {
        return false;
    }
    status = hipMalloc(reinterpret_cast<void**>(&dSeedsOut), count * sizeof(std::uint64_t));
    if (status != hipSuccess) {
        hipFree(dSeedsIn);
        return false;
    }
    status = hipMalloc(reinterpret_cast<void**>(&dStatesIn), count * sizeof(int));
    if (status != hipSuccess) {
        hipFree(dSeedsIn);
        hipFree(dSeedsOut);
        return false;
    }
    status = hipMalloc(reinterpret_cast<void**>(&dStatesOut), count * sizeof(int));
    if (status != hipSuccess) {
        hipFree(dSeedsIn);
        hipFree(dSeedsOut);
        hipFree(dStatesIn);
        return false;
    }

    status = hipMemcpy(dSeedsIn, seeds.data(), count * sizeof(std::uint64_t), hipMemcpyHostToDevice);
    if (status != hipSuccess) {
        goto cleanup;
    }
    status = hipMemcpy(dStatesIn, states.data(), count * sizeof(int), hipMemcpyHostToDevice);
    if (status != hipSuccess) {
        goto cleanup;
    }

    const unsigned int threadsPerBlock = 64;
    const unsigned int blocks = static_cast<unsigned int>((count + threadsPerBlock - 1) / threadsPerBlock);
    hipLaunchKernelGGL(clampMirrorKernel,
                       dim3(blocks),
                       dim3(threadsPerBlock),
                       0,
                       0,
                       dSeedsIn,
                       dSeedsOut,
                       dStatesIn,
                       dStatesOut,
                       count);
    status = hipDeviceSynchronize();
    if (status != hipSuccess) {
        goto cleanup;
    }

    status = hipMemcpy(seedsOut.data(), dSeedsOut, count * sizeof(std::uint64_t), hipMemcpyDeviceToHost);
    if (status != hipSuccess) {
        goto cleanup;
    }
    status = hipMemcpy(statesOut.data(), dStatesOut, count * sizeof(int), hipMemcpyDeviceToHost);
    if (status != hipSuccess) {
        goto cleanup;
    }

cleanup:
    hipFree(dSeedsIn);
    hipFree(dSeedsOut);
    hipFree(dStatesIn);
    hipFree(dStatesOut);

    if (status != hipSuccess) {
        return false;
    }

    return std::equal(seeds.begin(), seeds.end(), seedsOut.begin()) &&
           std::equal(states.begin(), states.end(), statesOut.begin());
#else
    (void)seeds;
    (void)states;
    return true;
#endif
}

} // namespace clamp
