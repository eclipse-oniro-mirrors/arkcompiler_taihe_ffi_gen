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

"""JNI_OnLoad / RegisterNatives generation.

The default JNI backend relies on the ``Java_pkg_Class_method`` symbol naming
convention, which the HotSpot/ART runtimes resolve automatically. This module
implements the alternative ``RegisterNatives`` strategy: it emits a single
``JNI_OnLoad`` entry point that explicitly registers every native method via a
``JNINativeMethod`` table. The native functions themselves (which are emitted
by ``JniPackageSourceGenerator``) are reused unchanged; only their addresses
are bound here.
"""

from dataclasses import dataclass, field

from taihe.codegen.abi.writer import CSourceWriter
from taihe.codegen.jni.analyses import (
    GlobFuncJniInfo,
    IfaceJniInfo,
    IfaceMethodJniInfo,
    PackageJniInfo,
    StructJniInfo,
    get_config,
    getter_name,
    is_void_like,
    java_desc_of,
    jni_sig_of,
    jni_type_of,
    setter_name,
)
from taihe.codegen.jni.signature import (
    method_signature,
    native_symbol,
)
from taihe.semantics.declarations import (
    GlobFuncDecl,
    IfaceDecl,
    IfaceMethodDecl,
    PackageDecl,
    PackageGroup,
    StructDecl,
)
from taihe.utils.analyses import AnalysisManager
from taihe.utils.outputs import GEN_CXX_SRC_GROUP, OutputManager


def _jni_return_type(am: AnalysisManager, func: GlobFuncDecl | IfaceMethodDecl) -> str:
    return jni_type_of(am, func.return_ty)


def _jni_param_list(am: AnalysisManager, func: GlobFuncDecl | IfaceMethodDecl) -> str:
    parts = []
    for param in func.params:
        if is_void_like(param.ty):
            continue
        parts.append(f"{jni_type_of(am, param.ty)} {param.name}")
    if not parts:
        return ""
    return ", " + ", ".join(parts)


@dataclass
class NativeMethodEntry:
    """A native method to be bound by ``RegisterNatives``.

    In addition to the registration-table fields (``java_name``, ``signature``
    and ``symbol``), it records enough type information to emit a matching
    forward declaration for the native function.
    """

    java_name: str
    signature: str
    symbol: str
    ret_jni: str
    param_str: str
    is_static: bool


@dataclass
class ClassRegistration:
    """All native methods bound to a single Java class."""

    descriptor: str
    methods: list[NativeMethodEntry] = field(default_factory=list)


