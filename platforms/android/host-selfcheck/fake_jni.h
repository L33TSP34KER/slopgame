/*
 * Host-only fake JNIEnv, shared by the two self-tests in this directory.
 * NOT part of the Android build.
 *
 * Java arrays are modelled as plain C structs so the wrapper's
 * GetPrimitiveArrayCritical / Get<Type>ArrayElements paths can be exercised
 * without a JVM:
 *
 *     FakeArray a = { .is_float = 1, .len = 4 * 9 };
 *     ... (jfloatArray)&a ...
 */
#ifndef GC_FAKE_JNI_H
#define GC_FAKE_JNI_H

#include <jni.h>
#include <stdint.h>

/** Room for 8192 floats (910 commands) or 8192 ints (2048 commands). */
#define FAKE_ARRAY_MAX 8192

typedef struct {
    int is_float;
    int len;
    union {
        float f[FAKE_ARRAY_MAX];
        int32_t i[FAKE_ARRAY_MAX];
        int8_t b[FAKE_ARRAY_MAX];
    } u;
} FakeArray;

/**
 * Initializer for a FakeArray, e.g. `FakeArray a = FAKE_ARRAY_INIT(1, 4 * 9);`.
 * A macro (not a compound literal) so it also works for static storage and so
 * -Wmissing-field-initializers stays quiet under -Werror.
 */
#define FAKE_ARRAY_INIT(is_float_kind, length) { (is_float_kind), (length), { { 0 } } }

/** The singleton environment (a pointer to a table of function pointers). */
JNIEnv *fake_jni_env(void);

#endif /* GC_FAKE_JNI_H */
