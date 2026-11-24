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

"""Unit tests for the JNI code writers."""

from pathlib import Path

from taihe.codegen.jni.writer import JavaWriter
from taihe.utils.outputs import BasicOutputConfig


def _read_writer(tmp_path: Path, package: str | None, relative_path: str) -> str:
    om = BasicOutputConfig(dst_dir=tmp_path).build()
    writer = JavaWriter(om, relative_path)
    writer.package = package
    with writer:
        writer.writelns("public class Foo {}")
    return (tmp_path / relative_path).read_text(encoding="utf-8")


def test_java_writer_emits_package_prologue(tmp_path: Path):
    content = _read_writer(tmp_path, "com.example", "com/example/Foo.java")
    assert content.startswith("package com.example;\n\npublic class Foo {}\n")


def test_java_writer_without_package(tmp_path: Path):
    content = _read_writer(tmp_path, None, "Foo.java")
    assert content == "public class Foo {}\n"


def test_java_writer_creates_intermediate_directories(tmp_path: Path):
    _read_writer(tmp_path, "a.b.c", "a/b/c/Foo.java")
    assert (tmp_path / "a" / "b" / "c" / "Foo.java").is_file()


def test_java_writer_default_indent_is_four_spaces(tmp_path: Path):
    om = BasicOutputConfig(dst_dir=tmp_path).build()
    writer = JavaWriter(om, "Foo.java")
    with writer:
        with writer.indented("class Foo {", "}"):
            writer.writelns("int x;")
    content = (tmp_path / "Foo.java").read_text(encoding="utf-8")
    assert "    int x;" in content
