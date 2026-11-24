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

"""Tests that document which types the JNI backend (v1) rejects."""

from pathlib import Path

import pytest

from taihe.codegen.jni.testutil import compile_jni_sources

UNSUPPORTED_SOURCES = [
    "function f(v: Vector<i32>): i32;",
    "function f(m: Map<String, i32>): i32;",
    "function f(s: Set<i32>): i32;",
    "function f(cb: (x: i32) => i32): i32;",
    "function f(): Future<i32>;",
    "function f(c: Completer<i32>): i32;",
    "function f(a: SharedArray<i32>): i32;",
    "function f(v: SharedVector<i32>): i32;",
    "function f(m: SharedMap<String, i32>): i32;",
    "function f(s: SharedSet<i32>): i32;",
]


@pytest.mark.parametrize("source", UNSUPPORTED_SOURCES)
def test_unsupported_generic_and_callback_types_raise(tmp_path: Path, source: str):
    with pytest.raises(ValueError, match="not supported"):
        compile_jni_sources(tmp_path, {"demo": source})


def test_union_type_raises(tmp_path: Path):
    with pytest.raises(ValueError, match="Union"):
        compile_jni_sources(
            tmp_path,
            {"demo": "union U { a: i32; b: String; } function f(u: U): i32;"},
        )


def test_optional_scalar_raises(tmp_path: Path):
    with pytest.raises(ValueError, match="Optional<scalar>"):
        compile_jni_sources(tmp_path, {"demo": "function f(a: Optional<i32>): i32;"})


def test_optional_bool_raises(tmp_path: Path):
    with pytest.raises(ValueError, match="Optional<scalar>"):
        compile_jni_sources(tmp_path, {"demo": "function f(a: Optional<bool>): i32;"})


def test_supported_optional_does_not_raise(tmp_path: Path):
    outputs, diagnostics = compile_jni_sources(
        tmp_path,
        {"demo": "function f(a: Optional<String>): i32;"},
    )
    assert diagnostics == ""
    assert "src/demo.jni.cpp" in outputs
