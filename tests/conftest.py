"""复用同版本宿主的真实配置隔离夹具，优先加载独立仓库的插件源码。"""

import os
import sys
from pathlib import Path

plugin_root = Path(__file__).resolve().parents[1]
host_root = Path(
    os.environ.get("AUTO_MAS_HOST_SOURCE", str(plugin_root.parent / "AUTO-MAS"))
).resolve()
if not (host_root / "app/plugin/base/script.py").is_file():
    raise RuntimeError(
        "请通过 AUTO_MAS_HOST_SOURCE 指定已完成插件框架迁移的宿主源码目录"
    )
for path in (host_root, host_root / "plugins/auto_mas_core/src", plugin_root / "src"):
    sys.path.insert(0, str(path))

from tests.conftest import isolated_app_paths as isolated_app_paths  # noqa: E402
from tests.conftest import isolated_config_roots as isolated_config_roots  # noqa: E402

# 宿主测试入口也会配置路径，导入夹具后恢复本仓库源码的优先级。
sys.path.insert(0, str(plugin_root / "src"))
