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

"""Integration tests covering declaration-kind edge cases."""

from pathlib import Path

from taihe.codegen.jni.testutil import compile_jni_sources


def _compile(tmp_path: Path, sources: dict[str, str]):
    outputs, diagnostics = compile_jni_sources(tmp_path, sources)
    assert diagnostics == ""
    return outputs


def test_string_backed_enum(tmp_path: Path):
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
    assert "::demo::Color::R" in cpp
    assert "::demo::Color::G" in cpp


def test_several_functions_in_package(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function a(): i32; function b(): String; function c(i: i32);"},
    )
    java = outputs["demo/Demo.java"]
    assert "public static native int a();" in java
    assert "public static native String b();" in java
    assert "public static native void c(int i);" in java

    cpp = outputs["src/demo.jni.cpp"]
    for name in ("a", "b", "c"):
        assert f"Java_demo_Demo_{name}" in cpp


def test_function_with_no_params_returning_void(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f();"})
    java = outputs["demo/Demo.java"]
    assert "public static native void f();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert (
        "JNIEXPORT void JNICALL Java_demo_Demo_f(JNIEnv* env, jclass /*cls*/) {" in cpp
    )


def test_interface_extends_inherits_parent_methods(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": "interface Base { run(): i32; } interface Child : Base { walk(): i32; }"
        },
    )
    java = outputs["demo/Child.java"]
    assert "public native int walk();" in java
    assert "public native int run();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Child_walk" in cpp
    assert "Java_demo_Child_run" in cpp
    assert "Java_demo_Base_run" in cpp
    assert "cpp_ptr->run()" in cpp


def test_multiple_interfaces(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "interface A { a(): i32; } interface B { b(): i32; }"},
    )
    assert "demo/A.java" in outputs
    assert "demo/B.java" in outputs
    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_A_a" in cpp
    assert "Java_demo_B_b" in cpp


def test_opaque_struct_field(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "struct Rec { h: Opaque; }"})
    java = outputs["demo/Rec.java"]
    assert "public native long getH();" in java
    assert "public native void setH(long value);" in java


def test_struct_with_struct_field(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct A { n: i32; } struct B { a: A; }"},
    )
    java = outputs["demo/B.java"]
    assert "public static native B create(A a);" in java
    assert "public native A getA();" in java


def test_noexcept_global_returning_struct(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Pt { x: i32; } @noexcept function make(): Pt;"},
    )
    cpp = outputs["src/demo.jni.cpp"]
    assert "::demo::Pt cpp_result = ::demo::make()" in cpp
    assert 'jclass cls = env->FindClass("demo/Pt");' in cpp


def test_function_returning_unit_and_void_side_by_side(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function f(): unit; function g();"},
    )
    java = outputs["demo/Demo.java"]
    assert "public static native void f();" in java
    assert "public static native void g();" in java


def test_struct_field_setter_with_string(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "struct Rec { label: String; }"})
    cpp = outputs["src/demo.jni.cpp"]
    assert "cpp_ptr->label = std::move(from_jni_tmp).value();" in cpp


def test_int64_struct_field_roundtrip(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "struct Rec { big: i64; }"})
    cpp = outputs["src/demo.jni.cpp"]
    assert "static_cast<int64_t>(jni_input)" in cpp
    assert "static_cast<jlong>(cpp_value)" in cpp


def test_bool_field_roundtrip(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "struct Rec { flag: bool; }"})
    cpp = outputs["src/demo.jni.cpp"]
    assert "static_cast<bool>(jni_input)" in cpp
    assert "static_cast<jboolean>(cpp_value)" in cpp
