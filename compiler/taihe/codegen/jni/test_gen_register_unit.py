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

"""Unit tests for the ``gen_register`` data structures."""

from taihe.codegen.jni.gen_register import ClassRegistration, NativeMethodEntry


def test_native_method_entry_static():
    entry = NativeMethodEntry(
        java_name="add",
        signature="(II)I",
        symbol="Java_com_example_Foo_add",
        ret_jni="jint",
        param_str=", jint a, jint b",
        is_static=True,
    )
    assert entry.java_name == "add"
    assert entry.signature == "(II)I"
    assert entry.symbol == "Java_com_example_Foo_add"
    assert entry.ret_jni == "jint"
    assert entry.param_str == ", jint a, jint b"
    assert entry.is_static is True


def test_native_method_entry_instance():
    entry = NativeMethodEntry(
        java_name="getX",
        signature="()I",
        symbol="Java_com_example_Pt_getX",
        ret_jni="jint",
        param_str="",
        is_static=False,
    )
    assert entry.is_static is False
    assert entry.param_str == ""


def test_class_registration_holds_methods():
    reg = ClassRegistration(descriptor="com/example/Foo")
    assert reg.descriptor == "com/example/Foo"
    assert reg.methods == []

    reg.methods.append(
        NativeMethodEntry("m", "()V", "Java_com_example_Foo_m", "void", "", True)
    )
    assert len(reg.methods) == 1
    assert reg.methods[0].java_name == "m"


def test_class_registration_many_methods():
    reg = ClassRegistration(descriptor="com/example/Pt")
    for name in ("create", "destroy", "getX", "setX"):
        reg.methods.append(
            NativeMethodEntry(
                name, "()V", f"Java_com_example_Pt_{name}", "void", "", name == "create"
            )
        )
    assert [m.java_name for m in reg.methods] == ["create", "destroy", "getX", "setX"]
    assert reg.methods[0].is_static is True
    assert reg.methods[1].is_static is False
