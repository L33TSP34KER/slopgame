/*
 * Host-only fake JNIEnv implementation.  NOT part of the Android build.
 * See fake_jni.h.
 */
#include "fake_jni.h"

static jsize fake_GetArrayLength(JNIEnv *env, jarray a)
{
    (void)env;
    return (jsize)((FakeArray *)a)->len;
}

static void *fake_GetPrimitiveArrayCritical(JNIEnv *env, jarray a, jboolean_stub *isCopy)
{
    (void)env;
    if (isCopy != NULL) {
        *isCopy = 0;
    }
    FakeArray *fa = (FakeArray *)a;
    return fa->is_float ? (void *)fa->u.f : (void *)fa->u.i;
}

static void fake_ReleasePrimitiveArrayCritical(JNIEnv *env, jarray a, void *p, jint mode)
{
    (void)env; (void)a; (void)p; (void)mode;
}

static jbyte *fake_GetByteArrayElements(JNIEnv *env, jbyteArray a, jboolean_stub *isCopy)
{
    (void)env;
    if (isCopy != NULL) {
        *isCopy = 0;
    }
    return (jbyte *)((FakeArray *)a)->u.b;
}

static void fake_ReleaseByteArrayElements(JNIEnv *env, jbyteArray a, jbyte *p, jint mode)
{
    (void)env; (void)a; (void)p; (void)mode;
}

static jclass fake_FindClass(JNIEnv *env, const char *name)
{
    (void)env; (void)name;
    return (jclass)(intptr_t)1;
}

static jobjectArray fake_NewObjectArray(JNIEnv *env, jsize n, jclass c, jobject init)
{
    (void)env; (void)c; (void)init;
    return (jobjectArray)(intptr_t)n; /* the test only checks the length */
}

static void fake_SetObjectArrayElement(JNIEnv *env, jobjectArray a, jsize i, jobject v)
{
    (void)env; (void)a; (void)i; (void)v;
}

static jstring fake_NewStringUTF(JNIEnv *env, const char *s)
{
    (void)env;
    return (jstring)(intptr_t)(s != NULL ? 2 : 0);
}

static void fake_DeleteLocalRef(JNIEnv *env, jobject o)
{
    (void)env; (void)o;
}

static struct JNINativeInterface_ g_table = {
    fake_GetArrayLength,
    fake_GetPrimitiveArrayCritical,
    fake_ReleasePrimitiveArrayCritical,
    fake_GetByteArrayElements,
    fake_ReleaseByteArrayElements,
    fake_FindClass,
    fake_NewObjectArray,
    fake_SetObjectArrayElement,
    fake_NewStringUTF,
    fake_DeleteLocalRef,
};

static JNIEnv g_env = &g_table;

JNIEnv *fake_jni_env(void)
{
    return &g_env;
}
