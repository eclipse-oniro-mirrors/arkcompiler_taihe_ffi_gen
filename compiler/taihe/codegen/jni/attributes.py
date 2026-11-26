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

from dataclasses import dataclass

from taihe.codegen.ani.attributes import ExtendsAttr
from taihe.semantics.attributes import TypedAttribute
from taihe.semantics.declarations import (
    GlobFuncDecl,
    IfaceMethodDecl,
    PackageDecl,
)


@dataclass
class JavaPackageAttr(TypedAttribute[PackageDecl]):
    NAME = "java_package"
    TARGETS = (PackageDecl,)

    java_package: str


@dataclass
class NativeLibraryAttr(TypedAttribute[PackageDecl]):
    NAME = "native_library"
    TARGETS = (PackageDecl,)

    lib_name: str


@dataclass
class JavaNameAttr(TypedAttribute[GlobFuncDecl | IfaceMethodDecl]):
    """Rename the generated Java method for a function or interface method.

    Without this attribute, the Taihe function/method name is used verbatim in
    the generated Java source and in the native ``Java_...`` symbol. With this
    attribute, the given name is used instead.

    Example:
        ```
        @java_name("addExact")
        fn add(a: i32, b: i32): i32;
        ```
    """

    NAME = "java_name"
    TARGETS = (GlobFuncDecl, IfaceMethodDecl)

    java_name: str


all_jni_attr_types = [
    JavaPackageAttr,
    NativeLibraryAttr,
    JavaNameAttr,
    ExtendsAttr,
]
