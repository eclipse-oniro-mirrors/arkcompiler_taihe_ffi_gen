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

"""Integration tests for interactions between declaration kinds and collection types."""

from pathlib import Path

from taihe.codegen.jni.testutil import compile_jni_sources


def _compile(tmp_path: Path, sources: dict[str, str], **kwargs):
    outputs, diagnostics = compile_jni_sources(tmp_path, sources, **kwargs)
    assert diagnostics == ""
    return outputs


def test_struct_with_collection_fields(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Rec {
                    values: Array<i32>;
                    names: Vector<String>;
                    attrs: Map<String, i32>;
                    tags: Set<String>;
                }
            """,
        },
    )
    java = outputs["demo/Rec.java"]
    assert "public native int[] getValues();" in java
    assert "public native java.util.ArrayList<String> getNames();" in java
    assert "public native java.util.HashMap<String, Integer> getAttrs();" in java
    assert "public native java.util.HashSet<String> getTags();" in java


def test_interface_method_with_collection_params(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                interface Svc {
                    process(items: Array<i32>): i32;
                    lookup(table: Map<String, i32>): String;
                }
            """,
        },
    )
    java = outputs["demo/Svc.java"]
    assert "public native int process(int[] items);" in java
    assert (
        "public native String lookup(java.util.HashMap<String, Integer> table);" in java
    )

    cpp = outputs["src/demo.jni.cpp"]
    assert "cpp_ptr->process(" in cpp
    assert "cpp_ptr->lookup(" in cpp


def test_struct_with_enum_and_struct_fields(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                enum Color: i32 { R = 0, G = 1 }
                struct Inner { n: i32; }
                struct Rec { c: Color; inner: Inner; }
            """,
        },
    )
    java = outputs["demo/Rec.java"]
    assert "public native Color getC();" in java
    assert "public native Inner getInner();" in java


def test_collection_of_structs_in_struct(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Pt { x: i32; }
                struct Shape { points: Array<Pt>; }
            """,
        },
    )
    java = outputs["demo/Shape.java"]
    assert "public native Pt[] getPoints();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "::taihe::array<::demo::Pt>" in cpp


def test_global_function_void_and_collections(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function f(a: Array<i32>); function g(): Vector<String>;"},
    )
    java = outputs["demo/Demo.java"]
    assert "public static native void f(int[] a);" in java
    assert "public static native java.util.ArrayList<String> g();" in java


def test_many_decl_kinds_together(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                enum Color: String { R = "red", G = "green" }
                struct Pt { x: i32; label: String; }
                interface Shape { area(): f64; points(): Array<Pt>; }
                function make(): Pt;
                function describe(s: Shape): String;
                function colors(): Array<Color>;
            """,
        },
    )
    assert "demo/Demo.java" in outputs
    assert "demo/Pt.java" in outputs
    assert "demo/Color.java" in outputs
    assert "demo/Shape.java" in outputs

    java = outputs["demo/Demo.java"]
    assert "public static native Pt make();" in java
    assert "public static native String describe(Shape s);" in java
    assert "public static native Color[] colors();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Demo_make" in cpp
    assert "Java_demo_Demo_describe" in cpp
    assert "Java_demo_Shape_area" in cpp
    assert "Java_demo_Shape_points" in cpp


def test_int64_and_unsigned_collections(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                function f64s(a: Array<f64>): i32;
                function u64s(v: Vector<u64>): i32;
                function i8s(m: Map<String, i8>): i32;
            """,
        },
    )
    java = outputs["demo/Demo.java"]
    assert "public static native int f64s(double[] a);" in java
    assert "public static native int u64s(java.util.ArrayList<Long> v);" in java
    assert "public static native int i8s(java.util.HashMap<String, Byte> m);" in java


def test_struct_create_with_nested_collection(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Rec { items: Array<i32>; }"},
    )
    java = outputs["demo/Rec.java"]
    assert "public static native Rec create(int[] items);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Rec_create" in cpp
    assert "array_builder<int32_t>" in cpp


def test_interface_extends_with_collection_method(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                interface Base { items(): Array<i32>; }
                interface Child : Base { extra(): i32; }
            """,
        },
    )
    java = outputs["demo/Child.java"]
    assert "public native int[] items();" in java
    assert "public native int extra();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Child_items" in cpp
    assert "cpp_ptr->items()" in cpp


def test_collections_with_no_destroy_option(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Rec { items: Array<i32>; }"},
        extra_options=["no-destroy"],
    )
    java = outputs["demo/Rec.java"]
    assert "destroy()" not in java


def test_collections_register_natives_full(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Pt { x: i32; }
                function f(a: Array<i32>, v: Vector<String>, m: Map<String, i32>, s: Set<Pt>): i32;
            """,
        },
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert (
        '{"f", "([ILjava/util/ArrayList;Ljava/util/HashMap;Ljava/util/HashSet;)I", '
        "reinterpret_cast<void*>(&Java_demo_Demo_f)},"
    ) in onload
