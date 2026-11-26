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

"""Integration tests for JNI collection (array/vector/map/set) generation."""

from pathlib import Path

import pytest

from taihe.codegen.jni.testutil import compile_jni_sources


def _compile(tmp_path: Path, sources: dict[str, str], **kwargs):
    outputs, diagnostics = compile_jni_sources(tmp_path, sources, **kwargs)
    assert diagnostics == ""
    return outputs


PRIMITIVE_ARRAYS = [
    ("bool", "boolean", "jbooleanArray", "Z"),
    ("i8", "byte", "jbyteArray", "B"),
    ("i16", "short", "jshortArray", "S"),
    ("i32", "int", "jintArray", "I"),
    ("i64", "long", "jlongArray", "J"),
    ("f32", "float", "jfloatArray", "F"),
    ("f64", "double", "jdoubleArray", "D"),
]


@pytest.mark.parametrize(("taihe_ty", "java_ty", "jni_ty", "sig"), PRIMITIVE_ARRAYS)
def test_primitive_array_mapping(tmp_path: Path, taihe_ty, java_ty, jni_ty, sig):
    outputs = _compile(
        tmp_path, {"demo": f"function f(a: Array<{taihe_ty}>): Array<{taihe_ty}>;"}
    )
    java = outputs["demo/Demo.java"]
    assert f"public static native {java_ty}[] f({java_ty}[] a);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert f"JNIEXPORT {jni_ty} JNICALL Java_demo_Demo_f" in cpp
    assert "env->GetArrayLength(jni_input);" in cpp
    assert "::taihe::array_builder" in cpp
    assert "std::move(builder).finish()" in cpp


def test_object_array_uses_object_array_element(tmp_path: Path):
    outputs = _compile(
        tmp_path, {"demo": "function f(a: Array<String>): Array<String>;"}
    )
    java = outputs["demo/Demo.java"]
    assert "public static native String[] f(String[] a);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "JNIEXPORT jobjectArray JNICALL Java_demo_Demo_f" in cpp
    assert "env->GetObjectArrayElement(jni_input, i)" in cpp
    assert "env->NewObjectArray(len, elem_cls, nullptr)" in cpp
    assert "env->SetObjectArrayElement(result, i, item)" in cpp


def test_struct_array_element_wraps_objects(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Pt { x: i32; } function f(a: Array<Pt>): Array<Pt>;"},
    )
    java = outputs["demo/Demo.java"]
    assert "public static native Pt[] f(Pt[] a);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert 'env->FindClass("demo/Pt");' in cpp
    assert "array_builder<::demo::Pt>" in cpp


def test_vector_boxed_scalar(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f(v: Vector<i32>): Vector<i32>;"})
    java = outputs["demo/Demo.java"]
    assert (
        "public static native java.util.ArrayList<Integer> f("
        "java.util.ArrayList<Integer> v);"
    ) in java

    cpp = outputs["src/demo.jni.cpp"]
    assert 'jclass list_cls = env->FindClass("java/util/ArrayList");' in cpp
    assert 'GetMethodID(boxed_cls, "intValue", "()I")' in cpp
    assert 'GetStaticMethodID(boxed_cls, "valueOf", "(I)Ljava/lang/Integer;")' in cpp
    assert "::taihe::vector<int32_t> result;" in cpp


def test_vector_of_strings(tmp_path: Path):
    outputs = _compile(
        tmp_path, {"demo": "function f(v: Vector<String>): Vector<String>;"}
    )
    java = outputs["demo/Demo.java"]
    assert (
        "public static native java.util.ArrayList<String> f("
        "java.util.ArrayList<String> v);"
    ) in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "::taihe::vector<::taihe::string>" in cpp


def test_map_string_to_int(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f(m: Map<String, i32>): i32;"})
    java = outputs["demo/Demo.java"]
    assert "public static native int f(java.util.HashMap<String, Integer> m);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert 'jclass map_cls = env->FindClass("java/util/HashMap");' in cpp
    assert 'GetMethodID(map_cls, "entrySet", "()Ljava/util/Set;")' in cpp
    assert 'GetMethodID(entry_cls, "getKey", "()Ljava/lang/Object;")' in cpp
    assert 'GetMethodID(entry_cls, "getValue", "()Ljava/lang/Object;")' in cpp
    assert "::taihe::map<::taihe::string, int32_t> result;" in cpp


def test_map_returning_to_hashmap(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f(): Map<String, String>;"})
    java = outputs["demo/Demo.java"]
    assert "public static native java.util.HashMap<String, String> f();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert (
        'GetMethodID(map_cls, "put", "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;")'
        in cpp
    )


def test_set_of_strings(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f(s: Set<String>): Set<String>;"})
    java = outputs["demo/Demo.java"]
    assert (
        "public static native java.util.HashSet<String> f(java.util.HashSet<String> s);"
        in java
    )

    cpp = outputs["src/demo.jni.cpp"]
    assert 'jclass set_cls = env->FindClass("java/util/HashSet");' in cpp
    assert 'GetMethodID(set_cls, "toArray", "()[Ljava/lang/Object;")' in cpp
    assert "::taihe::set<::taihe::string> result;" in cpp


def test_collection_register_natives_signatures(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function f(a: Array<i32>): i32; function g(v: Vector<f64>): String;"},
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert '{"f", "([I)I", reinterpret_cast<void*>(&Java_demo_Demo_f)},' in onload
    assert (
        '{"g", "(Ljava/util/ArrayList;)Ljava/lang/String;", '
        "reinterpret_cast<void*>(&Java_demo_Demo_g)},"
    ) in onload


def test_optional_collection_does_not_raise(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f(a: Optional<Vector<i32>>): i32;"})
    assert "src/demo.jni.cpp" in outputs
    java = outputs["demo/Demo.java"]
    assert "java.util.ArrayList<Integer> a" in java


def test_optional_array_does_not_raise(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f(a: Optional<Array<i32>>): i32;"})
    assert "src/demo.jni.cpp" in outputs
