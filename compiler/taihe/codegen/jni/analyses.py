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

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import cast

from typing_extensions import override

from taihe.codegen.abi.analyses import IfaceAbiInfo
from taihe.codegen.abi.writer import CSourceWriter
from taihe.codegen.ani.attributes import ExtendsAttr
from taihe.codegen.cpp.analyses import TypeCppInfo
from taihe.codegen.cpp.attributes import Encoding, EncodingAttr
from taihe.codegen.jni.attributes import (
    JavaNameAttr,
    JavaPackageAttr,
    NativeLibraryAttr,
)
from taihe.codegen.jni.signature import (
    method_signature,
    native_symbol,
)
from taihe.semantics.declarations import (
    EnumDecl,
    GlobFuncDecl,
    IfaceDecl,
    IfaceMethodDecl,
    PackageDecl,
    StructDecl,
    StructFieldDecl,
)
from taihe.semantics.types import (
    ArrayType,
    EnumType,
    IfaceType,
    MapType,
    NonVoidType,
    OpaqueType,
    OptionalType,
    ScalarKinds,
    ScalarType,
    SetType,
    StringType,
    StructType,
    UnitType,
    VectorType,
)
from taihe.semantics.visitor import NonVoidTypeVisitor
from taihe.utils.analyses import AbstractAnalysis, AnalysisManager


def upper_first(name: str) -> str:
    if not name:
        return name
    return name[0].upper() + name[1:]


def java_desc_of(java_pkg: str, name: str) -> str:
    return java_pkg.replace(".", "/") + "/" + name


def getter_name(field_name: str) -> str:
    return "get" + upper_first(field_name)


def setter_name(field_name: str) -> str:
    return "set" + upper_first(field_name)


def is_void_like(ty) -> bool:
    return not isinstance(ty, NonVoidType) or isinstance(ty, UnitType)


def jni_sig_of(am: AnalysisManager, ty) -> str:
    if is_void_like(ty):
        return "V"
    return TypeJniInfo.get(am, ty).jni_sig


def java_type_of(am: AnalysisManager, ty) -> str:
    if is_void_like(ty):
        return "void"
    return TypeJniInfo.get(am, ty).java_type


def jni_type_of(am: AnalysisManager, ty) -> str:
    if is_void_like(ty):
        return "void"
    return TypeJniInfo.get(am, ty).jni_type


@dataclass
class JniConfig:
    """Runtime configuration seeded by the backend.

    These are global (not per-declaration) knobs that affect code generation.
    They default to the same values used before the config mechanism existed.
    """

    register_natives: bool = False
    java_package: str | None = None
    native_library: str | None = None
    generate_destroy: bool = True


JNI_CONFIG_KEY = "jni-bridge-config"


class JniConfigAnalysis(AbstractAnalysis[str]):
    """Holder that seeds ``JniConfig`` into the ``AnalysisManager``.

    Instances are created by the backend during ``setup()`` and provided via
    ``AnalysisManager.provide``, so ``_create`` is never expected to run.
    """

    def __init__(self, am: AnalysisManager, key: str, config: JniConfig):
        del am, key
        self.config = config

    @classmethod
    @override
    def _create(cls, am: AnalysisManager, key: str) -> "JniConfigAnalysis":
        raise RuntimeError("JniConfigAnalysis must be provided by the backend")


def get_config(am: AnalysisManager) -> JniConfig:
    return JniConfigAnalysis.get(am, JNI_CONFIG_KEY).config


class PackageJniInfo(AbstractAnalysis[PackageDecl]):
    def __init__(self, am: AnalysisManager, p: PackageDecl) -> None:
        self.am = am
        self.pkg = p
        config = get_config(am)

        attr = JavaPackageAttr.get(p)
        self.java_pkg = config.java_package or (attr.java_package if attr else p.name)

        attr = NativeLibraryAttr.get(p)
        self.lib_name = config.native_library or (
            attr.lib_name if attr else p.segments[-1]
        )

        self.class_name = upper_first(p.segments[-1])
        self.java_dir = self.java_pkg.replace(".", "/")
        self.source = f"{p.name}.jni.cpp"

    @classmethod
    @override
    def _create(cls, am: AnalysisManager, p: PackageDecl) -> "PackageJniInfo":
        return PackageJniInfo(am, p)


class StructJniInfo(AbstractAnalysis[StructDecl]):
    def __init__(self, am: AnalysisManager, d: StructDecl) -> None:
        self.pkg_jni_info = PackageJniInfo.get(am, d.parent_pkg)
        self.java_name = d.name
        self.java_desc = java_desc_of(self.pkg_jni_info.java_pkg, d.name)
        self.jni_sig = f"L{self.java_desc};"

        # Flattened field paths. A field declared with `@extends` contributes its
        # parent's fields (prefixed with the field itself), so the resulting
        # struct exposes inherited fields directly.
        self.final_fields: list[list[StructFieldDecl]] = []
        for field in d.fields:
            if extend := ExtendsAttr.get(field):
                parent_info = StructJniInfo.get(am, extend.ty.decl)
                self.final_fields.extend(
                    [field, *parts] for parts in parent_info.final_fields
                )
            else:
                self.final_fields.append([field])

    @classmethod
    @override
    def _create(cls, am: AnalysisManager, d: StructDecl) -> "StructJniInfo":
        return StructJniInfo(am, d)


