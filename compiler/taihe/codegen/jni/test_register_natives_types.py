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

"""RegisterNatives signature matrix tests for JNI type mappings."""

from pathlib import Path

import pytest

from taihe.codegen.jni.testutil import compile_jni_sources


def _compile(tmp_path: Path, sources: dict[str, str]):
    outputs, diagnostics = compile_jni_sources(
        tmp_path,
        sources,
        register_natives=True,
    )
    assert diagnostics == ""
    return outputs["src/demo.jni_onload.cpp"]


SCALAR_SIGNATURES = [
    ("bool", "Z"),
    ("i8", "B"),
    ("i16", "S"),
    ("i32", "I"),
    ("i64", "J"),
    ("u8", "B"),
    ("u16", "S"),
    ("u32", "I"),
    ("u64", "J"),
    ("f32", "F"),
    ("f64", "D"),
]


@pytest.mark.parametrize(("taihe_ty", "sig"), SCALAR_SIGNATURES)
def test_scalar_signature_in_registration(tmp_path: Path, taihe_ty, sig):
    onload = _compile(tmp_path, {"demo": f"function f(a: {taihe_ty}): {taihe_ty};"})
    assert (
        f'{{"f", "({sig}){sig}", reinterpret_cast<void*>(&Java_demo_Demo_f)}},'
        in onload
    )


def test_string_signature_in_registration(tmp_path: Path):
    onload = _compile(tmp_path, {"demo": "function f(s: String): String;"})
    assert (
        '{"f", "(Ljava/lang/String;)Ljava/lang/String;", '
        "reinterpret_cast<void*>(&Java_demo_Demo_f)},"
    ) in onload


def test_struct_signature_in_registration(tmp_path: Path):
    onload = _compile(
        tmp_path,
        {"demo": "struct Pt { x: i32; } function f(p: Pt): Pt;"},
    )
    assert (
        '{"f", "(Ldemo/Pt;)Ldemo/Pt;", reinterpret_cast<void*>(&Java_demo_Demo_f)},'
        in onload
    )


def test_iface_signature_in_registration(tmp_path: Path):
    onload = _compile(
        tmp_path,
        {"demo": "interface Api { run(): i32; } function f(a: Api): Api;"},
    )
    assert (
        '{"f", "(Ldemo/Api;)Ldemo/Api;", reinterpret_cast<void*>(&Java_demo_Demo_f)},'
        in onload
    )


def test_enum_signature_in_registration(tmp_path: Path):
    onload = _compile(
        tmp_path,
        {"demo": "enum Color: i32 { R = 0 } function f(c: Color): Color;"},
    )
    assert (
        '{"f", "(Ldemo/Color;)Ldemo/Color;", reinterpret_cast<void*>(&Java_demo_Demo_f)},'
        in onload
    )


def test_optional_signature_in_registration(tmp_path: Path):
    onload = _compile(
        tmp_path,
        {"demo": "function f(s: Optional<String>): Optional<String>;"},
    )
    assert (
        '{"f", "(Ljava/lang/String;)Ljava/lang/String;", '
        "reinterpret_cast<void*>(&Java_demo_Demo_f)},"
    ) in onload


def test_opaque_signature_in_registration(tmp_path: Path):
    onload = _compile(tmp_path, {"demo": "function f(o: Opaque): Opaque;"})
    assert '{"f", "(J)J", reinterpret_cast<void*>(&Java_demo_Demo_f)},' in onload


def test_void_signature_in_registration(tmp_path: Path):
    onload = _compile(tmp_path, {"demo": "function f(a: i32);"})
    assert '{"f", "(I)V", reinterpret_cast<void*>(&Java_demo_Demo_f)},' in onload


def test_multi_param_signature_in_registration(tmp_path: Path):
    onload = _compile(
        tmp_path,
        {"demo": "function f(a: i32, b: String, c: f64): bool;"},
    )
    assert (
        '{"f", "(ILjava/lang/String;D)Z", reinterpret_cast<void*>(&Java_demo_Demo_f)},'
        in onload
    )


def test_struct_field_accessor_signatures_in_registration(tmp_path: Path):
    onload = _compile(
        tmp_path,
        {"demo": "struct Rec { x: i32; label: String; }"},
    )
    assert '{"create", "(ILjava/lang/String;)Ldemo/Rec;",' in onload
    assert '{"getX", "()I",' in onload
    assert '{"setX", "(I)V",' in onload
    assert '{"getLabel", "()Ljava/lang/String;",' in onload
    assert '{"setLabel", "(Ljava/lang/String;)V",' in onload
    assert '{"destroy", "()V",' in onload


def test_forward_declaration_void_return(tmp_path: Path):
    onload = _compile(tmp_path, {"demo": "function f(a: i32);"})
    assert (
        'extern "C" JNIEXPORT void JNICALL Java_demo_Demo_f('
        "JNIEnv* env, jclass /*cls*/, jint a);"
    ) in onload


def test_forward_declaration_instance_method(tmp_path: Path):
    onload = _compile(
        tmp_path,
        {"demo": "interface Api { run(): i32; }"},
    )
    assert (
        'extern "C" JNIEXPORT jint JNICALL Java_demo_Api_run('
        "JNIEnv* env, jobject /*obj*/);"
    ) in onload
