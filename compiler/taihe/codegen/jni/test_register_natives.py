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

"""Integration tests for ``JNI_OnLoad``/``RegisterNatives`` generation."""

from pathlib import Path

from taihe.codegen.jni.testutil import compile_jni_sources


def _compile(tmp_path: Path, sources: dict[str, str], **kwargs):
    outputs, diagnostics = compile_jni_sources(tmp_path, sources, **kwargs)
    assert diagnostics == ""
    return outputs


def _onload(outputs: dict[str, str], lib_name: str = "demo") -> str:
    path = f"src/{lib_name}.jni_onload.cpp"
    assert path in outputs
    return outputs[path]


def test_register_natives_enabled_generates_onload(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function add(a: i32, b: i32): i32;"},
        register_natives=True,
    )
    onload = _onload(outputs)
    assert (
        "JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void* /*reserved*/) {" in onload
    )
    assert "vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6)" in onload
    assert 'env->FindClass("demo/Demo");' in onload
    assert "return JNI_VERSION_1_6;" in onload


def test_register_natives_binds_global_function(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function add(a: i32, b: i32): i32;"},
        register_natives=True,
    )
    onload = _onload(outputs)
    assert '{"add", "(II)I", reinterpret_cast<void*>(&Java_demo_Demo_add)},' in onload


def test_register_natives_emits_forward_declarations(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function add(a: i32, b: i32): i32;"},
        register_natives=True,
    )
    onload = _onload(outputs)
    assert (
        'extern "C" JNIEXPORT jint JNICALL Java_demo_Demo_add('
        "JNIEnv* env, jclass /*cls*/, jint a, jint b);"
    ) in onload


def test_register_natives_string_signature(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function greet(name: String): String;"},
        register_natives=True,
    )
    onload = _onload(outputs)
    assert (
        '{"greet", "(Ljava/lang/String;)Ljava/lang/String;", '
        "reinterpret_cast<void*>(&Java_demo_Demo_greet)},"
    ) in onload


def test_register_natives_struct_methods(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Pt { x: i32; }"},
        register_natives=True,
    )
    onload = _onload(outputs)
    assert 'env->FindClass("demo/Pt");' in onload
    assert (
        '{"create", "(I)Ldemo/Pt;", reinterpret_cast<void*>(&Java_demo_Pt_create)},'
        in onload
    )
    assert '{"getX", "()I", reinterpret_cast<void*>(&Java_demo_Pt_getX)},' in onload
    assert '{"setX", "(I)V", reinterpret_cast<void*>(&Java_demo_Pt_setX)},' in onload
    assert (
        '{"destroy", "()V", reinterpret_cast<void*>(&Java_demo_Pt_destroy)},' in onload
    )


def test_register_natives_interface_methods(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "interface Calc { add(a: i32, b: i32): i32; }"},
        register_natives=True,
    )
    onload = _onload(outputs)
    assert 'env->FindClass("demo/Calc");' in onload
    assert '{"add", "(II)I", reinterpret_cast<void*>(&Java_demo_Calc_add)},' in onload
    assert (
        '{"destroy", "()V", reinterpret_cast<void*>(&Java_demo_Calc_destroy)},'
        in onload
    )


def test_register_natives_enum_param_uses_object_signature(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "enum Color: i32 { R = 0, G = 1 } function f(c: Color): i32;"},
        register_natives=True,
    )
    onload = _onload(outputs)
    assert (
        '{"f", "(Ldemo/Color;)I", reinterpret_cast<void*>(&Java_demo_Demo_f)},'
        in onload
    )


def test_disabled_register_natives_omits_onload(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function add(a: i32, b: i32): i32;"},
        register_natives=False,
    )
    assert "src/demo.jni_onload.cpp" not in outputs


def test_register_natives_registers_each_class_once(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                struct Pt { x: i32; }
                interface Calc { add(a: i32, b: i32): i32; }
                function top(): i32;
            """,
        },
        register_natives=True,
    )
    onload = _onload(outputs)
    assert onload.count("env->RegisterNatives(") == 3
    assert onload.count("JNI_OnLoad") == 1


def test_register_natives_lib_name_matches_package(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"com.example.custom": "function f(): i32;"},
        register_natives=True,
    )
    assert "src/custom.jni_onload.cpp" in outputs
    onload = _onload(outputs, lib_name="custom")
    assert 'env->FindClass("com/example/custom/Custom");' in onload


def test_no_destroy_option_omits_destroy_from_registration(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Pt { x: i32; }"},
        register_natives=True,
        extra_options=["no-destroy"],
    )
    onload = _onload(outputs)
    assert "destroy" not in onload
    assert (
        '{"create", "(I)Ldemo/Pt;", reinterpret_cast<void*>(&Java_demo_Pt_create)},'
        in onload
    )
