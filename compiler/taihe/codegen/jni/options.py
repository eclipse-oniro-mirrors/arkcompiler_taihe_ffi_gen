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
from typing import TYPE_CHECKING

from typing_extensions import override

from taihe.driver.options import AbstractConfigOption

if TYPE_CHECKING:
    from taihe.utils.diagnostics import DiagnosticsManager


@dataclass
class JavaPackageOption(AbstractConfigOption):
    """Override the Java package name for all generated classes.

    When set, this overrides the package name that would otherwise be derived
    from the Taihe package name (or from ``@java_package`` on a per-package
    basis).

    Usage: ``-Cjava-package=com.example``
    """

    NAME = "java-package"

    java_package: str | None = None

    @classmethod
    def try_parse(cls, value: str | None, dm: "DiagnosticsManager"):
        return cls(java_package=value)


@dataclass
class NativeLibraryOption(AbstractConfigOption):
    """Override the native library name embedded in ``System.loadLibrary``.

    Usage: ``-Cnative-library=mybridge``
    """

    NAME = "native-library"

    lib_name: str | None = None

    @classmethod
    def try_parse(cls, value: str | None, dm: "DiagnosticsManager"):
        return cls(lib_name=value)


@dataclass
class RegisterNativesOption(AbstractConfigOption):
    """Emit ``JNI_OnLoad`` with ``RegisterNatives`` instead of plain symbols.

    By default the JNI backend relies on the ``Java_pkg_Class_method`` symbol
    naming convention. When this option is enabled, an additional registration
    source file is emitted that registers every native method explicitly.

    Usage: ``-Cregister-natives``
    """

    NAME = "register-natives"

    @classmethod
    @override
    def try_parse(cls, value: str | None, dm: "DiagnosticsManager"):
        return cls()


@dataclass
class NoGenerateDestroyOption(AbstractConfigOption):
    """Disable the ``destroy()`` native method for structs and interfaces.

    The ``destroy()`` method releases the native object wrapped by the Java
    handle. It is enabled by default; this option disables it for use cases
    where the native lifetime is managed elsewhere.

    Usage: ``-Cno-destroy``
    """

    NAME = "no-destroy"

    @classmethod
    @override
    def try_parse(cls, value: str | None, dm: "DiagnosticsManager"):
        return cls()


all_jni_config_options = [
    JavaPackageOption,
    NativeLibraryOption,
    RegisterNativesOption,
    NoGenerateDestroyOption,
]
