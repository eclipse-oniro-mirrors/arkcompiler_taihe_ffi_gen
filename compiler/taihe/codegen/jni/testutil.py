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

"""Shared helpers for the JNI backend test suite."""

from io import StringIO
from pathlib import Path

from taihe.codegen.jni import JniBridgeBackendConfig
from taihe.driver.backend import BackendRegistry
from taihe.driver.contexts import CompilerInstance, CompilerInvocation
from taihe.driver.options import OptionRegistry
from taihe.utils.diagnostics import ConsoleDiagnosticsManager
from taihe.utils.outputs import BasicOutputConfig


def compile_jni_sources(
    project_dir: Path,
    sources: dict[str, str],
    *,
    register_natives: bool = False,
    extra_options: list[str] | None = None,
) -> tuple[dict[str, str], str]:
    """Compile in-memory ``.taihe`` sources with the JNI backend.

    Args:
        project_dir: A temporary directory to write sources and outputs to.
        sources: A mapping from package name to ``.taihe`` source text.
        register_natives: Emit the ``JNI_OnLoad``/``RegisterNatives`` file.
        extra_options: Additional ``-C`` config option strings.

    Returns:
        A tuple of (mapping from relative output path to content, diagnostics
        text). The diagnostics text must be empty on success.
    """
    source_dir = project_dir / "idl"
    source_dir.mkdir(exist_ok=True)
    source_files: list[Path] = []
    for name, source in sources.items():
        source_file = source_dir / f"{name}.taihe"
        source_file.write_text(source, encoding="utf-8")
        source_files.append(source_file)

    diagnostics = StringIO()
    dm = ConsoleDiagnosticsManager(diagnostics)
    backend_registry = BackendRegistry()
    backend_registry.register_builtins()
    backend_registry.register(JniBridgeBackendConfig)
    config_types = backend_registry.resolve(["jni-bridge"], dm)

    option_registry = OptionRegistry()
    for config_type in config_types:
        config_type.register_options_to(option_registry)
    config_args = (["register-natives"] if register_natives else []) + list(
        extra_options or []
    )
    options = option_registry.parse_options(config_args, dm)
    backend_configs = [
        config
        for config_type in config_types
        if (config := config_type.from_options(options, dm)) is not None
    ]

    output_dir = project_dir / "generated"
    invocation = CompilerInvocation(
        src_files=source_files,
        output_config=BasicOutputConfig(dst_dir=output_dir),
        backend_configs=backend_configs,
    )
    CompilerInstance(invocation, dm).run()
    outputs = {
        path.relative_to(output_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    return outputs, diagnostics.getvalue()
