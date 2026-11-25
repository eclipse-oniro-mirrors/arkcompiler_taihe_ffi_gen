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

"""Integration tests for JNI code generation across Taihe types and decls."""

from pathlib import Path

import pytest

from taihe.codegen.jni.testutil import compile_jni_sources


def _compile(tmp_path: Path, sources: dict[str, str], **kwargs):
    outputs, diagnostics = compile_jni_sources(tmp_path, sources, **kwargs)
    assert diagnostics == ""
    return outputs


SCALAR_TYPES = [
    ("bool", "boolean", "jboolean", "bool"),
    ("i8", "byte", "jbyte", "int8_t"),
    ("i16", "short", "jshort", "int16_t"),
    ("i32", "int", "jint", "int32_t"),
    ("i64", "long", "jlong", "int64_t"),
    ("u8", "byte", "jbyte", "uint8_t"),
    ("u16", "short", "jshort", "uint16_t"),
    ("u32", "int", "jint", "uint32_t"),
    ("u64", "long", "jlong", "uint64_t"),
    ("f32", "float", "jfloat", "float"),
    ("f64", "double", "jdouble", "double"),
]


@pytest.mark.parametrize(
    ("taihe_ty", "java_ty", "jni_ty", "cpp_ty"),
    SCALAR_TYPES,
)
def test_scalar_type_mapping(tmp_path: Path, taihe_ty, java_ty, jni_ty, cpp_ty):
    outputs = _compile(tmp_path, {"scalar": f"function f(a: {taihe_ty}): {taihe_ty};"})

    java = outputs["scalar/Scalar.java"]
    assert f"public static native {java_ty} f({java_ty} a);" in java

    cpp = outputs["src/scalar.jni.cpp"]
    assert f"Java_scalar_Scalar_f" in cpp
    assert f"static_cast<{cpp_ty}>(jni_input)" in cpp
    assert f"static_cast<{jni_ty}>(cpp_value)" in cpp


def test_void_return(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f(a: i32);"})
    java = outputs["demo/Demo.java"]
    assert "public static native void f(int a);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "JNIEXPORT void JNICALL Java_demo_Demo_f" in cpp
    # void functions have no result conversion lambda
    assert "into_jni_result" not in cpp


def test_unit_return_is_void(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f(): unit;"})
    java = outputs["demo/Demo.java"]
    assert "public static native void f();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "::taihe::expected<void, ::taihe::error> cpp_result" in cpp
    assert "return;" in cpp


def test_noexcept_function_has_no_result_wrapper(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "@noexcept function f(a: i32): i32;"})
    cpp = outputs["src/demo.jni.cpp"]
    assert "int32_t cpp_result = ::demo::f(" in cpp
    assert "if (!cpp_result.has_value())" not in cpp


def test_utf8_string_conversion(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function echo(s: String): String;"})
    cpp = outputs["src/demo.jni.cpp"]
    assert "GetStringUTFChars" in cpp
    assert "ReleaseStringUTFChars" in cpp
    assert "env->NewStringUTF(cpp_value.data())" in cpp


def test_utf16_string_conversion(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": 'function echo(s: @encoding("utf-16") String): @encoding("utf-16") String;'
        },
    )
    cpp = outputs["src/demo.jni.cpp"]
    assert "GetStringChars" in cpp
    assert "ReleaseStringChars" in cpp
    assert "env->NewString(reinterpret_cast<const jchar*>(cpp_value.data())" in cpp


def test_common_string_conversion(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": 'function echo(s: @encoding("common") String): @encoding("common") String;'
        },
    )
    cpp = outputs["src/demo.jni.cpp"]
    assert "::taihe::common_string result(chars);" in cpp
    assert "::taihe::string tmp(cpp_value);" in cpp


