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

from typing import cast

from taihe.codegen.abi.analyses import (
    GlobFuncAbiInfo,
    IfaceMethodAbiInfo,
)
from taihe.codegen.abi.writer import CSourceWriter
from taihe.codegen.cpp.analyses import (
    GlobFuncCppUserInfo,
    IfaceCppInfo,
    IfaceMethodCppInfo,
    PackageCppUserInfo,
    StructCppInfo,
    TypeCppInfo,
)
from taihe.codegen.jni.analyses import (
    GlobFuncJniInfo,
    IfaceJniInfo,
    IfaceMethodJniInfo,
    PackageJniInfo,
    StructJniInfo,
    TypeJniInfo,
    get_config,
    getter_name,
    is_void_like,
    jni_type_of,
    setter_name,
)
from taihe.semantics.declarations import (
    GlobFuncDecl,
    IfaceDecl,
    IfaceMethodDecl,
    PackageDecl,
    PackageGroup,
    StructDecl,
    StructFieldDecl,
)
from taihe.semantics.types import NonVoidType, UnitType
from taihe.utils.analyses import AnalysisManager
from taihe.utils.outputs import GEN_CXX_SRC_GROUP, OutputManager


def _jni_zero(jni_ret: str) -> str:
    if jni_ret == "void":
        return "return;"
    if jni_ret in ("jboolean", "jbyte", "jshort", "jint", "jlong", "jfloat", "jdouble"):
        return "return 0;"
    return "return nullptr;"


class JniCodeGenerator:
    def __init__(self, oc: OutputManager, am: AnalysisManager):
        self.oc = oc
        self.am = am

    def generate(self, pg: PackageGroup):
        for pkg in pg.iterate():
            JniPackageSourceGenerator(self.oc, self.am, pkg).gen_package_source()


