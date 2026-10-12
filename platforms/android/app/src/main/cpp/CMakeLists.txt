# ---------------------------------------------------------------------------
# libgame_jni.so -- the only native code Android builds from source.
#
# It is a *thin* JNI shim (game_jni.c) over the frozen C ABI in
# <repo>/include/game_core.h and dynamically links the prebuilt Rust core that
# build_core.sh drops into app/src/main/jniLibs/<abi>/libgame_core.so.
#
# Run ./build_core.sh before Gradle: the imported library is required at
# *configure* time, so a missing .so fails the build with the message below.
# ---------------------------------------------------------------------------
cmake_minimum_required(VERSION 3.18)

project(game_jni C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# app/src/main/cpp -> app/src/main -> app/src -> app -> android -> platforms -> <repo>
set(GC_REPO_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../../../..")
get_filename_component(GC_REPO_ROOT "${GC_REPO_ROOT}" ABSOLUTE)
set(GC_HEADER_DIR "${GC_REPO_ROOT}/include")

if(NOT EXISTS "${GC_HEADER_DIR}/game_core.h")
    message(FATAL_ERROR
        "game_core.h not found at ${GC_HEADER_DIR}/game_core.h.\n"
        "This CMakeLists assumes the Android platform lives in "
        "<repo>/platforms/android/app/src/main/cpp.  Do not move it.")
endif()

# --- prebuilt Rust core -----------------------------------------------------
set(GC_CORE_SO "${CMAKE_SOURCE_DIR}/../jniLibs/${ANDROID_ABI}/libgame_core.so")

if(NOT EXISTS "${GC_CORE_SO}")
    message(FATAL_ERROR
        "Prebuilt core missing: ${GC_CORE_SO}\n"
        "Run platforms/android/build_core.sh first (it needs the Android NDK "
        "and the rustup targets listed in README.md).")
endif()

add_library(game_core SHARED IMPORTED)
set_target_properties(game_core PROPERTIES
    IMPORTED_LOCATION "${GC_CORE_SO}")

# --- the JNI shim -----------------------------------------------------------
add_library(game_jni SHARED game_jni.c)

target_include_directories(game_jni PRIVATE "${GC_HEADER_DIR}")

target_compile_options(game_jni PRIVATE -Wall -Wextra)

# 16 KB page size compatibility (Android 15+).  Harmless on older NDKs; the
# prebuilt Rust core must be linked the same way (build_core.sh passes the
# equivalent -C link-arg to rustc).
target_link_options(game_jni PRIVATE "-Wl,-z,max-page-size=16384")

find_library(gc_log_lib log)
if(NOT gc_log_lib)
    message(FATAL_ERROR "liblog not found in the NDK sysroot")
endif()

target_link_libraries(game_jni
    game_core      # provides gc_*  (DT_NEEDED libgame_core.so, packaged from jniLibs)
    ${gc_log_lib}) # __android_log_print
