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

"""Unit tests for the JNI naming and mapping helpers in ``analyses``."""

import pytest

from taihe.codegen.jni.analyses import (
    getter_name,
    java_desc_of,
    setter_name,
    upper_first,
)


def test_upper_first():
    assert upper_first("example") == "Example"
    assert upper_first("a") == "A"
    assert upper_first("A") == "A"
    assert upper_first("ALPHA") == "ALPHA"
    assert upper_first("") == ""
    assert upper_first("fooBar") == "FooBar"


def test_upper_first_single_char():
    assert upper_first("x") == "X"


def test_java_desc_of():
    assert java_desc_of("com.example", "Foo") == "com/example/Foo"
    assert java_desc_of("a", "B") == "a/B"
    assert java_desc_of("", "C") == "/C"


def test_getter_name():
    assert getter_name("x") == "getX"
    assert getter_name("label") == "getLabel"
    assert getter_name("URL") == "getURL"


def test_setter_name():
    assert setter_name("x") == "setX"
    assert setter_name("label") == "setLabel"
    assert setter_name("URL") == "setURL"


@pytest.mark.parametrize(
    ("field", "expected_getter", "expected_setter"),
    [
        ("name", "getName", "setName"),
        ("age", "getAge", "setAge"),
        ("isActive", "getIsActive", "setIsActive"),
        ("value", "getValue", "setValue"),
    ],
)
def test_field_accessor_names(field, expected_getter, expected_setter):
    assert getter_name(field) == expected_getter
    assert setter_name(field) == expected_setter
