cmake_minimum_required(VERSION 3.21)

project(Clamp VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT DEFINED HIP_DIR)
    set(HIP_DIR "/opt/rocm/lib/cmake/hip" CACHE PATH "Path to HIPConfig.cmake")
endif()

if(NOT DEFINED CMAKE_PREFIX_PATH)
    set(CMAKE_PREFIX_PATH "/opt/rocm;/opt/rocm/lib/cmake" CACHE STRING "Additional search prefixes for ROCm components")
endif()

find_package(HIP REQUIRED)
enable_language(HIP)
find_package(rocblas REQUIRED)
find_package(Python3 COMPONENTS Interpreter)
add_library(clamp STATIC
    src/clamp.cpp
    src/telemetry/entropy_telemetry.cpp
    src/telemetry/entropy_validation.cpp
    src/telemetry/entropy_validation.hip
    src/scoring/TemporalScoring.cpp
    src/telemetry/temporal_aggregator.cpp
)

set_source_files_properties(
    src/telemetry/entropy_validation.hip
    PROPERTIES
        LANGUAGE HIP
)

set_source_files_properties(
    src/telemetry/entropy_validation.cpp
    PROPERTIES
        LANGUAGE HIP
)

set(ROCM_SNAPSHOT_JSON "" CACHE STRING "Path to resolved ROCm snapshot metadata")
if(ROCM_SNAPSHOT_JSON)
    target_compile_definitions(clamp PRIVATE CLAMP_ROCM_SNAPSHOT_JSON="${ROCM_SNAPSHOT_JSON}")
endif()

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

add_executable(clamp_scoring_test
    tests/test_scoring.cpp
)

target_link_libraries(clamp_scoring_test
    PRIVATE
        clamp
)

add_test(NAME clamp_scoring_test COMMAND clamp_scoring_test)

add_executable(clamp_aggregator_test
    tests/test_aggregator.cpp
)

target_link_libraries(clamp_aggregator_test
    PRIVATE
        clamp
)

add_test(NAME clamp_aggregator_test COMMAND clamp_aggregator_test)

if(Python3_Interpreter_FOUND)
    add_test(
        NAME rocforge_ci_mode_tests
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/ci/tests/test_ci_mode.py
    )
    add_test(
        NAME clamp_snapi_tests
        COMMAND ${Python3_EXECUTABLE} -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/clamp -p "test_*.py"
    )
    add_test(
        NAME clamp_cli_tests
        COMMAND ${Python3_EXECUTABLE} -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/cli -p "test_*.py"
    )
else()
    message(WARNING "Python3 interpreter not found; skipping rocforge_ci mode tests.")
endif()
