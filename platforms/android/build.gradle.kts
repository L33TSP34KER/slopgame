// Root build file: nothing but plugin versions.
//
// AGP 8.5.x requires Gradle 8.7+ (see gradle/wrapper/gradle-wrapper.properties),
// JDK 17 and Kotlin 1.9+.  Nothing here downloads AndroidX: the shell uses only
// framework APIs (Activity, GLSurfaceView, SoundPool, Vibrator, WindowInsets).
plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "1.9.24" apply false
}
