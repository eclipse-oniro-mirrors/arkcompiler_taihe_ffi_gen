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

"""Tests for the JNI backend configuration, attributes, and validation."""

from pathlib import Path

import pytest

from taihe.codegen.jni.testutil import compile_jni_sources


def _compile(tmp_path: Path, sources: dict[str, str], **kwargs):
    return compile_jni_sources(tmp_path, sources, **kwargs)


def test_java_package_attribute_overrides_package(tmp_path: Path):
    outputs, diagnostics = _compile(
        tmp_path,
        {"demo": '@!java_package("com.custom") function f(): i32;'},
    )
    assert diagnostics == ""
    assert "com/custom/Demo.java" in outputs
    java = outputs["com/custom/Demo.java"]
    assert "package com.custom;" in java
    assert "Java_com_custom_Demo_f" in outputs["src/demo.jni.cpp"]


def test_native_library_attribute_overrides_lib_name(tmp_path: Path):
    outputs, diagnostics = _compile(
        tmp_path,
        {"demo": '@!native_library("mylib") function f(): i32;'},
    )
    assert diagnostics == ""
    java = outputs["demo/Demo.java"]
    assert 'System.loadLibrary("mylib");' in java


def test_invalid_java_package_reports_error(tmp_path: Path):
    outputs, diagnostics = _compile(
        tmp_path,
        {"demo": '@!java_package("com example") function f(): i32;'},
    )
    assert "Java package name without spaces" in diagnostics


def test_invalid_native_library_reports_error(tmp_path: Path):
    outputs, diagnostics = _compile(
        tmp_path,
        {"demo": '@!native_library("not valid") function f(): i32;'},
    )
    assert "requires a valid" in diagnostics


def test_invalid_java_name_reports_error(tmp_path: Path):
    outputs, diagnostics = _compile(
        tmp_path,
        {"demo": '@java_name("bad name") function f(): i32;'},
    )
    assert "not a valid" in diagnostics


def test_valid_attributes_do_not_report_errors(tmp_path: Path):
    outputs, diagnostics = _compile(
        tmp_path,
        {
            "demo": """
                @!java_package("com.valid")
                @!native_library("validLib")
                @java_name("renamed")
                function f(): i32;
            """,
        },
    )
    assert diagnostics == ""
    java = outputs["com/valid/Demo.java"]
    assert 'System.loadLibrary("validLib");' in java
    assert "public static native int renamed();" in java


def test_optional_scalar_raises(tmp_path: Path):
    with pytest.raises(ValueError, match="Optional<scalar>"):
        compile_jni_sources(tmp_path, {"demo": "function f(a: Optional<i32>): i32;"})