class JniModuleRegisterGenerator:
    def __init__(self, oc: OutputManager, am: AnalysisManager):
        self.oc = oc
        self.am = am

    def generate(self, pg: PackageGroup):
        packages = [p for p in pg.iterate() if self._has_native_methods(p)]
        if not packages:
            return

        lib_name = PackageJniInfo.get(self.am, packages[0]).lib_name
        registrations = []
        for pkg in packages:
            registrations.extend(self.collect_package(pkg))

        target = CSourceWriter(
            self.oc,
            f"src/{lib_name}.jni_onload.cpp",
            group=GEN_CXX_SRC_GROUP,
        )
        with target:
            target.writelns("#include <jni.h>", "")
            self.gen_forward_decls(target, registrations)
            self.gen_onload(target, registrations)

    #######################
    # Method collection   #
    #######################

    def _has_native_methods(self, pkg: PackageDecl) -> bool:
        return bool(pkg.functions or pkg.structs or pkg.interfaces)

    def collect_package(self, pkg: PackageDecl) -> list[ClassRegistration]:
        pkg_jni_info = PackageJniInfo.get(self.am, pkg)
        registrations: list[ClassRegistration] = []

        if pkg.functions:
            reg = ClassRegistration(
                descriptor=java_desc_of(pkg_jni_info.java_pkg, pkg_jni_info.class_name)
            )
            for func in pkg.functions:
                info = GlobFuncJniInfo.get(self.am, func)
                reg.methods.append(
                    NativeMethodEntry(
                        java_name=info.java_name,
                        signature=info.jni_signature,
                        symbol=info.native_symbol,
                        ret_jni=_jni_return_type(self.am, func),
                        param_str=_jni_param_list(self.am, func),
                        is_static=True,
                    )
                )
            registrations.append(reg)

        for struct in pkg.structs:
            registrations.append(self.collect_struct(pkg_jni_info, struct))

        for iface in pkg.interfaces:
            registrations.append(self.collect_iface(pkg_jni_info, iface))

        return registrations

    def collect_struct(
        self,
        pkg_jni_info: PackageJniInfo,
        struct: StructDecl,
    ) -> ClassRegistration:
        struct_jni_info = StructJniInfo.get(self.am, struct)
        reg = ClassRegistration(descriptor=struct_jni_info.java_desc)

        field_infos = [f for f in struct.fields if not is_void_like(f.ty)]
        create_sig = method_signature(
            [jni_sig_of(self.am, f.ty) for f in field_infos],
            struct_jni_info.jni_sig,
        )
        create_params = ", ".join(
            f"{jni_type_of(self.am, f.ty)} {f.name}" for f in field_infos
        )
        if create_params:
            create_params = ", " + create_params
        reg.methods.append(
            NativeMethodEntry(
                java_name="create",
                signature=create_sig,
                symbol=native_symbol(
                    pkg_jni_info.java_pkg, struct_jni_info.java_name, "create"
                ),
                ret_jni="jobject",
                param_str=create_params,
                is_static=True,
            )
        )

        if get_config(self.am).generate_destroy:
            reg.methods.append(
                NativeMethodEntry(
                    java_name="destroy",
                    signature="()V",
                    symbol=native_symbol(
                        pkg_jni_info.java_pkg, struct_jni_info.java_name, "destroy"
                    ),
                    ret_jni="void",
                    param_str="",
                    is_static=False,
                )
            )

        for field_decl in field_infos:
            field_sig = jni_sig_of(self.am, field_decl.ty)
            field_jni = jni_type_of(self.am, field_decl.ty)
            reg.methods.append(
                NativeMethodEntry(
                    java_name=getter_name(field_decl.name),
                    signature=method_signature([], field_sig),
                    symbol=native_symbol(
                        pkg_jni_info.java_pkg,
                        struct_jni_info.java_name,
                        getter_name(field_decl.name),
                    ),
                    ret_jni=field_jni,
                    param_str="",
                    is_static=False,
                )
            )
            reg.methods.append(
                NativeMethodEntry(
                    java_name=setter_name(field_decl.name),
                    signature=method_signature([field_sig], "V"),
                    symbol=native_symbol(
                        pkg_jni_info.java_pkg,
                        struct_jni_info.java_name,
                        setter_name(field_decl.name),
                    ),
                    ret_jni="void",
                    param_str=f", {field_jni} value",
                    is_static=False,
                )
            )
        return reg

    def collect_iface(
        self,
        pkg_jni_info: PackageJniInfo,
        iface: IfaceDecl,
    ) -> ClassRegistration:
        iface_jni_info = IfaceJniInfo.get(self.am, iface)
        reg = ClassRegistration(descriptor=iface_jni_info.java_desc)

        if get_config(self.am).generate_destroy:
            reg.methods.append(
                NativeMethodEntry(
                    java_name="destroy",
                    signature="()V",
                    symbol=native_symbol(
                        pkg_jni_info.java_pkg, iface_jni_info.java_name, "destroy"
                    ),
                    ret_jni="void",
                    param_str="",
                    is_static=False,
                )
            )

        for method in iface.methods:
            info = IfaceMethodJniInfo.get(self.am, method)
            reg.methods.append(
                NativeMethodEntry(
                    java_name=info.java_name,
                    signature=info.jni_signature,
                    symbol=info.native_symbol,
                    ret_jni=_jni_return_type(self.am, method),
                    param_str=_jni_param_list(self.am, method),
                    is_static=False,
                )
            )
        return reg

    #######################
    # Emission            #
    #######################

    def gen_forward_decls(
        self,
        target: CSourceWriter,
        registrations: list[ClassRegistration],
    ):
        for reg in registrations:
            for method in reg.methods:
                receiver = "jclass /*cls*/" if method.is_static else "jobject /*obj*/"
                target.writelns(
                    f'extern "C" JNIEXPORT {method.ret_jni} JNICALL {method.symbol}('
                    f"JNIEnv* env, {receiver}{method.param_str});"
                )
        target.writelns("")

    def gen_onload(
        self,
        target: CSourceWriter,
        registrations: list[ClassRegistration],
    ):
        with target.indented(
            "JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void* /*reserved*/) {",
            "}",
        ):
            target.writelns(
                "JNIEnv* env = nullptr;",
            )
            with target.indented(
                "if (vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) != JNI_OK) {",
                "}",
            ):
                target.writelns("return JNI_ERR;")

            for index, reg in enumerate(registrations):
                target.writelns("")
                self.gen_register_class(target, index, reg)

            target.writelns(
                "",
                "return JNI_VERSION_1_6;",
            )

    def gen_register_class(
        self,
        target: CSourceWriter,
        index: int,
        reg: ClassRegistration,
    ):
        cls = f"cls_{index}"
        methods = f"methods_{index}"
        count = len(reg.methods)
        target.writelns(
            f'jclass {cls} = env->FindClass("{reg.descriptor}");',
        )
        with target.indented(
            f"if ({cls} == nullptr) {{",
            "}",
        ):
            target.writelns("return JNI_ERR;")
        with target.indented(
            f"JNINativeMethod {methods}[] = {{",
            "};",
        ):
            for method in reg.methods:
                target.writelns(
                    f'{{"{method.java_name}", "{method.signature}", '
                    f"reinterpret_cast<void*>(&{method.symbol})}},"
                )
        with target.indented(
            f"if (env->RegisterNatives({cls}, {methods}, {count}) != JNI_OK) {{",
            "}",
        ):
            target.writelns("return JNI_ERR;")
