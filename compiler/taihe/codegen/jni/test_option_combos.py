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

"""Integration tests for combinations of JNI backend options."""

from pathlib import Path

from taihe.codegen.jni.testutil import compile_jni_sources


def _compile(tmp_path: Path, sources: dict[str, str], **kwargs):
    outputs, diagnostics = compile_jni_sources(tmp_path, sources, **kwargs)
    assert diagnostics == ""
    return outputs


def test_java_package_with_register_natives(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function f(a: i32): i32;"},
        register_natives=True,
        extra_options=["java-package=com.custom"],
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert 'env->FindClass("com/custom/Demo");' in onload
    assert '{"f", "(I)I", reinterpret_cast<void*>(&Java_com_custom_Demo_f)},' in onload
    assert "Java_com_custom_Demo_f" in outputs["src/demo.jni.cpp"]


def test_native_library_with_register_natives(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "function f(): i32;"},
        register_natives=True,
        extra_options=["native-library=customlib"],
    )
    # The onload file is named after the resolved library name.
    assert "src/customlib.jni_onload.cpp" in outputs


def test_no_destroy_with_register_natives(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "interface Api { run(): i32; }"},
        register_natives=True,
        extra_options=["no-destroy"],
    )
    onload = outputs["src/demo.jni_onload.cpp"]
    assert "destroy" not in onload
    assert '{"run", "()I", reinterpret_cast<void*>(&Java_demo_Api_run)},' in onload


def test_all_options_combined(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": "struct Pt { x: i32; }"},
        register_natives=True,
        extra_options=[
            "java-package=org.final",
            "native-library=finallib",
            "no-destroy",
        ],
    )
    assert "org/final/Pt.java" in outputs
    assert "src/finallib.jni_onload.cpp" in outputs

    onload = outputs["src/finallib.jni_onload.cpp"]
    assert 'env->FindClass("org/final/Pt");' in onload
    assert "destroy" not in onload

    java = outputs["org/final/Pt.java"]
    assert "package org.final;" in java
    assert "destroy()" not in java


def test_attribute_and_option_agree(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {"demo": '@!java_package("com.agree") function f(): i32;'},
        extra_options=["java-package=com.agree"],
    )
    assert "com/agree/Demo.java" in outputs
    assert "Java_com_agree_Demo_f" in outputs["src/demo.jni.cpp"]


def test_option_only_affects_target_package(tmp_path: Path):
    outputs = _compile(
        tmp_path,
        {
            "alpha": "function a(): i32;",
            "beta": "function b(): i32;",
        },
        extra_options=["java-package=com.unified"],
    )
    # Both packages map into the same unified Java package.
    assert "com/unified/Alpha.java" in outputs
    assert "com/unified/Beta.java" in outputs
    assert "Java_com_unified_Alpha_a" in outputs["src/alpha.jni.cpp"]
    assert "Java_com_unified_Beta_b" in outputs["src/beta.jni.cpp"]
