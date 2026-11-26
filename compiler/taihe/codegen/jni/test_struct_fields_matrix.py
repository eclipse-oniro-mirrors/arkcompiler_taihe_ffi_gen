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

"""Matrix test: every supported type as a struct field."""

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
    ("Opaque", "long"),
    ("Array<i32>", "int[]"),
    ("Vector<String>", "java.util.ArrayList<String>"),
    ("Map<String, i32>", "java.util.HashMap<String, Integer>"),
    ("Set<String>", "java.util.HashSet<String>"),
    ("Optional<String>", "String"),
]


@pytest.mark.parametrize(("taihe_ty", "java_ty"), FIELD_TYPES)
def test_struct_field_matrix(tmp_path: Path, taihe_ty, java_ty):
    outputs = _compile(tmp_path, {"demo": f"struct Rec {{ value: {taihe_ty}; }}"})
    java = outputs["demo/Rec.java"]
    assert f"public static native Rec create({java_ty} value);" in java
    assert f"public native {java_ty} getValue();" in java
    assert f"public native void setValue({java_ty} value);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Rec_create" in cpp
    assert "Java_demo_Rec_getValue" in cpp
    assert "Java_demo_Rec_setValue" in cpp


@pytest.mark.parametrize(("taihe_ty", "java_ty"), FIELD_TYPES)
def test_struct_field_matrix_register_natives(tmp_path: Path, taihe_ty, java_ty):
    outputs = _compile(
        tmp_path,
        {"demo": f"struct Rec {{ value: {taihe_ty}; }}"},
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert "reinterpret_cast<void*>(&Java_demo_Rec_create)" in onload
    assert "reinterpret_cast<void*>(&Java_demo_Rec_getValue)" in onload
    assert "reinterpret_cast<void*>(&Java_demo_Rec_setValue)" in onload


USER_TYPES = [
    ("struct Point { x: i32; }", "Point"),
    ("enum Color: i32 { R = 0, G = 1 }", "Color"),
    ("interface Iface { run(): i32; }", "Iface"),
]


@pytest.mark.parametrize(("decl", "java_type"), USER_TYPES)
def test_user_type_as_struct_field(tmp_path: Path, decl, java_type):
    outputs = _compile(
        tmp_path,
        {"demo": f"{decl} struct Rec {{ value: {java_type}; }}"},
    )
    java = outputs["demo/Rec.java"]
    assert f"public native {java_type} getValue();" in java
    assert f"public native void setValue({java_type} value);" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "cpp_ptr->value" in cpp
