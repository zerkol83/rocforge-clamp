cmake_minimum_required(VERSION 3.21)

project(Clamp VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(HIP REQUIRED)
find_package(rocblas REQUIRED)

add_library(clamp STATIC
    src/clamp.cpp
)

target_include_directories(clamp
    PUBLIC
        ${PROJECT_SOURCE_DIR}/include
)

target_link_libraries(clamp
    PUBLIC
        hip::host
        roc::rocblas
)

add_executable(clamp_test
    tests/test_clamp.cpp
)

target_link_libraries(clamp_test
    PRIVATE
        clamp
)

enable_testing()
add_test(NAME clamp_test COMMAND clamp_test)
