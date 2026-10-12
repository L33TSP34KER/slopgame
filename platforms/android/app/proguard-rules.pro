# Keep every class that declares a native method, and the JNI entry point class
# itself: the JNI names in game_jni.c are derived from the *package, class and
# method* names, so renaming any of them silently breaks the seam.
-keepclasseswithmembernames class * {
    native <methods>;
}

-keep class com.gamecore.NativeCore { *; }
-keep class com.gamecore.NativeCore$* { *; }

# The renderer/activity are only referenced from the manifest and from each other.
-keep class com.gamecore.MainActivity { *; }

# Kotlin metadata is not needed at runtime; keep it out of the way.
-dontwarn kotlin.**