class IfaceJniInfo(AbstractAnalysis[IfaceDecl]):
    def __init__(self, am: AnalysisManager, d: IfaceDecl) -> None:
        self.pkg_jni_info = PackageJniInfo.get(am, d.parent_pkg)
        self.java_name = d.name
        self.java_desc = java_desc_of(self.pkg_jni_info.java_pkg, d.name)
        self.jni_sig = f"L{self.java_desc};"

        # Methods callable on this interface, flattened to include ancestors
        # (child declared first, then each parent via DFS). Each entry is a
        # (java_name, method) pair; the java_name may be renamed via @java_name.
        self.methods: list[tuple[str, IfaceMethodDecl]] = []
        iface_abi_info = IfaceAbiInfo.get(am, d)
        for ancestor_info in iface_abi_info.ancestor_infos.values():
            for method in ancestor_info.anc_iface.methods:
                self.methods.append(
                    (IfaceMethodJniInfo.get(am, method).java_name, method)
                )

    @classmethod
    @override
    def _create(cls, am: AnalysisManager, d: IfaceDecl) -> "IfaceJniInfo":
        return IfaceJniInfo(am, d)


class EnumJniInfo(AbstractAnalysis[EnumDecl]):
    def __init__(self, am: AnalysisManager, d: EnumDecl) -> None:
        self.pkg_jni_info = PackageJniInfo.get(am, d.parent_pkg)
        self.java_name = d.name
        self.java_desc = java_desc_of(self.pkg_jni_info.java_pkg, d.name)
        self.jni_sig = f"L{self.java_desc};"

    @classmethod
    @override
    def _create(cls, am: AnalysisManager, d: EnumDecl) -> "EnumJniInfo":
        return EnumJniInfo(am, d)


class GlobFuncJniInfo(AbstractAnalysis[GlobFuncDecl]):
    def __init__(self, am: AnalysisManager, f: GlobFuncDecl) -> None:
        self.pkg_jni_info = PackageJniInfo.get(am, f.parent_pkg)
        if attr := JavaNameAttr.get(f):
            self.java_name = attr.java_name
        else:
            self.java_name = f.name

        self.native_symbol = native_symbol(
            self.pkg_jni_info.java_pkg,
            self.pkg_jni_info.class_name,
            self.java_name,
        )
        self.jni_signature = method_signature(
            [
                jni_sig_of(am, param.ty)
                for param in f.params
                if not is_void_like(param.ty)
            ],
            jni_sig_of(am, f.return_ty),
        )

    @classmethod
    @override
    def _create(cls, am: AnalysisManager, f: GlobFuncDecl) -> "GlobFuncJniInfo":
        return GlobFuncJniInfo(am, f)


class IfaceMethodJniInfo(AbstractAnalysis[IfaceMethodDecl]):
    def __init__(self, am: AnalysisManager, f: IfaceMethodDecl) -> None:
        self.pkg_jni_info = PackageJniInfo.get(am, f.parent_pkg)
        if attr := JavaNameAttr.get(f):
            self.java_name = attr.java_name
        else:
            self.java_name = f.name

        self.jni_signature = method_signature(
            [
                jni_sig_of(am, param.ty)
                for param in f.params
                if not is_void_like(param.ty)
            ],
            jni_sig_of(am, f.return_ty),
        )

    @classmethod
    @override
    def _create(cls, am: AnalysisManager, f: IfaceMethodDecl) -> "IfaceMethodJniInfo":
        return IfaceMethodJniInfo(am, f)


SCALAR_JNI_MAP = {
    ScalarKinds.BOOL: ("boolean", "jboolean", "Z"),
    ScalarKinds.I8: ("byte", "jbyte", "B"),
    ScalarKinds.I16: ("short", "jshort", "S"),
    ScalarKinds.I32: ("int", "jint", "I"),
    ScalarKinds.I64: ("long", "jlong", "J"),
    ScalarKinds.U8: ("byte", "jbyte", "B"),
    ScalarKinds.U16: ("short", "jshort", "S"),
    ScalarKinds.U32: ("int", "jint", "I"),
    ScalarKinds.U64: ("long", "jlong", "J"),
    ScalarKinds.F32: ("float", "jfloat", "F"),
    ScalarKinds.F64: ("double", "jdouble", "D"),
}


class TypeJniInfo(AbstractAnalysis[NonVoidType], metaclass=ABCMeta):
    java_type: str
    jni_type: str
    jni_sig: str

    def __init__(self, am: AnalysisManager, t: NonVoidType):
        self.am = am
        self.cpp_info = TypeCppInfo.get(am, t)

    @classmethod
    @override
    def _create(cls, am: AnalysisManager, t: NonVoidType) -> "TypeJniInfo":
        return t.accept(TypeJniInfoDispatcher(am))

    @abstractmethod
    def gen_from_jni(self, target: CSourceWriter, name: str): ...

    @abstractmethod
    def gen_into_jni(self, target: CSourceWriter, name: str): ...


