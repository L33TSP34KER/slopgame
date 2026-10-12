plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.gamecore"
    compileSdk = 34
    // Pinned to the build-tools this machine has (36.1.0); leave it out and AGP
    // insists on the 34.0.0 that matches compileSdk.
    buildToolsVersion = (project.findProperty("buildTools") as String?) ?: "36.1.0"

    // Matches gradle.properties; override per machine with -Pndk.version=...
    ndkVersion = (project.findProperty("ndk.version") as String?) ?: "26.1.10909125"

    defaultConfig {
        applicationId = "com.gamecore"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"

        ndk {
            // arm64 for real devices, armeabi-v7a for old ones, x86_64 for the
            // emulator.  build_core.sh produces exactly these three ABIs, but a
            // single-ABI build is much faster while iterating:
            //     ./gradlew assembleDebug -Pabis=arm64-v8a
            val abis = (project.findProperty("abis") as String?)
                ?.split(",")
                ?.map { it.trim() }
                ?.filter { it.isNotEmpty() }
                ?: listOf("arm64-v8a", "armeabi-v7a", "x86_64")
            abiFilters += abis
        }

        externalNativeBuild {
            cmake {
                // game_jni.c is pure C and links no C++ at all, so asking for the
                // static STL keeps libc++_shared.so out of the APK (AGP defaults
                // to c++_shared).
                arguments += listOf("-DANDROID_STL=c++_static")
                // Optimisation levels stay with AGP/CMake per build type; this only
                // keeps frame pointers for readable native stack traces.
                // (-Wall -Wextra live in CMakeLists.txt so command-line and IDE
                // builds cannot drift apart.)
                cFlags += listOf("-fno-omit-frame-pointer")
            }
        }
    }

    buildTypes {
        debug {
            isJniDebuggable = true
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = false // the shell has no obfuscation needs yet
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    externalNativeBuild {
        cmake {
            // The version is intentionally omitted so AGP uses the CMake it knows
            // is installed; hard-coding one is the most common cause of
            // "CMake 'x.y.z' was not found" on a fresh machine.
            path = file("src/main/cpp/CMakeLists.txt")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    packaging {
        jniLibs {
            // libgame_core.so is built by cargo (build_core.sh) and copied into
            // src/main/jniLibs/<abi>/.  Keep its symbols: stripping is pointless
            // here and a mangled Rust .so is much harder to debug on device.
            keepDebugSymbols += listOf("**/libgame_core.so")
            useLegacyPackaging = false
        }
    }

    // The prebuilt core ships in the default jniLibs directory; stated explicitly
    // so it is obvious where build_core.sh must write.
    sourceSets {
        getByName("main") {
            jniLibs.srcDirs("src/main/jniLibs")
            assets.srcDirs("src/main/assets")
        }
    }

    buildFeatures {
        prefab = false
        buildConfig = false
    }

    lint {
        // The NDK-built wrapper and the prebuilt Rust core cannot be analysed by
        // lint; aborting the release build on those reports is not useful.
        abortOnError = false
        checkReleaseBuilds = false
    }
}

/*
 * Refreshes app/src/main/assets/ from <repo>/assets/dist/*.png by running
 * platforms/android/copy_assets.sh:
 *
 *     ./gradlew copyAssets
 *
 * It is deliberately NOT wired into preBuild: the PNGs are committed, so a clean
 * checkout (and a Windows machine without bash) builds without it.  Re-run it
 * whenever the art changes.
 */
tasks.register<Exec>("copyAssets") {
    group = "game"
    description = "Copy assets/dist/*.png into app/src/main/assets/ (see copy_assets.sh)"
    workingDir = rootProject.projectDir
    commandLine("bash", "${rootProject.projectDir}/copy_assets.sh")
}

dependencies {
    // Deliberately empty: the shell uses framework APIs only.  Kotlin's stdlib is
    // added by the Kotlin Android plugin.
}
