# CMake generated Testfile for 
# Source directory: /home/zerkol/Dev/rocforge/clamp
# Build directory: /home/zerkol/Dev/rocforge/clamp/build-ci
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test([=[clamp_test]=] "/home/zerkol/Dev/rocforge/clamp/build-ci/clamp_test")
set_tests_properties([=[clamp_test]=] PROPERTIES  _BACKTRACE_TRIPLES "/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;68;add_test;/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;0;")
add_test([=[clamp_scoring_test]=] "/home/zerkol/Dev/rocforge/clamp/build-ci/clamp_scoring_test")
set_tests_properties([=[clamp_scoring_test]=] PROPERTIES  _BACKTRACE_TRIPLES "/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;79;add_test;/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;0;")
add_test([=[clamp_aggregator_test]=] "/home/zerkol/Dev/rocforge/clamp/build-ci/clamp_aggregator_test")
set_tests_properties([=[clamp_aggregator_test]=] PROPERTIES  _BACKTRACE_TRIPLES "/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;90;add_test;/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;0;")
add_test([=[rocforge_ci_mode_tests]=] "/usr/bin/python3" "/home/zerkol/Dev/rocforge/clamp/ci/tests/test_ci_mode.py")
set_tests_properties([=[rocforge_ci_mode_tests]=] PROPERTIES  ENVIRONMENT "PYTHONPATH=/home/zerkol/Dev/rocforge/clamp" _BACKTRACE_TRIPLES "/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;93;add_test;/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;0;")
add_test([=[clamp_snapi_tests]=] "/usr/bin/python3" "-m" "unittest" "discover" "-s" "/home/zerkol/Dev/rocforge/clamp/tests/clamp" "-p" "test_*.py")
set_tests_properties([=[clamp_snapi_tests]=] PROPERTIES  ENVIRONMENT "PYTHONPATH=/home/zerkol/Dev/rocforge/clamp" _BACKTRACE_TRIPLES "/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;98;add_test;/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;0;")
add_test([=[clamp_cli_tests]=] "/usr/bin/python3" "-m" "unittest" "discover" "-s" "/home/zerkol/Dev/rocforge/clamp/tests/cli" "-p" "test_*.py")
set_tests_properties([=[clamp_cli_tests]=] PROPERTIES  ENVIRONMENT "PYTHONPATH=/home/zerkol/Dev/rocforge/clamp" _BACKTRACE_TRIPLES "/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;103;add_test;/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;0;")
