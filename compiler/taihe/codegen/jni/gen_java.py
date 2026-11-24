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

from taihe.codegen.jni.analyses import (
    EnumJniInfo,
    GlobFuncJniInfo,
    IfaceJniInfo,
    IfaceMethodJniInfo,
    PackageJniInfo,
    StructJniInfo,
    get_config,
    getter_name,
    is_void_like,
    java_type_of,
    setter_name,
)
from taihe.codegen.jni.writer import JavaWriter
from taihe.semantics.declarations import (
    EnumDecl,
    GlobFuncDecl,
    IfaceDecl,
    IfaceMethodDecl,
    PackageDecl,
    PackageGroup,
    StructDecl,
)
from taihe.utils.analyses import AnalysisManager
from taihe.utils.outputs import OutputManager


class JavaCodeGenerator:
    def __init__(self, oc: OutputManager, am: AnalysisManager):
        self.oc = oc
        self.am = am

    def generate(self, pg: PackageGroup):
        for pkg in pg.iterate():
            pkg_jni_info = PackageJniInfo.get(self.am, pkg)
            if pkg.functions:
                self.gen_package_class(pkg, pkg_jni_info)
            for struct in pkg.structs:
                self.gen_struct_class(pkg_jni_info, struct)
            for iface in pkg.interfaces:
                self.gen_iface_class(pkg_jni_info, iface)
            for enum in pkg.enums:
                self.gen_enum_class(pkg_jni_info, enum)

    #######################
    # Shared codegen aids #
    #######################

    def open_writer(self, pkg_jni_info: PackageJniInfo, class_name: str) -> JavaWriter:
        writer = JavaWriter(
            self.oc,
            f"{pkg_jni_info.java_dir}/{class_name}.java",
        )
        writer.package = pkg_jni_info.java_pkg
        return writer

    def java_param_list(self, func: GlobFuncDecl | IfaceMethodDecl) -> str:
        parts = []
        for param in func.params:
            if is_void_like(param.ty):
                continue
            parts.append(f"{java_type_of(self.am, param.ty)} {param.name}")
        return ", ".join(parts)

    def java_return_type(self, func: GlobFuncDecl | IfaceMethodDecl) -> str:
        return java_type_of(self.am, func.return_ty)

    def java_field_type(self, field) -> str:
        return java_type_of(self.am, field.ty)

    ########################
    # Package-level class  #
    ########################

    def gen_package_class(self, pkg: PackageDecl, pkg_jni_info: PackageJniInfo):
        with self.open_writer(pkg_jni_info, pkg_jni_info.class_name) as target:
            with target.indented(
                f"public final class {pkg_jni_info.class_name} {{",
                f"}}",
            ):
                target.writelns(
                    f"/**",
                    f" * Package-level functions for the Taihe package {pkg.name}.",
                    f" */",
                )
                with target.indented(
                    f"static {{",
                    f"}}",
                ):
                    target.writelns(
                        f'System.loadLibrary("{pkg_jni_info.lib_name}");',
                    )
                target.writelns("")
                for func in pkg.functions:
                    java_name = GlobFuncJniInfo.get(self.am, func).java_name
                    target.writelns(
                        f"public static native {self.java_return_type(func)} {java_name}({self.java_param_list(func)});",
                    )

    ########################
    # Struct class         #
    ########################

    def gen_struct_class(self, pkg_jni_info: PackageJniInfo, struct: StructDecl):
        struct_jni_info = StructJniInfo.get(self.am, struct)
        with self.open_writer(pkg_jni_info, struct_jni_info.java_name) as target:
            with target.indented(
                f"public class {struct_jni_info.java_name} {{",
                f"}}",
            ):
                target.writelns(
                    f"private final long handle;",
                    f"",
                )
                with target.indented(
                    f"private {struct_jni_info.java_name}(long handle) {{",
                    f"}}",
                ):
                    target.writelns(
                        f"this.handle = handle;",
                    )
                target.writelns("")
                create_params = []
                for field in struct.fields:
                    if is_void_like(field.ty):
                        continue
                    create_params.append(f"{self.java_field_type(field)} {field.name}")
                target.writelns(
                    f"public static native {struct_jni_info.java_name} create({', '.join(create_params)});",
                )
                if get_config(self.am).generate_destroy:
                    target.writelns("")
                    target.writelns(
                        f"public native void destroy();",
                    )
                for field in struct.fields:
                    if is_void_like(field.ty):
                        continue
                    target.writelns(
                        f"public native {self.java_field_type(field)} {getter_name(field.name)}();",
                        f"public native void {setter_name(field.name)}({self.java_field_type(field)} value);",
                    )

    ########################
    # Interface class      #
    ########################

    def gen_iface_class(self, pkg_jni_info: PackageJniInfo, iface: IfaceDecl):
        iface_jni_info = IfaceJniInfo.get(self.am, iface)
        with self.open_writer(pkg_jni_info, iface_jni_info.java_name) as target:
            with target.indented(
                f"public class {iface_jni_info.java_name} {{",
                f"}}",
            ):
                target.writelns(
                    f"private final long handle;",
                    f"",
                )
                with target.indented(
                    f"private {iface_jni_info.java_name}(long handle) {{",
                    f"}}",
                ):
                    target.writelns(
                        f"this.handle = handle;",
                    )
                target.writelns("")
                if get_config(self.am).generate_destroy:
                    target.writelns(
                        f"public native void destroy();",
                    )
                for method in iface.methods:
                    java_name = IfaceMethodJniInfo.get(self.am, method).java_name
                    target.writelns(
                        f"public native {self.java_return_type(method)} {java_name}({self.java_param_list(method)});",
                    )

    ########################
    # Enum class           #
    ########################

    def gen_enum_class(self, pkg_jni_info: PackageJniInfo, enum: EnumDecl):
        enum_jni_info = EnumJniInfo.get(self.am, enum)
        items = list(enum.items)
        with self.open_writer(pkg_jni_info, enum_jni_info.java_name) as target:
            with target.indented(
                f"public enum {enum_jni_info.java_name} {{",
                f"}}",
            ):
                for i, item in enumerate(items):
                    comma = "," if i < len(items) - 1 else ""
                    target.writelns(f"{item.name}{comma}")
