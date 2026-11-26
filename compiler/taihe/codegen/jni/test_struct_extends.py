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

"""Integration tests for struct field inheritance via ``@extends``."""

from pathlib import Path

from taihe.codegen.jni.testutil import compile_jni_sources


def _compile(tmp_path: Path, sources: dict[str, str], **kwargs):
    outputs, diagnostics = compile_jni_sources(tmp_path, sources, **kwargs)
    assert diagnostics == ""
    return outputs


def test_struct_extends_flattens_fields(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Book { title: String; year: i32; }
                struct RustBook { @extends base: Book; rust_version: i32; }
            """,
        },
    )

    java = outputs["demo/RustBook.java"]
    assert (
        "public static native RustBook create(String title, int year, int rust_version);"
        in java
    )
    assert "public native String getTitle();" in java
    assert "public native void setTitle(String value);" in java
    assert "public native int getYear();" in java
    assert "public native int getRust_version();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert (
        "new ::demo::RustBook{::demo::Book{std::move(from_jni_tmp_title).value(), "
        "std::move(from_jni_tmp_year).value()}, std::move(from_jni_tmp_rust_version).value()}"
        in cpp
    )
    assert "cpp_ptr->base.title" in cpp
    assert "cpp_ptr->base.year" in cpp
    assert "cpp_ptr->rust_version" in cpp
    assert "Java_demo_RustBook_getTitle" in cpp


def test_struct_extends_getter_uses_nested_access(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Inner { n: i32; }
                struct Outer { @extends inner: Inner; label: String; }
            """,
        },
    )
    cpp = outputs["src/demo.jni.cpp"]
    assert "return into_jni_field(env, cpp_ptr->inner.n);" in cpp
    assert "cpp_ptr->inner.n = std::move(from_jni_tmp).value();" in cpp
    assert "return into_jni_field(env, cpp_ptr->label);" in cpp


def test_struct_extends_register_natives(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Book { title: String; }
                struct RustBook { @extends base: Book; rust_version: i32; }
            """,
        },
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert (
        '{"create", "(Ljava/lang/String;I)Ldemo/RustBook;", '
        "reinterpret_cast<void*>(&Java_demo_RustBook_create)},"
    ) in onload
    assert '{"getTitle", "()Ljava/lang/String;",' in onload
    assert '{"getRust_version", "()I",' in onload


def test_struct_extends_deep_chain(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct A { a: i32; }
                struct B { @extends a: A; b: i32; }
                struct C { @extends b: B; c: i32; }
            """,
        },
    )
    java = outputs["demo/C.java"]
    assert "public static native C create(int a, int b, int c);" in java
    assert "public native int getA();" in java
    assert "public native int getB();" in java
    assert "public native int getC();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "cpp_ptr->b.a.a" in cpp
    assert "cpp_ptr->b.b" in cpp
    assert "cpp_ptr->c" in cpp
