# Clamp

Clamp is a ROCForge module that offers a simple C++ anchor abstraction designed for HIP-enabled workflows. It demonstrates how to integrate HIP and rocBLAS dependencies while exposing a lightweight stateful API.

## Prerequisites
- ROCm 6.x with HIP and rocBLAS packages installed
- Clang with C++20 support
- CMake 3.21+ and Ninja

## Build
```bash
mkdir build
cd build
cmake -G Ninja ..
ninja
./clamp_test
```

The `libclamp.a` static library and `clamp_test` executable are produced in the build directory.
