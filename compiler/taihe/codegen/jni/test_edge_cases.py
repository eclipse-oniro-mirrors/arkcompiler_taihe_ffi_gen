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

"""Edge-case integration tests for the JNI backend."""

from pathlib import Path

from taihe.codegen.jni.testutil import compile_jni_sources


def _compile(tmp_path: Path, sources: dict[str, str], **kwargs):
    outputs, diagnostics = compile_jni_sources(tmp_path, sources, **kwargs)
    assert diagnostics == ""
    return outputs


def test_function_with_no_params(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function f(): i32;"})
    java = outputs["demo/Demo.java"]
    assert "public static native int f();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Demo_f(JNIEnv* env, jclass /*cls*/)" in cpp


def test_many_global_functions(tmp_path: Path):
    funcs = [f"function f{i}(a: i32): i32;" for i in range(20)]
    outputs = _compile(tmp_path, {"demo": "\n".join(funcs)})
    java = outputs["demo/Demo.java"]
    for i in range(20):
        assert f"public static native int f{i}(int a);" in java

    cpp = outputs["src/demo.jni.cpp"]
    for i in range(20):
        assert f"Java_demo_Demo_f{i}" in cpp


def test_long_parameter_list(tmp_path: Path):
    params = ", ".join(f"a{i}: i32" for i in range(8))
    outputs = _compile(tmp_path, {"demo": f"function f({params}): i32;"})
    java = outputs["demo/Demo.java"]
    assert (
        "public static native int f(int a0, int a1, int a2, int a3, int a4, int a5, int a6, int a7);"
        in java
    )

    cpp = outputs["src/demo.jni.cpp"]
    assert (
        "Java_demo_Demo_f(JNIEnv* env, jclass /*cls*/, jint a0, jint a1, jint a2, jint a3, jint a4, jint a5, jint a6, jint a7)"
        in cpp
    )


def test_utf8_string_with_unicode_literal(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "function echo(s: String): String;"})
    cpp = outputs["src/demo.jni.cpp"]
    assert "GetStringUTFChars" in cpp
    assert "ReleaseStringUTFChars" in cpp


def test_interface_with_no_methods(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "interface Empty {}"})
    java = outputs["demo/Empty.java"]
    assert "public class Empty {" in java
    assert "public native void destroy();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Empty_destroy" in cpp


def test_struct_with_many_fields(tmp_path: Path):
    fields = " ".join(f"f{i}: i32;" for i in range(10))
    outputs = _compile(tmp_path, {"demo": f"struct Big {{ {fields} }}"})
    java = outputs["demo/Big.java"]
    for i in range(10):
        assert f"public native int getF{i}();" in java
        assert f"public native void setF{i}(int value);" in java


def test_multiple_packages_with_collections_and_extends(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "alpha": """
                struct Base { n: i32; }
                struct Derived { @extends base: Base; items: Array<i32>; }
                function f(v: Vector<i32>): i32;
            """,
            "beta": """
                interface Root { run(): i32; }
                interface Leaf : Root { walk(): i32; }
            """,
        },
    )
    assert "alpha/Derived.java" in outputs
    assert "beta/Leaf.java" in outputs

    derived = outputs["alpha/Derived.java"]
    assert "public static native Derived create(int n, int[] items);" in derived
    assert "public native int getN();" in derived
    assert "public native int[] getItems();" in derived

    leaf = outputs["beta/Leaf.java"]
    assert "public native int run();" in leaf
    assert "public native int walk();" in leaf


def test_struct_extends_and_interface_extends_register_natives(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Base { n: i32; }
                struct Derived { @extends base: Base; items: Array<i32>; }
                interface Root { run(): i32; }
                interface Leaf : Root { walk(): i32; }
            """,
        },
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert (
        '{"create", "(I[I)Ldemo/Derived;", reinterpret_cast<void*>(&Java_demo_Derived_create)},'
        in onload
    )
    assert '{"getN", "()I",' in onload
    assert '{"walk", "()I", reinterpret_cast<void*>(&Java_demo_Leaf_walk)},' in onload
    assert '{"run", "()I", reinterpret_cast<void*>(&Java_demo_Leaf_run)},' in onload


def test_noexcept_function_with_collection(tmp_path: Path):
    outputs = _compile(tmp_path, {"demo": "@noexcept function f(a: Array<i32>): i32;"})
    cpp = outputs["src/demo.jni.cpp"]
    assert "int32_t cpp_result = ::demo::f(" in cpp
    assert "if (!cpp_result.has_value())" not in cpp


def test_boolean_field_and_return_roundtrip(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Rec { flag: bool; } function get(s: Rec): bool;"},
    )
    java = outputs["demo/Rec.java"]
    assert "public native boolean getFlag();" in java
    assert "public native void setFlag(boolean value);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "static_cast<jboolean>(cpp_value)" in cpp


def test_enum_string_backed_in_collection(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": 'enum Color: String { R = "red", G = "green" } '
            "function f(cs: Array<Color>): Array<Color>;"
        },
    )
    java = outputs["demo/Demo.java"]
    assert "public static native Color[] f(Color[] cs);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "::taihe::array<::demo::Color>" in cpp
    assert 'GetMethodID(cls, "ordinal", "()I")' in cpp
    assert "GetStaticFieldID" in cpp
