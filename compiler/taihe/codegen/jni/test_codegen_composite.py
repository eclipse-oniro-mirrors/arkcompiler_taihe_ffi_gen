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

"""Composite integration tests for JNI code generation across decl kinds."""

from pathlib import Path

import pytest

from taihe.codegen.jni.testutil import compile_jni_sources


def _compile(tmp_path: Path, sources: dict[str, str], **kwargs):
    outputs, diagnostics = compile_jni_sources(tmp_path, sources, **kwargs)
    assert diagnostics == ""
    return outputs


FIELD_TYPES = [
    ("bool", "boolean"),
    ("i8", "byte"),
    ("i16", "short"),
    ("i32", "int"),
    ("i64", "long"),
    ("u8", "byte"),
    ("u16", "short"),
    ("u32", "int"),
    ("u64", "long"),
    ("f32", "float"),
    ("f64", "double"),
    ("String", "String"),
]


@pytest.mark.parametrize(("taihe_ty", "java_ty"), FIELD_TYPES)
def test_struct_field_types(tmp_path: Path, taihe_ty, java_ty):
    outputs = _compile(tmp_path, {"demo": f"struct Rec {{ value: {taihe_ty}; }}"})
    java = outputs["demo/Rec.java"]
    assert f"public static native Rec create({java_ty} value);" in java
    assert f"public native {java_ty} getValue();" in java
    assert f"public native void setValue({java_ty} value);" in java


def test_global_function_with_mixed_params(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Pt { x: i32; }
                enum Color: i32 { R = 0, G = 1 }
                function mix(a: i32, s: String, p: Pt, c: Color, o: Opaque): f64;
            """,
        },
    )
    java = outputs["demo/Demo.java"]
    assert (
        "public static native double mix(int a, String s, Pt p, Color c, long o);"
        in java
    )

    cpp = outputs["src/demo.jni.cpp"]
    assert "JNIEXPORT jdouble JNICALL Java_demo_Demo_mix" in cpp
    assert "jint a, jstring s, jobject p, jobject c, jlong o" in cpp


def test_global_function_returning_struct_wraps_handle(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Pt { x: i32; } function make(): Pt;"},
    )
    cpp = outputs["src/demo.jni.cpp"]
    assert 'jclass cls = env->FindClass("demo/Pt");' in cpp
    assert 'jmethodID ctor = env->GetMethodID(cls, "<init>", "(J)V");' in cpp
    assert "reinterpret_cast<jlong>(cpp_ptr)" in cpp


def test_global_function_returning_interface_wraps_handle(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "interface Api { run(): i32; } function make(): Api;"},
    )
    cpp = outputs["src/demo.jni.cpp"]
    assert 'jclass cls = env->FindClass("demo/Api");' in cpp
    assert "Java_demo_Demo_make" in cpp


def test_interface_method_returning_enum(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                enum Color: i32 { R = 0, G = 1 }
                interface C { pick(): Color; }
            """,
        },
    )
    cpp = outputs["src/demo.jni.cpp"]
    assert "cpp_ptr->pick()" in cpp
    assert (
        'jfieldID fid = env->GetStaticFieldID(cls, item_name, "Ldemo/Color;");' in cpp
    )


def test_interface_method_with_struct_param(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Pt { x: i32; }
                interface C { move(p: Pt): i32; }
            """,
        },
    )
    cpp = outputs["src/demo.jni.cpp"]
    assert "cpp_ptr->move(" in cpp
    assert 'jfieldID handle_fid = env->GetFieldID(cls, "handle", "J");' in cpp


def test_optional_interface_param(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                interface Api { run(): i32; }
                function f(a: Optional<Api>): i32;
            """,
        },
    )
    cpp = outputs["src/demo.jni.cpp"]
    assert "::taihe::optional<::demo::Api>" in cpp
    assert "return std::nullopt;" in cpp


def test_nested_struct_field(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Inner { n: i32; }
                struct Outer { inner: Inner; }
            """,
        },
    )
    java = outputs["demo/Outer.java"]
    assert "public native Inner getInner();" in java
    assert "public native void setInner(Inner value);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "cpp_ptr->inner" in cpp


def test_enum_with_many_items_generates_switch_cases(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                enum Mode: i32 { A = 0, B = 1, C = 2, D = 3, E = 4 }
                function pick(): Mode;
            """,
        },
    )
    cpp = outputs["src/demo.jni.cpp"]
    for item in ("A", "B", "C", "D", "E"):
        assert f"::demo::Mode::{item}" in cpp


def test_multiple_packages_in_one_compilation(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "alpha": "function a(): i32;",
            "beta": "function b(): String;",
        },
    )
    assert "alpha/Alpha.java" in outputs
    assert "beta/Beta.java" in outputs
    assert "src/alpha.jni.cpp" in outputs
    assert "src/beta.jni.cpp" in outputs
    assert "Java_alpha_Alpha_a" in outputs["src/alpha.jni.cpp"]
    assert "Java_beta_Beta_b" in outputs["src/beta.jni.cpp"]


def test_noexcept_interface_method(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "interface C { @noexcept add(a: i32, b: i32): i32; }"},
    )
    cpp = outputs["src/demo.jni.cpp"]
    assert "int32_t cpp_result = cpp_ptr->add(" in cpp
    assert "if (!cpp_result.has_value())" not in cpp


def test_struct_created_from_global_ctorless_function(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Pt { x: i32; } function make(x: i32): Pt;"},
    )
    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Demo_make" in cpp
    assert "::demo::Pt* cpp_ptr = new ::demo::Pt(cpp_value);" in cpp


def test_string_field_getter_uses_new_string_utf(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "struct Rec { label: String; }"})
    cpp = outputs["src/demo.jni.cpp"]
    assert "env->NewStringUTF(cpp_value.data())" in cpp


def test_scalar_field_setter_uses_static_cast(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "struct Rec { n: i64; }"})
    cpp = outputs["src/demo.jni.cpp"]
    assert "static_cast<int64_t>(jni_input)" in cpp
    assert "static_cast<jlong>(cpp_value)" in cpp


def test_single_segment_package_class_name(tmp_path: Path):
    outputs = _compile(tmp_path, {"util": "function f(): i32;"})
    assert "util/Util.java" in outputs
    java = outputs["util/Util.java"]
    assert "package util;" in java
    assert "public final class Util {" in java
