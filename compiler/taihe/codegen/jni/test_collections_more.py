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

"""Additional integration tests for JNI collection generation."""

from pathlib import Path

import pytest

from taihe.codegen.jni.testutil import compile_jni_sources


def _compile(tmp_path: Path, sources: dict[str, str], **kwargs):
    outputs, diagnostics = compile_jni_sources(tmp_path, sources, **kwargs)
    assert diagnostics == ""
    return outputs


SCALAR_BOXING = [
    ("bool", "Boolean", "Boolean", "booleanValue"),
    ("i8", "Byte", "Byte", "byteValue"),
    ("i16", "Short", "Short", "shortValue"),
    ("i32", "Integer", "Integer", "intValue"),
    ("i64", "Long", "Long", "longValue"),
    ("u8", "Byte", "Byte", "byteValue"),
    ("u16", "Short", "Short", "shortValue"),
    ("u32", "Integer", "Integer", "intValue"),
    ("u64", "Long", "Long", "longValue"),
    ("f32", "Float", "Float", "floatValue"),
    ("f64", "Double", "Double", "doubleValue"),
]

SCALAR_BOXING_2 = [(taihe, boxed) for taihe, boxed, *_ in SCALAR_BOXING]


@pytest.mark.parametrize(
    ("taihe_ty", "java_boxed", "boxed_cls", "unbox"), SCALAR_BOXING
)
def test_vector_boxes_scalar(
    tmp_path: Path,
    taihe_ty,
    java_boxed,
    boxed_cls,
    unbox,
):
    outputs = _compile(
        tmp_path, {"demo": f"function f(v: Vector<{taihe_ty}>): Vector<{taihe_ty}>;"}
    )
    java = outputs["demo/Demo.java"]
    assert f"java.util.ArrayList<{java_boxed}>" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert f'env->FindClass("java/lang/{boxed_cls}");' in cpp
    assert f'GetMethodID(boxed_cls, "{unbox}", ' in cpp
    assert f'GetStaticMethodID(boxed_cls, "valueOf", ' in cpp


@pytest.mark.parametrize(("taihe_ty", "java_boxed"), SCALAR_BOXING_2)
def test_map_boxes_value(
    tmp_path: Path,
    taihe_ty,
    java_boxed,
):
    outputs = _compile(
        tmp_path, {"demo": f"function f(m: Map<String, {taihe_ty}>): {taihe_ty};"}
    )
    java = outputs["demo/Demo.java"]
    assert f"java.util.HashMap<String, {java_boxed}>" in java


def test_set_boxes_scalar(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f(s: Set<i32>): Set<i32>;"})
    java = outputs["demo/Demo.java"]
    assert "java.util.HashSet<Integer>" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert 'GetMethodID(boxed_cls, "intValue", "()I")' in cpp
    assert 'GetStaticMethodID(boxed_cls, "valueOf", "(I)Ljava/lang/Integer;")' in cpp


def test_nested_vector(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f(v: Vector<Vector<i32>>): i32;"})
    java = outputs["demo/Demo.java"]
    assert "java.util.ArrayList<java.util.ArrayList<Integer>>" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "::taihe::vector<::taihe::vector<int32_t>>" in cpp


def test_nested_array(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f(a: Array<Array<i32>>): i32;"})
    java = outputs["demo/Demo.java"]
    assert "public static native int f(int[][] a);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert (
        "JNIEXPORT jint JNICALL Java_demo_Demo_f(JNIEnv* env, jclass /*cls*/, jobjectArray a)"
        in cpp
    )
    assert "::taihe::array<::taihe::array<int32_t>>" in cpp


def test_map_of_string_to_vector(tmp_path: Path):
    outputs = _compile(
        tmp_path, {"demo": "function f(m: Map<String, Vector<i32>>): i32;"}
    )
    java = outputs["demo/Demo.java"]
    assert "java.util.HashMap<String, java.util.ArrayList<Integer>>" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "::taihe::map<::taihe::string, ::taihe::vector<int32_t>>" in cpp


def test_struct_in_vector(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Pt { x: i32; } function f(v: Vector<Pt>): Vector<Pt>;"},
    )
    java = outputs["demo/Demo.java"]
    assert "java.util.ArrayList<Pt>" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "::taihe::vector<::demo::Pt>" in cpp


def test_enum_in_set(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "enum Color: i32 { R = 0 } function f(s: Set<Color>): Set<Color>;"},
    )
    java = outputs["demo/Demo.java"]
    assert "java.util.HashSet<Color>" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "::taihe::set<::demo::Color>" in cpp


def test_optional_element_in_array(tmp_path: Path):
    outputs = _compile(
        tmp_path, {"demo": "function f(a: Array<Optional<String>>): i32;"}
    )
    java = outputs["demo/Demo.java"]
    assert "public static native int f(String[] a);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "::taihe::array<::taihe::optional<::taihe::string>>" in cpp


def test_struct_array_register_natives_signature(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Pt { x: i32; } function f(a: Array<Pt>): i32;"},
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert (
        '{"f", "([Ldemo/Pt;)I", reinterpret_cast<void*>(&Java_demo_Demo_f)},' in onload
    )


def test_map_register_natives_signature(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function f(m: Map<String, i32>): i32;"},
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert (
        '{"f", "(Ljava/util/HashMap;)I", reinterpret_cast<void*>(&Java_demo_Demo_f)},'
        in onload
    )


def test_set_register_natives_signature(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function f(s: Set<i64>): i32;"},
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert (
        '{"f", "(Ljava/util/HashSet;)I", reinterpret_cast<void*>(&Java_demo_Demo_f)},'
        in onload
    )


def test_array_of_bool_primitive_signature(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function f(a: Array<bool>): Array<bool>;"},
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert '{"f", "([Z)[Z", reinterpret_cast<void*>(&Java_demo_Demo_f)},' in onload
