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

"""Integration tests for interface method inheritance."""

from pathlib import Path

from taihe.codegen.jni.testutil import compile_jni_sources


def _compile(tmp_path: Path, sources: dict[str, str], **kwargs):
    outputs, diagnostics = compile_jni_sources(tmp_path, sources, **kwargs)
    assert diagnostics == ""
    return outputs


def test_child_interface_inherits_parent_methods(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                interface Base { run(): i32; stop(): String; }
                interface Child : Base { walk(): i32; }
            """,
        },
    )
    java = outputs["demo/Child.java"]
    assert "public native int walk();" in java
    assert "public native int run();" in java
    assert "public native String stop();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Child_run" in cpp
    assert "Java_demo_Child_stop" in cpp
    assert "cpp_ptr->run()" in cpp
    assert "cpp_ptr->stop()" in cpp


def test_deep_interface_inheritance(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": """
                interface A { a(): i32; }
                interface B : A { b(): i32; }
                interface C : B { c(): i32; }
            """,
        },
    )
    java = outputs["demo/C.java"]
    assert "public native int a();" in java
    assert "public native int b();" in java
    assert "public native int c();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_C_a" in cpp
    assert "Java_demo_C_b" in cpp
    assert "Java_demo_C_c" in cpp


def test_interface_extends_register_natives(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": "interface Base { run(): i32; } interface Child : Base { walk(): i32; }"
        },
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert '{"walk", "()I", reinterpret_cast<void*>(&Java_demo_Child_walk)},' in onload
    assert '{"run", "()I", reinterpret_cast<void*>(&Java_demo_Child_run)},' in onload


def test_interface_extends_forward_declaration(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "interface Base { run(): String; } interface Child : Base {}"},
        register_natives=True,
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert (
        'extern "C" JNIEXPORT jstring JNICALL Java_demo_Child_run('
        "JNIEnv* env, jobject /*obj*/);"
    ) in onload


def test_interface_extends_method_rename_inherited(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "demo": 'interface Base { @java_name("execute") run(): i32; } '
            "interface Child : Base { walk(): i32; }"
        },
    )
    java = outputs["demo/Child.java"]
    assert "public native int execute();" in java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Child_execute" in cpp


def test_base_interface_still_generates_own_methods(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "interface Base { run(): i32; } interface Child : Base {}"},
    )
    assert "demo/Base.java" in outputs
    base_java = outputs["demo/Base.java"]
    assert "public native int run();" in base_java

    child_java = outputs["demo/Child.java"]
    assert "public native int run();" in child_java

    cpp = outputs["src/demo.jni.cpp"]
    assert "Java_demo_Base_run" in cpp
    assert "Java_demo_Child_run" in cpp
