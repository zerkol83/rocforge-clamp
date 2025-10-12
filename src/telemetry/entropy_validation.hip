#include <cstddef>
#include <cstdint>

#include <hip/hip_runtime.h>

extern "C" __global__
void clampMirrorKernel(const std::uint64_t* seedsIn,
                       std::uint64_t* seedsOut,
                       const int* statesIn,
                       int* statesOut,
                       std::size_t count) {
    const std::size_t idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < count) {
        seedsOut[idx] = seedsIn[idx];
        statesOut[idx] = statesIn[idx];
    }
}
