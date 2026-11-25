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

"""Edge-case tests for JNI backend attributes and options."""

from pathlib import Path

from taihe.codegen.jni.attributes import (
    JavaNameAttr,
    JavaPackageAttr,
    NativeLibraryAttr,
)
from taihe.codegen.jni.testutil import compile_jni_sources
from taihe.semantics.declarations import GlobFuncDecl, IfaceMethodDecl, PackageDecl


def test_attribute_names_and_targets():
    assert JavaPackageAttr.NAME == "java_package"
    assert (PackageDecl,) == JavaPackageAttr.TARGETS
    assert NativeLibraryAttr.NAME == "native_library"
    assert (PackageDecl,) == NativeLibraryAttr.TARGETS
    assert JavaNameAttr.NAME == "java_name"
    assert (GlobFuncDecl, IfaceMethodDecl) == JavaNameAttr.TARGETS


def test_java_package_with_dots_in_package_name(tmp_path: Path):
    outputs, diagnostics = compile_jni_sources(
        tmp_path,
        {"com.example.deep": "function f(): i32;"},
    )
    assert diagnostics == ""
    assert "com/example/deep/Deep.java" in outputs


def test_java_package_attribute_with_empty_value_reports_error(tmp_path: Path):
    outputs, diagnostics = compile_jni_sources(
        tmp_path,
        {"demo": '@!java_package("") function f(): i32;'},
    )
    assert "Java package name" in diagnostics


def test_native_library_with_digits_reports_error(tmp_path: Path):
    outputs, diagnostics = compile_jni_sources(
        tmp_path,
        {"demo": '@!native_library("123") function f(): i32;'},
    )
    assert "library name" in diagnostics


def test_native_library_with_underscore_is_valid(tmp_path: Path):
    outputs, diagnostics = compile_jni_sources(
        tmp_path,
        {"demo": '@!native_library("my_lib") function f(): i32;'},
    )
    assert diagnostics == ""
    java = outputs["demo/Demo.java"]
    assert 'System.loadLibrary("my_lib");' in java


def test_java_name_with_dollar_sign_is_valid(tmp_path: Path):
    outputs, diagnostics = compile_jni_sources(
        tmp_path,
        {"demo": '@java_name("f$special") function f(): i32;'},
    )
    assert diagnostics == ""
    java = outputs["demo/Demo.java"]
    assert "public static native int f$special();" in java


def test_java_package_option_beats_attribute(tmp_path: Path):
    outputs, diagnostics = compile_jni_sources(
        tmp_path,
        {"demo": '@!java_package("com.from_attr") function f(): i32;'},
        extra_options=["java-package=com.from_option"],
    )
    assert diagnostics == ""
    assert "com/from_option/Demo.java" in outputs
    assert "com/from_attr" not in outputs


def test_native_library_option_beats_attribute(tmp_path: Path):
    outputs, diagnostics = compile_jni_sources(
        tmp_path,
        {"demo": '@!native_library("attr_lib") function f(): i32;'},
        extra_options=["native-library=option_lib"],
    )
    assert diagnostics == ""
    java = outputs["demo/Demo.java"]
    assert 'System.loadLibrary("option_lib");' in java