class JniPackageSourceGenerator:
    def __init__(self, oc: OutputManager, am: AnalysisManager, pkg: PackageDecl):
        self.am = am
        self.pkg = pkg
        pkg_jni_info = PackageJniInfo.get(am, pkg)
        self.target = CSourceWriter(
            oc,
            f"src/{pkg_jni_info.source}",
            group=GEN_CXX_SRC_GROUP,
        )

    ######################
    # Package generation #
    ######################

    def gen_package_source(self):
        pkg_cpp_user_info = PackageCppUserInfo.get(self.am, self.pkg)
        with self.target:
            self.target.add_include("taihe/expected.hpp")
            self.target.add_include("taihe/error.hpp")
            self.target.add_include(pkg_cpp_user_info.header)
            self.target.writelns(
                "#include <jni.h>",
                "",
            )
            self.gen_throw_helper()
            for struct in self.pkg.structs:
                self.gen_struct(struct)
            for iface in self.pkg.interfaces:
                self.gen_iface(iface)
            for func in self.pkg.functions:
                self.gen_global_func(func)

    def gen_throw_helper(self):
        with self.target.indented(
            "static void taihe_jni_throw(JNIEnv* env, ::taihe::error const& err) {",
            "}",
        ):
            self.target.writelns(
                "::taihe::string msg = err.message();",
                'jclass cls = env->FindClass("java/lang/RuntimeException");',
            )
            with self.target.indented(
                "if (cls != nullptr) {",
                "}",
            ):
                self.target.writelns(
                    "env->ThrowNew(cls, msg.data());",
                )
        self.target.writelns("")

    #######################
    # Shared codegen aids #
    #######################

    def native_symbol(
        self, pkg_jni_info: PackageJniInfo, class_name: str, method_name: str
    ) -> str:
        java_pkg_sym = pkg_jni_info.java_pkg.replace(".", "_")
        return f"Java_{java_pkg_sym}_{class_name}_{method_name}"

    def jni_param_list(self, func: GlobFuncDecl | IfaceMethodDecl) -> str:
        parts = []
        for param in func.params:
            if is_void_like(param.ty):
                continue
            info = TypeJniInfo.get(self.am, param.ty)
            parts.append(f"{info.jni_type} {param.name}")
        if not parts:
            return ""
        return ", " + ", ".join(parts)

    def jni_return_type(self, func: GlobFuncDecl | IfaceMethodDecl) -> str:
        return jni_type_of(self.am, func.return_ty)

    def gen_unwrap_this(self, cpp_owner: str):
        self.target.writelns(
            f"jclass this_cls = env->GetObjectClass(obj);",
            f'jfieldID this_handle_fid = env->GetFieldID(this_cls, "handle", "J");',
            f"jlong this_handle = env->GetLongField(obj, this_handle_fid);",
            f"{cpp_owner}* cpp_ptr = reinterpret_cast<{cpp_owner}*>(this_handle);",
        )

    def gen_wrap_object(self, java_desc: str, ptr_expr: str):
        self.target.writelns(
            f'jclass wrap_cls = env->FindClass("{java_desc}");',
            f'jmethodID wrap_ctor = env->GetMethodID(wrap_cls, "<init>", "(J)V");',
            f"jobject wrap_obj = env->NewObject(wrap_cls, wrap_ctor, reinterpret_cast<jlong>({ptr_expr}));",
        )

    def gen_read_func_params(
        self,
        func: GlobFuncDecl | IfaceMethodDecl,
        err_stmt: str,
    ) -> list[str]:
        cpp_exprs = []
        for param in func.params:
            if is_void_like(param.ty):
                continue
            info = TypeJniInfo.get(self.am, param.ty)
            from_jni = f"from_jni_arg_{param.name}"
            tmp = f"from_jni_tmp_{param.name}"
            info.gen_from_jni(self.target, from_jni)
            self.target.writelns(
                f"auto {tmp} = {from_jni}(env, {param.name});",
            )
            with self.target.indented(f"if (!{tmp}.has_value()) {{", "}"):
                self.target.writelns(
                    f"taihe_jni_throw(env, {tmp}.error());",
                    err_stmt,
                )
            cpp_exprs.append(f"std::move({tmp}).value()")
        return cpp_exprs

    def gen_call_and_return(
        self,
        func: GlobFuncDecl | IfaceMethodDecl,
        invoke: str,
        is_noexcept: bool,
        jni_ret: str,
    ):
        return_ty = func.return_ty
        has_return = isinstance(return_ty, NonVoidType) and not isinstance(
            return_ty,
            UnitType,
        )
        err_stmt = _jni_zero(jni_ret)
        if isinstance(return_ty, NonVoidType) and not isinstance(return_ty, UnitType):
            cpp_owner = TypeCppInfo.get(self.am, return_ty).as_owner
        else:
            cpp_owner = "void"
        cpp_result_type = (
            cpp_owner
            if is_noexcept
            else f"::taihe::expected<{cpp_owner}, ::taihe::error>"
        )

        if not has_return:
            if is_noexcept:
                self.target.writelns(f"{invoke};")
            else:
                self.target.writelns(f"{cpp_result_type} cpp_result = {invoke};")
                with self.target.indented(f"if (!cpp_result.has_value()) {{", "}"):
                    self.target.writelns(
                        f"taihe_jni_throw(env, cpp_result.error());",
                        err_stmt,
                    )
            return

        self.target.writelns(f"{cpp_result_type} cpp_result = {invoke};")
        if is_noexcept:
            result = "std::move(cpp_result)"
        else:
            with self.target.indented(f"if (!cpp_result.has_value()) {{", "}"):
                self.target.writelns(
                    f"taihe_jni_throw(env, cpp_result.error());",
                    err_stmt,
                )
            result = "std::move(cpp_result).value()"
        return_info = TypeJniInfo.get(self.am, cast(NonVoidType, return_ty))
        return_info.gen_into_jni(self.target, "into_jni_result")
        self.target.writelns(f"return into_jni_result(env, {result});")

    ########################
    # Global functions     #
    ########################

    def gen_global_func(self, func: GlobFuncDecl):
        func_jni_info = GlobFuncJniInfo.get(self.am, func)
        func_abi_info = GlobFuncAbiInfo.get(self.am, func)
        func_cpp_info = GlobFuncCppUserInfo.get(self.am, func)
        jni_ret = self.jni_return_type(func)
        sym = func_jni_info.native_symbol
        with self.target.indented(
            f'extern "C" JNIEXPORT {jni_ret} JNICALL {sym}(JNIEnv* env, jclass /*cls*/{self.jni_param_list(func)}) {{',
            f"}}",
        ):
            cpp_exprs = self.gen_read_func_params(func, _jni_zero(jni_ret))
            invoke = f"{func_cpp_info.full_name}({', '.join(cpp_exprs)})"
            self.gen_call_and_return(func, invoke, func_abi_info.is_noexcept, jni_ret)
        self.target.writelns("")

    ########################
    # Structs               #
    ########################

    def gen_struct(self, struct: StructDecl):
        struct_cpp_info = StructCppInfo.get(self.am, struct)
        struct_jni_info = StructJniInfo.get(self.am, struct)
        self.gen_struct_create(struct, struct_cpp_info, struct_jni_info)
        if get_config(self.am).generate_destroy:
            self.gen_struct_destroy(struct_cpp_info, struct_jni_info)
        for field in struct.fields:
            if is_void_like(field.ty):
                continue
            self.gen_struct_getter(struct, struct_cpp_info, struct_jni_info, field)
            self.gen_struct_setter(struct, struct_cpp_info, struct_jni_info, field)

    def gen_struct_create(
        self,
        struct: StructDecl,
        struct_cpp_info: StructCppInfo,
        struct_jni_info: StructJniInfo,
    ):
        pkg_jni_info = PackageJniInfo.get(self.am, self.pkg)
        sym = self.native_symbol(pkg_jni_info, struct_jni_info.java_name, "create")
        params_parts = []
        for field in struct.fields:
            if is_void_like(field.ty):
                continue
            info = TypeJniInfo.get(self.am, field.ty)
            params_parts.append(f"{info.jni_type} {field.name}")
        params_str = (", " + ", ".join(params_parts)) if params_parts else ""
        with self.target.indented(
            f'extern "C" JNIEXPORT jobject JNICALL {sym}(JNIEnv* env, jclass /*cls*/{params_str}) {{',
            f"}}",
        ):
            cpp_exprs = []
            for field in struct.fields:
                if is_void_like(field.ty):
                    continue
                info = TypeJniInfo.get(self.am, field.ty)
                from_jni = f"from_jni_field_{field.name}"
                tmp = f"from_jni_tmp_{field.name}"
                info.gen_from_jni(self.target, from_jni)
                self.target.writelns(f"auto {tmp} = {from_jni}(env, {field.name});")
                with self.target.indented(f"if (!{tmp}.has_value()) {{", "}"):
                    self.target.writelns(
                        f"taihe_jni_throw(env, {tmp}.error());",
                        "return nullptr;",
                    )
                cpp_exprs.append(f"std::move({tmp}).value()")
            cpp_exprs_str = ", ".join(cpp_exprs)
            self.target.writelns(
                f"auto* cpp_ptr = new {struct_cpp_info.as_owner}{{{cpp_exprs_str}}};",
            )
            self.gen_wrap_object(struct_jni_info.java_desc, "cpp_ptr")
            self.target.writelns("return wrap_obj;")
        self.target.writelns("")

    def gen_struct_destroy(
        self,
        struct_cpp_info: StructCppInfo,
        struct_jni_info: StructJniInfo,
    ):
        pkg_jni_info = PackageJniInfo.get(self.am, self.pkg)
        sym = self.native_symbol(pkg_jni_info, struct_jni_info.java_name, "destroy")
        with self.target.indented(
            f'extern "C" JNIEXPORT void JNICALL {sym}(JNIEnv* env, jobject obj) {{',
            f"}}",
        ):
            self.gen_unwrap_this(struct_cpp_info.as_owner)
            self.target.writelns("delete cpp_ptr;")
        self.target.writelns("")

    def gen_struct_getter(
        self,
        struct: StructDecl,
        struct_cpp_info: StructCppInfo,
        struct_jni_info: StructJniInfo,
        field: StructFieldDecl,
    ):
        pkg_jni_info = PackageJniInfo.get(self.am, self.pkg)
        info = TypeJniInfo.get(self.am, field.ty)
        sym = self.native_symbol(
            pkg_jni_info,
            struct_jni_info.java_name,
            getter_name(field.name),
        )
        with self.target.indented(
            f'extern "C" JNIEXPORT {info.jni_type} JNICALL {sym}(JNIEnv* env, jobject obj) {{',
            f"}}",
        ):
            self.gen_unwrap_this(struct_cpp_info.as_owner)
            info.gen_into_jni(self.target, "into_jni_field")
            self.target.writelns(f"return into_jni_field(env, cpp_ptr->{field.name});")
        self.target.writelns("")

    def gen_struct_setter(
        self,
        struct: StructDecl,
        struct_cpp_info: StructCppInfo,
        struct_jni_info: StructJniInfo,
        field: StructFieldDecl,
    ):
        pkg_jni_info = PackageJniInfo.get(self.am, self.pkg)
        info = TypeJniInfo.get(self.am, field.ty)
        sym = self.native_symbol(
            pkg_jni_info,
            struct_jni_info.java_name,
            setter_name(field.name),
        )
        with self.target.indented(
            f'extern "C" JNIEXPORT void JNICALL {sym}(JNIEnv* env, jobject obj, {info.jni_type} value) {{',
            f"}}",
        ):
            self.gen_unwrap_this(struct_cpp_info.as_owner)
            info.gen_from_jni(self.target, "from_jni_field")
            self.target.writelns("auto from_jni_tmp = from_jni_field(env, value);")
            with self.target.indented("if (!from_jni_tmp.has_value()) {", "}"):
                self.target.writelns(
                    "taihe_jni_throw(env, from_jni_tmp.error());",
                    "return;",
                )
            self.target.writelns(
                f"cpp_ptr->{field.name} = std::move(from_jni_tmp).value();",
            )
        self.target.writelns("")

    ########################
    # Interfaces            #
    ########################

    def gen_iface(self, iface: IfaceDecl):
        iface_cpp_info = IfaceCppInfo.get(self.am, iface)
        iface_jni_info = IfaceJniInfo.get(self.am, iface)
        if get_config(self.am).generate_destroy:
            self.gen_iface_destroy(iface_cpp_info, iface_jni_info)
        for method in iface.methods:
            self.gen_iface_method(iface, iface_cpp_info, iface_jni_info, method)

    def gen_iface_destroy(
        self,
        iface_cpp_info: IfaceCppInfo,
        iface_jni_info: IfaceJniInfo,
    ):
        pkg_jni_info = PackageJniInfo.get(self.am, self.pkg)
        sym = self.native_symbol(pkg_jni_info, iface_jni_info.java_name, "destroy")
        with self.target.indented(
            f'extern "C" JNIEXPORT void JNICALL {sym}(JNIEnv* env, jobject obj) {{',
            f"}}",
        ):
            self.gen_unwrap_this(iface_cpp_info.as_owner)
            self.target.writelns("delete cpp_ptr;")
        self.target.writelns("")

    def gen_iface_method(
        self,
        iface: IfaceDecl,
        iface_cpp_info: IfaceCppInfo,
        iface_jni_info: IfaceJniInfo,
        method: IfaceMethodDecl,
    ):
        method_jni_info = IfaceMethodJniInfo.get(self.am, method)
        method_cpp_info = IfaceMethodCppInfo.get(self.am, method)
        method_abi_info = IfaceMethodAbiInfo.get(self.am, method)
        jni_ret = self.jni_return_type(method)
        sym = method_jni_info.native_symbol
        with self.target.indented(
            f'extern "C" JNIEXPORT {jni_ret} JNICALL {sym}(JNIEnv* env, jobject obj{self.jni_param_list(method)}) {{',
            f"}}",
        ):
            self.gen_unwrap_this(iface_cpp_info.as_owner)
            cpp_exprs = self.gen_read_func_params(method, _jni_zero(jni_ret))
            invoke = f"cpp_ptr->{method_cpp_info.call_name}({', '.join(cpp_exprs)})"
            self.gen_call_and_return(
                method, invoke, method_abi_info.is_noexcept, jni_ret
            )
        self.target.writelns("")
