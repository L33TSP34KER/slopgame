/* Host-only syntax-check stub for jni.h. NOT part of the Android build. */
#ifndef STUB_JNI_H
#define STUB_JNI_H
#include <stddef.h>
#include <stdint.h>
typedef int32_t jint;
typedef int64_t jlong;
typedef float   jfloat;
typedef int8_t  jbyte;
typedef jint    jsize;
typedef void *jobject;
typedef void *jclass;
typedef void *jstring;
typedef void *jarray;
typedef void *jfloatArray;
typedef void *jintArray;
typedef void *jbyteArray;
typedef void *jobjectArray;
typedef void *jweak;
typedef unsigned char jboolean_stub;
#define JNIEXPORT
#define JNICALL
#define JNI_ABORT 2
typedef const struct JNINativeInterface_ *JNIEnv;
struct JNINativeInterface_ {
    jsize  (*GetArrayLength)(JNIEnv *, jarray);
    void * (*GetPrimitiveArrayCritical)(JNIEnv *, jarray, jboolean_stub *);
    void   (*ReleasePrimitiveArrayCritical)(JNIEnv *, jarray, void *, jint);
    jbyte* (*GetByteArrayElements)(JNIEnv *, jbyteArray, jboolean_stub *);
    void   (*ReleaseByteArrayElements)(JNIEnv *, jbyteArray, jbyte *, jint);
    jclass (*FindClass)(JNIEnv *, const char *);
    jobjectArray (*NewObjectArray)(JNIEnv *, jsize, jclass, jobject);
    void   (*SetObjectArrayElement)(JNIEnv *, jobjectArray, jsize, jobject);
    jstring (*NewStringUTF)(JNIEnv *, const char *);
    void   (*DeleteLocalRef)(JNIEnv *, jobject);
};
#endif
