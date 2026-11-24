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

"""Unit tests for ``taihe.codegen.jni.signature``."""

import pytest

from taihe.codegen.jni.signature import (
    NativeMethod,
    class_descriptor,
    class_signature,
    java_pkg_to_native_prefix,
    mangle_overload_suffix,
    method_signature,
    native_symbol,
    overloaded_native_symbol,
)


def test_java_pkg_to_native_prefix():
    assert java_pkg_to_native_prefix("com") == "Java_com"
    assert java_pkg_to_native_prefix("com.example") == "Java_com_example"
    assert java_pkg_to_native_prefix("com.example.deep") == "Java_com_example_deep"
    assert java_pkg_to_native_prefix("") == "Java_"


def test_native_symbol():
    assert native_symbol("com.example", "Foo", "add") == "Java_com_example_Foo_add"
    assert native_symbol("a", "B", "c") == "Java_a_B_c"
    assert native_symbol("", "Cls", "m") == "Java__Cls_m"


def test_class_descriptor():
    assert class_descriptor("com.example", "Foo") == "com/example/Foo"
    assert class_descriptor("a", "B") == "a/B"
    assert class_descriptor("", "C") == "/C"


def test_class_signature():
    assert class_signature("com.example", "Foo") == "Lcom/example/Foo;"
    assert class_signature("a", "B") == "La/B;"


def test_method_signature():
    assert method_signature([], "V") == "()V"
    assert method_signature([], "I") == "()I"
    assert method_signature(["I"], "I") == "(I)I"
    assert method_signature(["I", "I"], "I") == "(II)I"
    assert method_signature(["Z", "B", "S", "I", "J", "F", "D"], "V") == ("(ZBSIJFD)V")
    assert method_signature(["Ljava/lang/String;"], "V") == "(Ljava/lang/String;)V"


def test_method_signature_empty_params_double_dims():
    assert method_signature(["[[I", "Ljava/lang/String;"], "V") == (
        "([[ILjava/lang/String;)V"
    )


def test_mangle_overload_suffix_basic():
    assert mangle_overload_suffix("(I)V") == "__(I)V"
    assert mangle_overload_suffix("II") == "__II"
    assert mangle_overload_suffix("V") == "__V"
    assert mangle_overload_suffix("") == "__"


def test_mangle_overload_suffix_escapes_special_chars():
    assert mangle_overload_suffix("_") == "___1"
    assert mangle_overload_suffix(";") == "___2"
    assert mangle_overload_suffix("[") == "___3"
    assert mangle_overload_suffix("/") == "___"
    assert mangle_overload_suffix("_;[") == "___1_2_3"
    assert mangle_overload_suffix("a_b") == "__a_1b"


def test_overloaded_native_symbol():
    assert (
        overloaded_native_symbol("com.example", "Foo", "run", "(I)V")
        == "Java_com_example_Foo_run__(I)V"
    )
    assert (
        overloaded_native_symbol("com.example", "Foo", "run", "(Ljava/lang/String;)V")
        == "Java_com_example_Foo_run__(Ljava_lang_String_2)V"
    )


def test_native_method_is_immutable_record():
    method = NativeMethod("add", "(II)I", "Java_com_example_Foo_add")
    assert method.java_name == "add"
    assert method.signature == "(II)I"
    assert method.native_symbol == "Java_com_example_Foo_add"


def test_mangle_escapes_underscores_in_mixed_input():
    assert mangle_overload_suffix("Ljava_lang_String_2") == "__Ljava_1lang_1String_12"


@pytest.mark.parametrize(
    ("java_pkg", "class_name", "method_name", "expected"),
    [
        ("com.example", "Foo", "bar", "Java_com_example_Foo_bar"),
        ("one.two.three", "C", "m", "Java_one_two_three_C_m"),
        ("", "C", "m", "Java__C_m"),
        ("pkg", "Class", "methodName", "Java_pkg_Class_methodName"),
    ],
)
def test_native_symbol_parametrized(java_pkg, class_name, method_name, expected):
    assert native_symbol(java_pkg, class_name, method_name) == expected


@pytest.mark.parametrize(
    ("param_sigs", "return_sig", "expected"),
    [
        ([], "V", "()V"),
        (["I"], "V", "(I)V"),
        (["I", "J"], "D", "(IJ)D"),
        (
            ["Ljava/lang/String;"],
            "Ljava/lang/String;",
            "(Ljava/lang/String;)Ljava/lang/String;",
        ),
    ],
)
def test_method_signature_parametrized(param_sigs, return_sig, expected):
    assert method_signature(param_sigs, return_sig) == expected
