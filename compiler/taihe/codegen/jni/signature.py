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

"""JNI naming and signature utilities.

This module centralizes the mapping between Taihe declarations and the JNI
on-the-wire conventions:

- ``Java_...`` exported symbol names.
- JNI method descriptors such as ``(Ljava/lang/String;I)V``.
- Short (register-natives) name mangling for overloaded methods.

It is intentionally free of any dependence on the semantic IR so that it can be
unit-tested in isolation.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeMethod:
    """A single entry in a ``JNINativeMethod`` table.

    Attributes:
        java_name: The method name as seen from Java.
        signature: The JNI method descriptor, e.g. ``(II)I``.
        native_symbol: The fully-qualified ``Java_...`` symbol name.
    """

    java_name: str
    signature: str
    native_symbol: str


def java_pkg_to_native_prefix(java_pkg: str) -> str:
    """Convert a Java package name to the ``Java_`` symbol prefix.

    ``com.example`` becomes ``Java_com_example``. Dots are replaced with
    underscores, matching the JVM symbol lookup rules.
    """
    return "Java_" + java_pkg.replace(".", "_")


def native_symbol(java_pkg: str, class_name: str, method_name: str) -> str:
    """Build the exported symbol name for a native method.

    ``com.example`` + ``Foo`` + ``bar`` becomes ``Java_com_example_Foo_bar``.
    """
    return f"{java_pkg_to_native_prefix(java_pkg)}_{class_name}_{method_name}"


def class_descriptor(java_pkg: str, class_name: str) -> str:
    """Return the JNI class descriptor for a Java class.

    ``com.example`` + ``Foo`` becomes ``com/example/Foo``.
    """
    return java_pkg.replace(".", "/") + "/" + class_name


def class_signature(java_pkg: str, class_name: str) -> str:
    """Return the JNI type signature for a Java class.

    ``com.example`` + ``Foo`` becomes ``Lcom/example/Foo;``.
    """
    return f"L{class_descriptor(java_pkg, class_name)};"


def method_signature(param_sigs: list[str], return_sig: str) -> str:
    """Compose a JNI method descriptor from parameter and return signatures."""
    return f"({''.join(param_sigs)}){return_sig}"


# Mapping of the characters that JNI requires escaping in overloaded method
# mangling. The mangling is only emitted for the *second* and subsequent
# overloads of the same Java method name.
_JNI_ESCAPE_TABLE = {
    "_": "_1",
    ";": "_2",
    "[": "_3",
    "/": "_",
}


def mangle_overload_suffix(signature: str) -> str:
    """Escape a JNI signature for use in an overloaded native symbol name.

    Per the JNI spec, overloaded methods are disambiguated by appending
    ``__`` followed by the escaped signature (``_`` -> ``_1``, ``;`` -> ``_2``,
    ``[`` -> ``_3``, ``/`` -> ``_``).
    """
    escaped = "".join(_JNI_ESCAPE_TABLE.get(ch, ch) for ch in signature)
    return "__" + escaped


def overloaded_native_symbol(
    java_pkg: str,
    class_name: str,
    method_name: str,
    signature: str,
) -> str:
    """Build the exported symbol name for an overloaded native method."""
    base = native_symbol(java_pkg, class_name, method_name)
    return base + mangle_overload_suffix(signature)
