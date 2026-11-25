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

"""Unit tests for ``taihe.codegen.jni.options`` and backend config."""

from io import StringIO

from taihe.codegen.jni import JniBridgeBackendConfig
from taihe.codegen.jni.analyses import JniConfig
from taihe.codegen.jni.options import (
    JavaPackageOption,
    NativeLibraryOption,
    NoGenerateDestroyOption,
    RegisterNativesOption,
)
from taihe.driver.options import OptionRegistry
from taihe.utils.diagnostics import ConsoleDiagnosticsManager


def _parse_options(args: list[str]):
    registry = OptionRegistry()
    registry.register(
        JavaPackageOption,
        NativeLibraryOption,
        RegisterNativesOption,
        NoGenerateDestroyOption,
    )
    dm = ConsoleDiagnosticsManager(StringIO())
    return registry.parse_options(args, dm), dm


def test_flag_option_constructs_instance():
    option = RegisterNativesOption.try_parse(
        None, ConsoleDiagnosticsManager(StringIO())
    )
    assert option is not None


def test_value_option_constructs_instance():
    option = JavaPackageOption.try_parse(
        "com.example", ConsoleDiagnosticsManager(StringIO())
    )
    assert option.java_package == "com.example"


def test_value_option_without_value_yields_none():
    option = JavaPackageOption.try_parse(None, ConsoleDiagnosticsManager(StringIO()))
    assert option.java_package is None


def test_parse_none_options():
    options, dm = _parse_options([])
    assert not dm.has_error
    assert options.get(JavaPackageOption) is None
    assert options.get(NativeLibraryOption) is None
    assert options.get(RegisterNativesOption) is None
    assert options.get(NoGenerateDestroyOption) is None


def test_parse_all_options():
    options, dm = _parse_options(
        [
            "java-package=com.custom",
            "native-library=bridge",
            "register-natives",
            "no-destroy",
        ]
    )
    assert not dm.has_error
    java_package_opt = options.get(JavaPackageOption)
    native_library_opt = options.get(NativeLibraryOption)
    assert java_package_opt is not None
    assert java_package_opt.java_package == "com.custom"
    assert native_library_opt is not None
    assert native_library_opt.lib_name == "bridge"
    assert options.get(RegisterNativesOption) is not None
    assert options.get(NoGenerateDestroyOption) is not None


def test_jni_config_defaults():
    config = JniConfig()
    assert config.register_natives is False
    assert config.java_package is None
    assert config.native_library is None
    assert config.generate_destroy is True


def test_jni_config_custom():
    config = JniConfig(
        register_natives=True,
        java_package="org.custom",
        native_library="mylib",
        generate_destroy=False,
    )
    assert config.register_natives is True
    assert config.java_package == "org.custom"
    assert config.native_library == "mylib"
    assert config.generate_destroy is False


def test_backend_config_defaults():
    config = JniBridgeBackendConfig()
    assert config.NAME == "jni-bridge"
    assert config.DEPS == ["cpp-user"]
    assert config.register_natives is False
    assert config.java_package is None
    assert config.native_library is None
    assert config.generate_destroy is True


def test_backend_config_from_options():
    options, _ = _parse_options(
        [
            "java-package=com.custom",
            "native-library=bridge",
            "register-natives",
            "no-destroy",
        ]
    )
    config = JniBridgeBackendConfig.from_options(
        options,
        ConsoleDiagnosticsManager(StringIO()),
    )
    assert config.java_package == "com.custom"
    assert config.native_library == "bridge"
    assert config.register_natives is True
    assert config.generate_destroy is False


def test_backend_config_from_empty_options():
    options, _ = _parse_options([])
    config = JniBridgeBackendConfig.from_options(
        options,
        ConsoleDiagnosticsManager(StringIO()),
    )
    assert config.java_package is None
    assert config.native_library is None
    assert config.register_natives is False
    assert config.generate_destroy is True