def test_opaque_type_is_jlong(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f(o: Opaque): Opaque;"})
    java = outputs["demo/Demo.java"]
    assert "public static native long f(long o);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "JNIEXPORT jlong JNICALL Java_demo_Demo_f" in cpp
    assert "::taihe::expected<uintptr_t, ::taihe::error>" in cpp
    assert "static_cast<jlong>(cpp_value)" in cpp


def test_struct_generates_handle_and_accessors(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Pt { x: i32; label: String; }"},
    )

    java = outputs["demo/Pt.java"]
    assert "private final long handle;" in java
    assert "private Pt(long handle) {" in java
    assert "public static native Pt create(int x, String label);" in java
    assert "public native int getX();" in java
    assert "public native void setX(int value);" in java
    assert "public native String getLabel();" in java
    assert "public native void setLabel(String value);" in java
    assert "public native void destroy();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Pt_create" in cpp
    assert "Java_demo_Pt_getX" in cpp
    assert "Java_demo_Pt_setLabel" in cpp
    assert "Java_demo_Pt_destroy" in cpp
    assert '"handle", "J"' in cpp


def test_interface_generates_methods(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "interface Calc { add(a: i32, b: i32): i32; describe(): String; }"},
    )

    java = outputs["demo/Calc.java"]
    assert "private final long handle;" in java
    assert "public native int add(int a, int b);" in java
    assert "public native String describe();" in java
    assert "public native void destroy();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Calc_add" in cpp
    assert "Java_demo_Calc_describe" in cpp
    assert "cpp_ptr->add(" in cpp
    assert "cpp_ptr->describe()" in cpp


def test_interface_returning_struct(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Pt { x: i32; }
                interface Factory { make(): Pt; }
            """,
        },
    )
    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Factory_make" in cpp
    assert 'jclass cls = env->FindClass("demo/Pt");' in cpp


def test_enum_maps_to_java_enum(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": 'enum Color: String { R = "red", G = "green" } function pick(): Color;'
        },
    )

    java = outputs["demo/Color.java"]
    assert "public enum Color {" in java
    assert "R," in java
    assert "G" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "static_cast<std::underlying_type_t<::demo::Color>>(cpp_value)" in cpp
    assert "::demo::Color::R" in cpp
    assert "::demo::Color::G" in cpp


def test_enum_param_uses_ordinal(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "enum Color: i32 { R = 0, G = 1 } function f(c: Color): i32;"},
    )
    cpp = outputs["src/demo.jni.cpp"]
    assert "CallIntMethod(jni_input, ordinal)" in cpp
    assert "static_cast<::demo::Color>(ord)" in cpp


def test_optional_struct_param_and_return(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Pt { x: i32; }
                function f(p: Optional<Pt>): Optional<Pt>;
            """,
        },
    )
    cpp = outputs["src/demo.jni.cpp"]
    assert "::taihe::optional<::demo::Pt>" in cpp
    assert "return std::nullopt;" in cpp
    assert "std::in_place" in cpp
    assert "::taihe::optional_view<::demo::Pt>" in cpp


def test_optional_string_return_is_nullable(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f(): Optional<String>;"})
    java = outputs["demo/Demo.java"]
    assert "public static native String f();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "::taihe::optional_view<::taihe::string>" in cpp
    assert "return nullptr;" in cpp


def test_java_name_renames_global_function(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": '@java_name("addExact") function add(a: i32, b: i32): i32;'},
    )
    java = outputs["demo/Demo.java"]
    assert "public static native int addExact(int a, int b);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Demo_addExact" in cpp
    assert "::demo::add(" in cpp


def test_java_name_renames_iface_method(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": 'interface C { @java_name("sum") add(a: i32, b: i32): i32; }'},
    )
    java = outputs["demo/C.java"]
    assert "public native int sum(int a, int b);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_C_sum" in cpp
    assert "cpp_ptr->add(" in cpp


def test_package_class_derives_from_last_segment(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"com.example.deep": "function f(): i32;"},
    )
    assert "com/example/deep/Deep.java" in outputs
    java = outputs["com/example/deep/Deep.java"]
    assert "package com.example.deep;" in java
    assert "public final class Deep {" in java
    assert 'System.loadLibrary("deep");' in java


def test_no_destroy_option_omits_destroy_methods(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Pt { x: i32; }"},
        extra_options=["no-destroy"],
    )
    java = outputs["demo/Pt.java"]
    assert "destroy()" not in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Pt_destroy" not in cpp
