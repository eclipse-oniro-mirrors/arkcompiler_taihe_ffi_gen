# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Huawei Device Co., Ltd.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Integration tests for option combinations exercised with the new features."""

from pathlib import Path

from taihe.codegen.jni.testutil import compile_jni_sources


def _compile(tmp_path: Path, sources: dict[str, str], **kwargs):
    outputs, diagnostics = compile_jni_sources(tmp_path, sources, **kwargs)
    assert diagnostics == ""
    return outputs


def test_java_package_with_collections(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function f(v: Vector<i32>): i32;"},
        extra_options=["java-package=com.custom"],
    )
    assert "com/custom/Demo.java" in outputs
    java = outputs["com/custom/Demo.java"]
    assert "package com.custom;" in java
    assert "java.util.ArrayList<Integer>" in java
    assert "Java_com_custom_Demo_f" in outputs["src/demo.jni.cpp"]


def test_java_package_with_extends(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Base { n: i32; }
                struct Derived { @extends base: Base; items: Array<i32>; }
            """,
        },
        extra_options=["java-package=com.custom"],
    )
    assert "com/custom/Derived.java" in outputs

    cpp = outputs["src/demo.jni.cpp"]
    assert 'env->FindClass("com/custom/Derived");' in cpp
    assert "cpp_ptr->base.n" in cpp


def test_native_library_with_collections(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function f(m: Map<String, i32>): i32;"},
        extra_options=["native-library=customlib"],
    )
    java = outputs["demo/Demo.java"]
    assert 'System.loadLibrary("customlib");' in java


def test_no_destroy_with_extends_and_collections(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Base { n: i32; }
                struct Derived { @extends base: Base; items: Array<i32>; }
                interface Svc { run(): i32; }
            """,
        },
        extra_options=["no-destroy"],
    )
    java = outputs["demo/Derived.java"]
    assert "destroy()" not in java

    svc = outputs["demo/Svc.java"]
    assert "destroy()" not in svc


def test_all_options_with_features(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Base { n: i32; }
                struct Derived { @extends base: Base; items: Vector<i32>; }
            """,
        },
        register_natives=True,
        extra_options=[
            "java-package=org.final",
            "native-library=finallib",
            "no-destroy",
        ],
    )
    assert "org/final/Derived.java" in outputs
    assert "src/finallib.jni_onload.cpp" in outputs

    onload = outputs["src/finallib.jni_onload.cpp"]
    assert 'env->FindClass("org/final/Derived");' in onload
    assert "destroy" not in onload
    assert "reinterpret_cast<void*>(&Java_org_final_Derived_create)" in onload
    assert "reinterpret_cast<void*>(&Java_org_final_Derived_getN)" in onload


def test_register_natives_collection_plus_extends(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Base { n: i32; }
                struct Derived { @extends base: Base; points: Array<String>; }
                function f(m: Map<String, Derived>): i32;
            """,
        },
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert (
        '{"create", "(I[Ljava/lang/String;)Ldemo/Derived;", '
        "reinterpret_cast<void*>(&Java_demo_Derived_create)},"
    ) in onload
    assert '{"f", "(Ljava/util/HashMap;)I",' in onload


def test_attribute_and_option_priority_with_collections(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": '@!java_package("com.attr") function f(a: Array<i32>): i32;'},
        extra_options=["java-package=com.option"],
    )
    # The option overrides the attribute.
    assert "com/option/Demo.java" in outputs
    assert "Java_com_option_Demo_f" in outputs["src/demo.jni.cpp"]


def test_register_natives_forward_decl_collection_param(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function f(v: Vector<i32>, m: Map<String, i32>): i32;"},
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert (
        'extern "C" JNIEXPORT jint JNICALL Java_demo_Demo_f('
        "JNIEnv* env, jclass /*cls*/, jobject v, jobject m);"
    ) in onload


def test_register_natives_forward_decl_jobject_array_and_scalar(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function f(a: Array<String>, b: i64): String;"},
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert (
        'extern "C" JNIEXPORT jstring JNICALL Java_demo_Demo_f('
        "JNIEnv* env, jclass /*cls*/, jobjectArray a, jlong b);"
    ) in onload
    assert (
        '{"f", "([Ljava/lang/String;J)Ljava/lang/String;", '
        "reinterpret_cast<void*>(&Java_demo_Demo_f)},"
    ) in onload


def test_collection_in_struct_field_register_natives_full_signature(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Rec { values: Array<i32>; table: Map<String, i32>; }"},
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert (
        '{"create", "([ILjava/util/HashMap;)Ldemo/Rec;", '
        "reinterpret_cast<void*>(&Java_demo_Rec_create)},"
    ) in onload
    assert '{"getValues", "()[I",' in onload
    assert '{"setValues", "([I)V",' in onload
    assert '{"getTable", "()Ljava/util/HashMap;",' in onload
    assert '{"setTable", "(Ljava/util/HashMap;)V",' in onload