class ScalarTypeJniInfo(TypeJniInfo):
    def __init__(self, am: AnalysisManager, t: ScalarType):
        super().__init__(am, t)
        self.java_type, self.jni_type, self.jni_sig = SCALAR_JNI_MAP[t.kind]

    @override
    def gen_from_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.jni_type} jni_input) -> ::taihe::expected<{self.cpp_info.as_owner}, ::taihe::error> {{",
            f"}};",
        ):
            target.writelns(
                f"return static_cast<{self.cpp_info.as_owner}>(jni_input);",
            )

    @override
    def gen_into_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.cpp_info.as_param} cpp_value) -> {self.jni_type} {{",
            f"}};",
        ):
            target.writelns(
                f"return static_cast<{self.jni_type}>(cpp_value);",
            )


class OpaqueTypeJniInfo(TypeJniInfo):
    def __init__(self, am: AnalysisManager, t: OpaqueType):
        super().__init__(am, t)
        self.java_type = "long"
        self.jni_type = "jlong"
        self.jni_sig = "J"

    @override
    def gen_from_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, jlong jni_input) -> ::taihe::expected<{self.cpp_info.as_owner}, ::taihe::error> {{",
            f"}};",
        ):
            target.writelns(
                f"return static_cast<{self.cpp_info.as_owner}>(jni_input);",
            )

    @override
    def gen_into_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.cpp_info.as_param} cpp_value) -> jlong {{",
            f"}};",
        ):
            target.writelns(
                f"return static_cast<jlong>(cpp_value);",
            )


class UnitTypeJniInfo(TypeJniInfo):
    def __init__(self, am: AnalysisManager, t: UnitType):
        super().__init__(am, t)
        self.java_type = "void"
        self.jni_type = "void"
        self.jni_sig = "V"

    @override
    def gen_from_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env) -> ::taihe::expected<{self.cpp_info.as_owner}, ::taihe::error> {{",
            f"}};",
        ):
            target.writelns(
                f"return {self.cpp_info.as_owner}{{}};",
            )

    @override
    def gen_into_jni(self, target: CSourceWriter, name: str):
        raise ValueError("unit type does not need a JNI conversion")


class Utf8StringTypeJniInfo(TypeJniInfo):
    def __init__(self, am: AnalysisManager, t: StringType):
        super().__init__(am, t)
        self.java_type = "String"
        self.jni_type = "jstring"
        self.jni_sig = "Ljava/lang/String;"

    @override
    def gen_from_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, jstring jni_input) -> ::taihe::expected<{self.cpp_info.as_owner}, ::taihe::error> {{",
            f"}};",
        ):
            target.writelns(
                f'if (jni_input == nullptr) {{ return ::taihe::unexpected(::taihe::error("null string")); }}',
                f"const char* chars = env->GetStringUTFChars(jni_input, nullptr);",
                f"{self.cpp_info.as_owner} result(chars);",
                f"env->ReleaseStringUTFChars(jni_input, chars);",
                f"return result;",
            )

    @override
    def gen_into_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.cpp_info.as_param} cpp_value) -> jstring {{",
            f"}};",
        ):
            target.writelns(
                f"return env->NewStringUTF(cpp_value.data());",
            )


class Utf16StringTypeJniInfo(TypeJniInfo):
    def __init__(self, am: AnalysisManager, t: StringType):
        super().__init__(am, t)
        self.java_type = "String"
        self.jni_type = "jstring"
        self.jni_sig = "Ljava/lang/String;"

    @override
    def gen_from_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, jstring jni_input) -> ::taihe::expected<{self.cpp_info.as_owner}, ::taihe::error> {{",
            f"}};",
        ):
            target.writelns(
                f'if (jni_input == nullptr) {{ return ::taihe::unexpected(::taihe::error("null string")); }}',
                f"const jchar* chars = env->GetStringChars(jni_input, nullptr);",
                f"{self.cpp_info.as_owner} result(reinterpret_cast<const char16_t*>(chars), static_cast<std::size_t>(env->GetStringLength(jni_input)));",
                f"env->ReleaseStringChars(jni_input, chars);",
                f"return result;",
            )

    @override
    def gen_into_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.cpp_info.as_param} cpp_value) -> jstring {{",
            f"}};",
        ):
            target.writelns(
                f"return env->NewString(reinterpret_cast<const jchar*>(cpp_value.data()), static_cast<jsize>(cpp_value.size()));",
            )


class CommonStringTypeJniInfo(TypeJniInfo):
    def __init__(self, am: AnalysisManager, t: StringType):
        super().__init__(am, t)
        self.java_type = "String"
        self.jni_type = "jstring"
        self.jni_sig = "Ljava/lang/String;"

    @override
    def gen_from_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, jstring jni_input) -> ::taihe::expected<{self.cpp_info.as_owner}, ::taihe::error> {{",
            f"}};",
        ):
            target.writelns(
                f'if (jni_input == nullptr) {{ return ::taihe::unexpected(::taihe::error("null string")); }}',
                f"const char* chars = env->GetStringUTFChars(jni_input, nullptr);",
                f"{self.cpp_info.as_owner} result(chars);",
                f"env->ReleaseStringUTFChars(jni_input, chars);",
                f"return result;",
            )

    @override
    def gen_into_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.cpp_info.as_param} cpp_value) -> jstring {{",
            f"}};",
        ):
            target.writelns(
                f"::taihe::string tmp(cpp_value);",
                f"return env->NewStringUTF(tmp.data());",
            )


class StructTypeJniInfo(TypeJniInfo):
    def __init__(self, am: AnalysisManager, t: StructType):
        super().__init__(am, t)
        self.type = t
        struct_jni_info = StructJniInfo.get(am, t.decl)
        self.java_type = struct_jni_info.java_name
        self.jni_type = "jobject"
        self.jni_sig = struct_jni_info.jni_sig

    @override
    def gen_from_jni(self, target: CSourceWriter, name: str):
        struct_jni_info = StructJniInfo.get(self.am, self.type.decl)
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, jobject jni_input) -> ::taihe::expected<{self.cpp_info.as_owner}, ::taihe::error> {{",
            f"}};",
        ):
            target.writelns(
                f'if (jni_input == nullptr) {{ return ::taihe::unexpected(::taihe::error("null object")); }}',
                f"jclass cls = env->GetObjectClass(jni_input);",
                f'jfieldID handle_fid = env->GetFieldID(cls, "handle", "J");',
                f"jlong handle = env->GetLongField(jni_input, handle_fid);",
                f"{self.cpp_info.as_owner}* cpp_ptr = reinterpret_cast<{self.cpp_info.as_owner}*>(handle);",
                f"return *cpp_ptr;",
            )

    @override
    def gen_into_jni(self, target: CSourceWriter, name: str):
        struct_jni_info = StructJniInfo.get(self.am, self.type.decl)
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.cpp_info.as_param} cpp_value) -> jobject {{",
            f"}};",
        ):
            target.writelns(
                f"{self.cpp_info.as_owner}* cpp_ptr = new {self.cpp_info.as_owner}(cpp_value);",
                f'jclass cls = env->FindClass("{struct_jni_info.java_desc}");',
                f'jmethodID ctor = env->GetMethodID(cls, "<init>", "(J)V");',
                f"return env->NewObject(cls, ctor, reinterpret_cast<jlong>(cpp_ptr));",
            )


class IfaceTypeJniInfo(TypeJniInfo):
    def __init__(self, am: AnalysisManager, t: IfaceType):
        super().__init__(am, t)
        self.type = t
        iface_jni_info = IfaceJniInfo.get(am, t.decl)
        self.java_type = iface_jni_info.java_name
        self.jni_type = "jobject"
        self.jni_sig = iface_jni_info.jni_sig

    @override
    def gen_from_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, jobject jni_input) -> ::taihe::expected<{self.cpp_info.as_owner}, ::taihe::error> {{",
            f"}};",
        ):
            target.writelns(
                f'if (jni_input == nullptr) {{ return ::taihe::unexpected(::taihe::error("null object")); }}',
                f"jclass cls = env->GetObjectClass(jni_input);",
                f'jfieldID handle_fid = env->GetFieldID(cls, "handle", "J");',
                f"jlong handle = env->GetLongField(jni_input, handle_fid);",
                f"{self.cpp_info.as_owner}* cpp_ptr = reinterpret_cast<{self.cpp_info.as_owner}*>(handle);",
                f"return *cpp_ptr;",
            )

    @override
    def gen_into_jni(self, target: CSourceWriter, name: str):
        iface_jni_info = IfaceJniInfo.get(self.am, self.type.decl)
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.cpp_info.as_param} cpp_value) -> jobject {{",
            f"}};",
        ):
            target.writelns(
                f"{self.cpp_info.as_owner}* cpp_ptr = new {self.cpp_info.as_owner}(cpp_value);",
                f'jclass cls = env->FindClass("{iface_jni_info.java_desc}");',
                f'jmethodID ctor = env->GetMethodID(cls, "<init>", "(J)V");',
                f"return env->NewObject(cls, ctor, reinterpret_cast<jlong>(cpp_ptr));",
            )


class EnumTypeJniInfo(TypeJniInfo):
    def __init__(self, am: AnalysisManager, t: EnumType):
        super().__init__(am, t)
        self.type = t
        enum_jni_info = EnumJniInfo.get(am, t.decl)
        self.java_type = enum_jni_info.java_name
        self.jni_type = "jobject"
        self.jni_sig = enum_jni_info.jni_sig

    @override
    def gen_from_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, jobject jni_input) -> ::taihe::expected<{self.cpp_info.as_owner}, ::taihe::error> {{",
            f"}};",
        ):
            target.writelns(
                f'if (jni_input == nullptr) {{ return ::taihe::unexpected(::taihe::error("null enum")); }}',
                f"jclass cls = env->GetObjectClass(jni_input);",
                f'jmethodID ordinal = env->GetMethodID(cls, "ordinal", "()I");',
                f"jint ord = env->CallIntMethod(jni_input, ordinal);",
                f"return static_cast<{self.cpp_info.as_owner}>(ord);",
            )

    @override
    def gen_into_jni(self, target: CSourceWriter, name: str):
        enum_decl = self.type.decl
        enum_jni_info = EnumJniInfo.get(self.am, enum_decl)
        cpp_name = self.cpp_info.as_owner
        items = list(enum_decl.items)
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.cpp_info.as_param} cpp_value) -> jobject {{",
            f"}};",
        ):
            target.writelns(
                f'jclass cls = env->FindClass("{enum_jni_info.java_desc}");',
                f"const char* item_name = nullptr;",
            )
            with target.indented(
                f"switch (static_cast<std::underlying_type_t<{cpp_name}>>(cpp_value)) {{",
                f"}}",
            ):
                for item in items:
                    target.writelns(
                        f"case static_cast<std::underlying_type_t<{cpp_name}>>({cpp_name}::{item.name}):",
                        f'    item_name = "{item.name}";',
                        f"    break;",
                    )
                if items:
                    first = items[0]
                    target.writelns(
                        f"default:",
                        f'    item_name = "{first.name}";',
                        f"    break;",
                    )
            target.writelns(
                f'jfieldID fid = env->GetStaticFieldID(cls, item_name, "{enum_jni_info.jni_sig}");',
                f"return env->GetStaticObjectField(cls, fid);",
            )


class OptionalTypeJniInfo(TypeJniInfo):
    def __init__(self, am: AnalysisManager, t: OptionalType):
        super().__init__(am, t)
        self.type = t
        item_jni_info = TypeJniInfo.get(am, t.item_ty)
        if isinstance(t.item_ty, ScalarType):
            raise ValueError(
                "Optional<scalar> is not supported by the JNI backend (v1)"
            )
        self.java_type = item_jni_info.java_type
        self.jni_type = item_jni_info.jni_type
        self.jni_sig = item_jni_info.jni_sig

    @override
    def gen_from_jni(self, target: CSourceWriter, name: str):
        item_jni_info = TypeJniInfo.get(self.am, self.type.item_ty)
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.jni_type} jni_input) -> ::taihe::expected<{self.cpp_info.as_owner}, ::taihe::error> {{",
            f"}};",
        ):
            item_jni_info.gen_from_jni(target, "from_jni_item")
            with target.indented(
                f"if (jni_input == nullptr) {{",
                f"}}",
            ):
                target.writelns(
                    f"return std::nullopt;",
                )
            target.writelns(
                f"return {self.cpp_info.as_owner}(std::in_place, TH_TRY(from_jni_item(env, jni_input)));",
            )

    @override
    def gen_into_jni(self, target: CSourceWriter, name: str):
        item_jni_info = TypeJniInfo.get(self.am, self.type.item_ty)
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.cpp_info.as_param} cpp_value) -> {self.jni_type} {{",
            f"}};",
        ):
            item_jni_info.gen_into_jni(target, "into_jni_item")
            with target.indented(
                f"if (cpp_value) {{",
                f"}}",
            ):
                target.writelns(
                    f"return into_jni_item(env, *cpp_value);",
                )
            target.writelns(
                f"return nullptr;",
            )


# Mapping from a scalar JNI type to its (primitive array type, region stem). The
# region stem is used to compose Get/Set<X>ArrayRegion and New<X>Array.
_JNI_ARRAY_TYPES = {
    "jboolean": ("jbooleanArray", "Boolean"),
    "jbyte": ("jbyteArray", "Byte"),
    "jshort": ("jshortArray", "Short"),
    "jint": ("jintArray", "Int"),
    "jlong": ("jlongArray", "Long"),
    "jfloat": ("jfloatArray", "Float"),
    "jdouble": ("jdoubleArray", "Double"),
}

# Boxed Java type descriptors for scalar kinds, used when scalars appear as
# elements of ArrayList/HashMap/HashSet (which box primitives).
_SCALAR_BOXED_CLASS = {
    ScalarKinds.BOOL: "java/lang/Boolean",
    ScalarKinds.I8: "java/lang/Byte",
    ScalarKinds.I16: "java/lang/Short",
    ScalarKinds.I32: "java/lang/Integer",
    ScalarKinds.I64: "java/lang/Long",
    ScalarKinds.U8: "java/lang/Byte",
    ScalarKinds.U16: "java/lang/Short",
    ScalarKinds.U32: "java/lang/Integer",
    ScalarKinds.U64: "java/lang/Long",
    ScalarKinds.F32: "java/lang/Float",
    ScalarKinds.F64: "java/lang/Double",
}


def _is_scalar_item(info: TypeJniInfo) -> bool:
    return info.jni_type in _JNI_ARRAY_TYPES


def _java_element_type(am: AnalysisManager, item_ty: NonVoidType) -> str:
    """Return the boxed Java type name used inside collection generics."""
    info = TypeJniInfo.get(am, item_ty)
    if _is_scalar_item(info):
        scalar_ty = cast(ScalarType, item_ty)
        return _SCALAR_BOXED_CLASS[scalar_ty.kind].split("/")[-1]
    return info.java_type


def _gen_elem_from_jni(
    target: CSourceWriter,
    am: AnalysisManager,
    item_ty: NonVoidType,
    name: str,
):
    """Emit ``name`` = ``(JNIEnv*, jobject) -> expected<owner, error>``.

    Reference-typed elements reuse their regular conversion; scalar elements
    are unboxed from their Java wrapper object.
    """
    item_info = TypeJniInfo.get(am, item_ty)
    if not _is_scalar_item(item_info):
        item_info.gen_from_jni(target, name)
        return
    scalar_ty = cast(ScalarType, item_ty)
    boxed_cls = _SCALAR_BOXED_CLASS[scalar_ty.kind]
    _, jni_scalar, sig = SCALAR_JNI_MAP[scalar_ty.kind]
    java_prim = SCALAR_JNI_MAP[scalar_ty.kind][0]
    call = _JNI_ARRAY_TYPES[jni_scalar][1]
    with target.indented(
        f"static constexpr auto {name} = [](JNIEnv* env, jobject item) -> ::taihe::expected<{item_info.cpp_info.as_owner}, ::taihe::error> {{",
        f"}};",
    ):
        target.writelns(
            f'jclass boxed_cls = env->FindClass("{boxed_cls}");',
            f'jmethodID unbox_mid = env->GetMethodID(boxed_cls, "{java_prim}Value", "(){sig}");',
            f"{jni_scalar} v = env->Call{call}Method(item, unbox_mid);",
            f"return static_cast<{item_info.cpp_info.as_owner}>(v);",
        )


def _gen_elem_into_jni(
    target: CSourceWriter,
    am: AnalysisManager,
    item_ty: NonVoidType,
    name: str,
):
    """Emit ``name`` = ``(JNIEnv*, <item param>) -> jobject``.

    Reference-typed elements reuse their regular conversion; scalar elements
    are boxed into their Java wrapper object.
    """
    item_info = TypeJniInfo.get(am, item_ty)
    if not _is_scalar_item(item_info):
        item_info.gen_into_jni(target, name)
        return
    scalar_ty = cast(ScalarType, item_ty)
    boxed_cls = _SCALAR_BOXED_CLASS[scalar_ty.kind]
    _, jni_scalar, sig = SCALAR_JNI_MAP[scalar_ty.kind]
    with target.indented(
        f"static constexpr auto {name} = [](JNIEnv* env, {item_info.cpp_info.as_param} cpp_value) -> jobject {{",
        f"}};",
    ):
        target.writelns(
            f'jclass boxed_cls = env->FindClass("{boxed_cls}");',
            f'jmethodID value_of = env->GetStaticMethodID(boxed_cls, "valueOf", "({sig})L{boxed_cls};");',
            f"return env->CallStaticObjectMethod(boxed_cls, value_of, static_cast<{jni_scalar}>(cpp_value));",
        )


class ArrayTypeJniInfo(TypeJniInfo):
    def __init__(self, am: AnalysisManager, t: ArrayType):
        super().__init__(am, t)
        self.type = t
        item_info = TypeJniInfo.get(am, t.item_ty)
        self._is_scalar_item = _is_scalar_item(item_info)
        if self._is_scalar_item:
            _, jni_scalar, sig = SCALAR_JNI_MAP[cast(ScalarType, t.item_ty).kind]
            self._array_type, self._region = _JNI_ARRAY_TYPES[jni_scalar]
            self.java_type = f"{item_info.java_type}[]"
            self.jni_type = self._array_type
            self.jni_sig = f"[{sig}"
        else:
            self._array_type = "jobjectArray"
            self._region = ""
            self.java_type = f"{item_info.java_type}[]"
            self.jni_type = "jobjectArray"
            self.jni_sig = f"[{item_info.jni_sig}"

    @override
    def gen_from_jni(self, target: CSourceWriter, name: str):
        item_ty = self.type.item_ty
        item_cpp_info = TypeCppInfo.get(self.am, item_ty)
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.jni_type} jni_input) -> ::taihe::expected<{self.cpp_info.as_owner}, ::taihe::error> {{",
            f"}};",
        ):
            target.writelns(
                "jsize len = env->GetArrayLength(jni_input);",
                f"::taihe::array_builder<{item_cpp_info.as_owner}> builder(static_cast<std::size_t>(len));",
            )
            if self._is_scalar_item:
                _, jni_scalar, _ = SCALAR_JNI_MAP[cast(ScalarType, item_ty).kind]
                with target.indented(
                    "for (jsize i = 0; i < len; i++) {",
                    "}",
                ):
                    target.writelns(
                        f"{jni_scalar} item;",
                        f"env->Get{self._region}ArrayRegion(jni_input, i, 1, &item);",
                        f"builder.emplace_back(static_cast<{item_cpp_info.as_owner}>(item));",
                    )
            else:
                _gen_elem_from_jni(target, self.am, item_ty, "from_jni_item")
                with target.indented(
                    "for (jsize i = 0; i < len; i++) {",
                    "}",
                ):
                    target.writelns(
                        "jobject item = env->GetObjectArrayElement(jni_input, i);",
                        "builder.emplace_back(TH_TRY(from_jni_item(env, item)));",
                    )
            target.writelns("return std::move(builder).finish();")

    @override
    def gen_into_jni(self, target: CSourceWriter, name: str):
        item_ty = self.type.item_ty
        item_info = TypeJniInfo.get(self.am, item_ty)
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.cpp_info.as_param} cpp_value) -> {self.jni_type} {{",
            f"}};",
        ):
            target.writelns("jsize len = static_cast<jsize>(cpp_value.size());")
            if self._is_scalar_item:
                _, jni_scalar, _ = SCALAR_JNI_MAP[cast(ScalarType, item_ty).kind]
                target.writelns(
                    f"{self.jni_type} result = env->New{self._region}Array(len);",
                )
                with target.indented(
                    "for (jsize i = 0; i < len; i++) {",
                    "}",
                ):
                    target.writelns(
                        f"{jni_scalar} item = static_cast<{jni_scalar}>(cpp_value[i]);",
                        f"env->Set{self._region}ArrayRegion(result, i, 1, &item);",
                    )
                target.writelns("return result;")
            else:
                _gen_elem_into_jni(target, self.am, item_ty, "into_jni_item")
                elem_desc = item_info.jni_sig[1:-1]
                target.writelns(
                    f'jclass elem_cls = env->FindClass("{elem_desc}");',
                    "jobjectArray result = env->NewObjectArray(len, elem_cls, nullptr);",
                )
                with target.indented(
                    "for (jsize i = 0; i < len; i++) {",
                    "}",
                ):
                    target.writelns(
                        "jobject item = into_jni_item(env, cpp_value[i]);",
                        "env->SetObjectArrayElement(result, i, item);",
                    )
                target.writelns("return result;")


class VectorTypeJniInfo(TypeJniInfo):
    def __init__(self, am: AnalysisManager, t: VectorType):
        super().__init__(am, t)
        self.type = t
        self.java_type = f"java.util.ArrayList<{_java_element_type(am, t.val_ty)}>"
        self.jni_type = "jobject"
        self.jni_sig = "Ljava/util/ArrayList;"

    @override
    def gen_from_jni(self, target: CSourceWriter, name: str):
        val_ty = self.type.val_ty
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, jobject jni_input) -> ::taihe::expected<{self.cpp_info.as_owner}, ::taihe::error> {{",
            f"}};",
        ):
            target.writelns(
                'if (jni_input == nullptr) { return ::taihe::unexpected(::taihe::error("null list")); }',
            )
            _gen_elem_from_jni(target, self.am, val_ty, "from_jni_item")
            target.writelns(
                'jclass list_cls = env->FindClass("java/util/ArrayList");',
                'jmethodID size_mid = env->GetMethodID(list_cls, "size", "()I");',
                'jmethodID get_mid = env->GetMethodID(list_cls, "get", "(I)Ljava/lang/Object;");',
                "jint size = env->CallIntMethod(jni_input, size_mid);",
                f"{self.cpp_info.as_owner} result;",
                "result.reserve(static_cast<std::size_t>(size));",
            )
            with target.indented(
                "for (jint i = 0; i < size; i++) {",
                "}",
            ):
                target.writelns(
                    "jobject item = env->CallObjectMethod(jni_input, get_mid, i);",
                    "result.emplace_back(TH_TRY(from_jni_item(env, item)));",
                )
            target.writelns("return result;")

    @override
    def gen_into_jni(self, target: CSourceWriter, name: str):
        val_ty = self.type.val_ty
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.cpp_info.as_param} cpp_value) -> jobject {{",
            f"}};",
        ):
            _gen_elem_into_jni(target, self.am, val_ty, "into_jni_item")
            target.writelns(
                'jclass list_cls = env->FindClass("java/util/ArrayList");',
                'jmethodID ctor_mid = env->GetMethodID(list_cls, "<init>", "()V");',
                'jmethodID add_mid = env->GetMethodID(list_cls, "add", "(Ljava/lang/Object;)Z");',
                "jobject result = env->NewObject(list_cls, ctor_mid);",
            )
            with target.indented(
                "for (auto it = cpp_value.begin(); it != cpp_value.end(); ++it) {",
                "}",
            ):
                target.writelns(
                    "jobject item = into_jni_item(env, *it);",
                    "env->CallBooleanMethod(result, add_mid, item);",
                )
            target.writelns("return result;")


class MapTypeJniInfo(TypeJniInfo):
    def __init__(self, am: AnalysisManager, t: MapType):
        super().__init__(am, t)
        self.type = t
        key_java = _java_element_type(am, t.key_ty)
        val_java = _java_element_type(am, t.val_ty)
        self.java_type = f"java.util.HashMap<{key_java}, {val_java}>"
        self.jni_type = "jobject"
        self.jni_sig = "Ljava/util/HashMap;"

    @override
    def gen_from_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, jobject jni_input) -> ::taihe::expected<{self.cpp_info.as_owner}, ::taihe::error> {{",
            f"}};",
        ):
            target.writelns(
                'if (jni_input == nullptr) { return ::taihe::unexpected(::taihe::error("null map")); }',
            )
            _gen_elem_from_jni(target, self.am, self.type.key_ty, "from_jni_key")
            _gen_elem_from_jni(target, self.am, self.type.val_ty, "from_jni_value")
            target.writelns(
                'jclass map_cls = env->FindClass("java/util/HashMap");',
                'jmethodID entry_set_mid = env->GetMethodID(map_cls, "entrySet", "()Ljava/util/Set;");',
                "jobject entry_set = env->CallObjectMethod(jni_input, entry_set_mid);",
                'jclass set_cls = env->FindClass("java/util/Set");',
                'jmethodID to_array_mid = env->GetMethodID(set_cls, "toArray", "()[Ljava/lang/Object;");',
                "jobjectArray entries = static_cast<jobjectArray>(env->CallObjectMethod(entry_set, to_array_mid));",
                "jsize len = env->GetArrayLength(entries);",
                'jclass entry_cls = env->FindClass("java/util/Map$Entry");',
                'jmethodID get_key_mid = env->GetMethodID(entry_cls, "getKey", "()Ljava/lang/Object;");',
                'jmethodID get_value_mid = env->GetMethodID(entry_cls, "getValue", "()Ljava/lang/Object;");',
                f"{self.cpp_info.as_owner} result;",
            )
            with target.indented(
                "for (jsize i = 0; i < len; i++) {",
                "}",
            ):
                target.writelns(
                    "jobject entry = env->GetObjectArrayElement(entries, i);",
                    "jobject key = env->CallObjectMethod(entry, get_key_mid);",
                    "jobject value = env->CallObjectMethod(entry, get_value_mid);",
                    "result.emplace(TH_TRY(from_jni_key(env, key)), TH_TRY(from_jni_value(env, value)));",
                )
            target.writelns("return result;")

    @override
    def gen_into_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.cpp_info.as_param} cpp_value) -> jobject {{",
            f"}};",
        ):
            _gen_elem_into_jni(target, self.am, self.type.key_ty, "into_jni_key")
            _gen_elem_into_jni(target, self.am, self.type.val_ty, "into_jni_value")
            target.writelns(
                'jclass map_cls = env->FindClass("java/util/HashMap");',
                'jmethodID ctor_mid = env->GetMethodID(map_cls, "<init>", "()V");',
                'jmethodID put_mid = env->GetMethodID(map_cls, "put", "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;");',
                "jobject result = env->NewObject(map_cls, ctor_mid);",
            )
            with target.indented(
                "for (auto it = cpp_value.begin(); it != cpp_value.end(); ++it) {",
                "}",
            ):
                target.writelns(
                    "jobject key = into_jni_key(env, it->first);",
                    "jobject value = into_jni_value(env, it->second);",
                    "env->CallObjectMethod(result, put_mid, key, value);",
                )
            target.writelns("return result;")


class SetTypeJniInfo(TypeJniInfo):
    def __init__(self, am: AnalysisManager, t: SetType):
        super().__init__(am, t)
        self.type = t
        self.java_type = f"java.util.HashSet<{_java_element_type(am, t.key_ty)}>"
        self.jni_type = "jobject"
        self.jni_sig = "Ljava/util/HashSet;"

    @override
    def gen_from_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, jobject jni_input) -> ::taihe::expected<{self.cpp_info.as_owner}, ::taihe::error> {{",
            f"}};",
        ):
            target.writelns(
                'if (jni_input == nullptr) { return ::taihe::unexpected(::taihe::error("null set")); }',
            )
            _gen_elem_from_jni(target, self.am, self.type.key_ty, "from_jni_item")
            target.writelns(
                'jclass set_cls = env->FindClass("java/util/HashSet");',
                'jmethodID to_array_mid = env->GetMethodID(set_cls, "toArray", "()[Ljava/lang/Object;");',
                "jobjectArray items = static_cast<jobjectArray>(env->CallObjectMethod(jni_input, to_array_mid));",
                "jsize len = env->GetArrayLength(items);",
                f"{self.cpp_info.as_owner} result;",
            )
            with target.indented(
                "for (jsize i = 0; i < len; i++) {",
                "}",
            ):
                target.writelns(
                    "jobject item = env->GetObjectArrayElement(items, i);",
                    "result.emplace(TH_TRY(from_jni_item(env, item)));",
                )
            target.writelns("return result;")

    @override
    def gen_into_jni(self, target: CSourceWriter, name: str):
        with target.indented(
            f"static constexpr auto {name} = [](JNIEnv* env, {self.cpp_info.as_param} cpp_value) -> jobject {{",
            f"}};",
        ):
            _gen_elem_into_jni(target, self.am, self.type.key_ty, "into_jni_item")
            target.writelns(
                'jclass set_cls = env->FindClass("java/util/HashSet");',
                'jmethodID ctor_mid = env->GetMethodID(set_cls, "<init>", "()V");',
                'jmethodID add_mid = env->GetMethodID(set_cls, "add", "(Ljava/lang/Object;)Z");',
                "jobject result = env->NewObject(set_cls, ctor_mid);",
            )
            with target.indented(
                "for (auto it = cpp_value.begin(); it != cpp_value.end(); ++it) {",
                "}",
            ):
                target.writelns(
                    "jobject item = into_jni_item(env, *it);",
                    "env->CallBooleanMethod(result, add_mid, item);",
                )
            target.writelns("return result;")


class TypeJniInfoDispatcher(NonVoidTypeVisitor[TypeJniInfo]):
    def __init__(self, am: AnalysisManager):
        self.am = am

    @override
    def visit_scalar_type(self, t: ScalarType) -> TypeJniInfo:
        return ScalarTypeJniInfo(self.am, t)

    @override
    def visit_opaque_type(self, t: OpaqueType) -> TypeJniInfo:
        return OpaqueTypeJniInfo(self.am, t)

    @override
    def visit_unit_type(self, t: UnitType) -> TypeJniInfo:
        return UnitTypeJniInfo(self.am, t)

    @override
    def visit_string_type(self, t: StringType) -> TypeJniInfo:
        if encoding_attr := EncodingAttr.get(t.ref):
            match encoding_attr.value:
                case Encoding.UTF8:
                    return Utf8StringTypeJniInfo(self.am, t)
                case Encoding.UTF16:
                    return Utf16StringTypeJniInfo(self.am, t)
                case Encoding.COMMON:
                    return CommonStringTypeJniInfo(self.am, t)
        return Utf8StringTypeJniInfo(self.am, t)

    @override
    def visit_struct_type(self, t: StructType) -> TypeJniInfo:
        return StructTypeJniInfo(self.am, t)

    @override
    def visit_iface_type(self, t: IfaceType) -> TypeJniInfo:
        return IfaceTypeJniInfo(self.am, t)

    @override
    def visit_enum_type(self, t: EnumType) -> TypeJniInfo:
        return EnumTypeJniInfo(self.am, t)

    @override
    def visit_optional_type(self, t: OptionalType) -> TypeJniInfo:
        return OptionalTypeJniInfo(self.am, t)

    @override
    def visit_array_type(self, t: ArrayType) -> TypeJniInfo:
        return ArrayTypeJniInfo(self.am, t)

    @override
    def visit_vector_type(self, t: VectorType) -> TypeJniInfo:
        return VectorTypeJniInfo(self.am, t)

    @override
    def visit_map_type(self, t: MapType) -> TypeJniInfo:
        return MapTypeJniInfo(self.am, t)

    @override
    def visit_set_type(self, t: SetType) -> TypeJniInfo:
        return SetTypeJniInfo(self.am, t)

    @override
    def visit_union_type(self, t) -> TypeJniInfo:
        raise ValueError(
            f"Union type '{t.signature}' is not supported by the JNI backend (v1)"
        )

    @override
    def visit_generic_type(self, t) -> TypeJniInfo:
        raise ValueError(
            f"Generic type '{t.signature}' is not supported by the JNI backend (v1)"
        )

    @override
    def visit_callback_type(self, t) -> TypeJniInfo:
        raise ValueError(
            f"Callback type '{t.signature}' is not supported by the JNI backend (v1)"
        )
