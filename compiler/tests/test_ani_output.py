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

from io import StringIO
from pathlib import Path

import pytest
from taihe.driver.backend import BackendRegistry
from taihe.driver.contexts import CompilerInstance, CompilerInvocation
from taihe.driver.options import OptionRegistry
from taihe.utils.diagnostics import ConsoleDiagnosticsManager
from taihe.utils.outputs import BasicOutputConfig
from taihe.utils.resources import ResourceContext


@pytest.fixture(scope="module", autouse=True)
def _initialize_resources():
    try:
        ResourceContext.instance()
    except ValueError:
        ResourceContext.initialize()


def generate_ani_sources(
    project_dir: Path,
    sources: dict[str, str],
    *,
    use_ats: bool = False,
    output_name: str = "generated",
) -> dict[str, str]:
    source_dir = project_dir / "idl"
    source_dir.mkdir(exist_ok=True)
    source_files = []
    for name, source in sources.items():
        source_file = source_dir / f"{name}.taihe"
        source_file.write_text(source, encoding="utf-8")
        source_files.append(source_file)

    diagnostics = StringIO()
    dm = ConsoleDiagnosticsManager(diagnostics)
    backend_registry = BackendRegistry()
    backend_registry.register_builtins()
    config_types = backend_registry.resolve(["cpp-author", "ani-bridge"], dm)
    option_registry = OptionRegistry()
    for config_type in config_types:
        config_type.register_options_to(option_registry)
    options = option_registry.parse_options(
        ["arkts:use-ats-extension"] if use_ats else [], dm
    )
    backend_configs = [
        config
        for config_type in config_types
        if (config := config_type.from_options(options, dm)) is not None
    ]
    assert not dm.has_error, diagnostics.getvalue()

    output_dir = project_dir / output_name
    invocation = CompilerInvocation(
        src_files=source_files,
        output_config=BasicOutputConfig(dst_dir=output_dir),
        backend_configs=backend_configs,
    )
    CompilerInstance(invocation, dm).run()
    assert not dm.has_error, diagnostics.getvalue()
    return {
        path.relative_to(output_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in output_dir.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("use_ats", [False, True])
def test_ani_source_extensions(tmp_path: Path, use_ats: bool):
    outputs = generate_ani_sources(
        tmp_path,
        {"hello": "function add(a: i32, b: i32): String;"},
        use_ats=use_ats,
    )

    ext = "ats" if use_ats else "ets"
    other_ext = "ets" if use_ats else "ats"

    assert f"hello.{ext}" in outputs
    assert f"hello.{other_ext}" not in outputs
    assert (
        "native function _taihe_add_native(a: int, b: int): string;"
        in outputs[f"hello.{ext}"]
    )
    assert "export function add(a: int, b: int): string {" in outputs[f"hello.{ext}"]
    assert "return _taihe_add_native(a, b);" in outputs[f"hello.{ext}"]
    # .ets keeps the "use static" prologue; .ats omits it
    assert ('"use static";' in outputs[f"hello.{ext}"]) == (not use_ats)


def test_ats_replaces_ets_and_preserves_native_outputs(tmp_path: Path):
    sources = {
        "value": "struct Value { n: i32; }",
        "api": "from value use Value; function echo(value: Value): Value;",
    }
    original = generate_ani_sources(tmp_path, sources, output_name="ets")
    ats_outputs = generate_ani_sources(
        tmp_path, sources, use_ats=True, output_name="ats"
    )

    # Native (C/C++) outputs are identical regardless of extension
    native_names = {n for n in original if not n.endswith((".ets", ".ats"))}
    assert {n: ats_outputs[n] for n in native_names} == {
        n: original[n] for n in native_names
    }

    # .ets files are gone, .ats files are present
    assert not any(n.endswith(".ets") for n in ats_outputs)
    assert "value.ats" in ats_outputs
    assert "api.ats" in ats_outputs

    # value has no cross-module imports: content differs only by the
    # "use static" prologue which .ets keeps and .ats omits
    assert '"use static";' in original["value.ets"]
    assert '"use static";' not in ats_outputs["value.ats"]
    stripped = original["value.ets"].replace('"use static";\n', "", 1)
    assert ats_outputs["value.ats"] == stripped

    # api has imports: .ats uses .ats import paths
    assert "from './value.ets';" in original["api.ets"]
    assert "from './value.ats';" in ats_outputs["api.ats"]
    assert ".ets'" not in ats_outputs["api.ats"]


def test_ats_imports_nested_modules_and_keeps_local_type_aliases(tmp_path: Path):
    outputs = generate_ani_sources(
        tmp_path,
        {
            "value": """
                @!namespace("models/value", "data")
                struct Value { n: i32; }
                function copy(value: Value): Value;
            """,
            "extra": """
                @!namespace("models/value", "extra")
                struct Extra { text: String; }
            """,
            "api": """
                @!namespace("client/api")
                from value use Value;
                from extra use Extra;
                struct Request { value: Value; extra: Extra; }
                function echo(request: Request): Request;
            """,
        },
        use_ats=True,
    )

    # Only .ats files, no .ets
    assert not any(n.endswith(".ets") for n in outputs)
    assert "from './../models/value.ats';" in outputs["client/api.ats"]
    assert ".ets'" not in outputs["client/api.ats"]
    assert (
        "export type _taihe_models_value_data_Value = data.Value;"
        in outputs["models/value.ats"]
    )
    assert (
        "export type _taihe_client_api_Request = Request;" in outputs["client/api.ats"]
    )
    assert {name for name in outputs if name.endswith((".ets", ".ats"))} == {
        "models/value.ats",
        "client/api.ats",
    }
