# CMake generated Testfile for 
# Source directory: /home/zerkol/Dev/rocforge/clamp
# Build directory: /home/zerkol/Dev/rocforge/clamp
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test([=[clamp_test]=] "/home/zerkol/Dev/rocforge/clamp/clamp_test")
set_tests_properties([=[clamp_test]=] PROPERTIES  _BACKTRACE_TRIPLES "/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;65;add_test;/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;0;")
add_test([=[clamp_scoring_test]=] "/home/zerkol/Dev/rocforge/clamp/clamp_scoring_test")
set_tests_properties([=[clamp_scoring_test]=] PROPERTIES  _BACKTRACE_TRIPLES "/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;76;add_test;/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;0;")
add_test([=[clamp_aggregator_test]=] "/home/zerkol/Dev/rocforge/clamp/clamp_aggregator_test")
set_tests_properties([=[clamp_aggregator_test]=] PROPERTIES  _BACKTRACE_TRIPLES "/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;87;add_test;/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;0;")
add_test([=[clamp_aggregator_extended_test]=] "/home/zerkol/Dev/rocforge/clamp/clamp_aggregator_extended_test")
set_tests_properties([=[clamp_aggregator_extended_test]=] PROPERTIES  _BACKTRACE_TRIPLES "/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;98;add_test;/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;0;")
add_test([=[clamp_inspect_test]=] "/home/zerkol/Dev/rocforge/clamp/clamp_inspect_test")
set_tests_properties([=[clamp_inspect_test]=] PROPERTIES  _BACKTRACE_TRIPLES "/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;109;add_test;/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;0;")
add_test([=[clamp_compare_test]=] "/home/zerkol/Dev/rocforge/clamp/clamp_compare_test")
set_tests_properties([=[clamp_compare_test]=] PROPERTIES  _BACKTRACE_TRIPLES "/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;120;add_test;/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;0;")
add_test([=[clamp_phase4_end2end]=] "/usr/bin/python3" "/home/zerkol/Dev/rocforge/clamp/tests/test_phase4_end2end.py")
set_tests_properties([=[clamp_phase4_end2end]=] PROPERTIES  WORKING_DIRECTORY "/home/zerkol/Dev/rocforge/clamp" _BACKTRACE_TRIPLES "/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;122;add_test;/home/zerkol/Dev/rocforge/clamp/CMakeLists.txt;0;")
