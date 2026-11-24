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

import keyword
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from taihe.driver.backend import Backend, BackendConfig

if TYPE_CHECKING:
    from taihe.driver.contexts import CompilerInstance
    from taihe.driver.options import OptionRegistry, OptionStore
    from taihe.utils.diagnostics import DiagnosticsManager


_JS_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def _is_valid_java_identifier(name: str) -> bool:
    return bool(_JS_IDENTIFIER_RE.match(name)) and not keyword.iskeyword(name)


@dataclass
class JniBridgeBackendConfig(BackendConfig):
    NAME = "jni-bridge"
    DEPS: ClassVar = ["cpp-user"]

    register_natives: bool = False
    java_package: str | None = None
    native_library: str | None = None
    generate_destroy: bool = True

    @classmethod
    def register_options_to(cls, option_registry: "OptionRegistry"):
        from taihe.codegen.jni.options import all_jni_config_options

        option_registry.register(*all_jni_config_options)

    @classmethod
    def from_options(cls, options: "OptionStore", dm: "DiagnosticsManager"):
        from taihe.codegen.jni.options import (
            JavaPackageOption,
            NativeLibraryOption,
            NoGenerateDestroyOption,
            RegisterNativesOption,
        )

        java_package_opt = options.get(JavaPackageOption)
        native_library_opt = options.get(NativeLibraryOption)
        return JniBridgeBackendConfig(
            java_package=java_package_opt.java_package if java_package_opt else None,
            native_library=native_library_opt.lib_name if native_library_opt else None,
            register_natives=options.get(RegisterNativesOption) is not None,
            generate_destroy=options.get(NoGenerateDestroyOption) is None,
        )

    def build(self, instance: "CompilerInstance"):
        from taihe.codegen.jni.analyses import (
            JNI_CONFIG_KEY,
            JniConfig,
            JniConfigAnalysis,
        )
        from taihe.codegen.jni.attributes import all_jni_attr_types
        from taihe.codegen.jni.gen_java import JavaCodeGenerator
        from taihe.codegen.jni.gen_jni import JniCodeGenerator
        from taihe.codegen.jni.gen_register import JniModuleRegisterGenerator

        class JniBridgeBackendImpl(Backend):
            def __init__(self, ci: "CompilerInstance", config: JniBridgeBackendConfig):
                self._ci = ci
                self._config = config

            def setup(self):
                self._ci.attribute_registry.register(*all_jni_attr_types)
                am = self._ci.analysis_manager
                config = JniConfig(
                    register_natives=self._config.register_natives,
                    java_package=self._config.java_package,
                    native_library=self._config.native_library,
                    generate_destroy=self._config.generate_destroy,
                )
                JniConfigAnalysis.provide(
                    am,
                    JNI_CONFIG_KEY,
                    JniConfigAnalysis(am, JNI_CONFIG_KEY, config),
                )

            def validate(self):
                self._validate_jni_attributes()

            def _validate_jni_attributes(self):
                from taihe.codegen.jni.attributes import (
                    JavaNameAttr,
                    JavaPackageAttr,
                    NativeLibraryAttr,
                )
                from taihe.utils.exceptions import AdhocError

                dm = self._ci.diagnostics_manager
                for pkg in self._ci.package_group.iterate():
                    if (attr := JavaPackageAttr.get(pkg)) and (
                        not attr.java_package or " " in attr.java_package
                    ):
                        dm.emit(
                            AdhocError(
                                f"Attribute '@{attr.NAME}' requires a non-empty "
                                "Java package name without spaces.",
                                loc=attr.loc,
                            )
                        )
                    if (
                        attr := NativeLibraryAttr.get(pkg)
                    ) and not _is_valid_java_identifier(attr.lib_name):
                        dm.emit(
                            AdhocError(
                                f"Attribute '@{attr.NAME}' requires a valid "
                                "library name.",
                                loc=attr.loc,
                            )
                        )
                    for func in pkg.functions:
                        if attr := JavaNameAttr.get(func):
                            self._check_java_name(attr.java_name, attr.loc, dm)
                    for iface in pkg.interfaces:
                        for method in iface.methods:
                            if attr := JavaNameAttr.get(method):
                                self._check_java_name(attr.java_name, attr.loc, dm)

            def _check_java_name(self, name, loc, dm):
                from taihe.utils.exceptions import AdhocError

                if not _is_valid_java_identifier(name):
                    dm.emit(
                        AdhocError(
                            f"Attribute '@java_name' value {name!r} is not a valid "
                            "Java identifier.",
                            loc=loc,
                        )
                    )

            def generate(self):
                om = self._ci.output_manager
                am = self._ci.analysis_manager
                pg = self._ci.package_group
                JniCodeGenerator(om, am).generate(pg)
                JavaCodeGenerator(om, am).generate(pg)
                if self._config.register_natives:
                    JniModuleRegisterGenerator(om, am).generate(pg)

        return JniBridgeBackendImpl(instance, self)
