// Standard AGP settings file.  The Android platform lives in its own Gradle
// build rooted here (platforms/android), completely independent from the Rust
// workspace at the repository root.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "game-android"

include(":app")
