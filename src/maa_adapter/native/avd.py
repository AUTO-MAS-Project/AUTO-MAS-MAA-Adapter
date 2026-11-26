#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""MAA 在 ModAVD 上的截图通道：冒充 MuMu 的截图接口。

MaaCore（v6.18.0 实测）对 ModAVD 没有截图增强，走 adb 单次约 250 ms。它的 MuMu 通道
只是在配置的 MuMu 目录下 ``LoadLibrary`` ``shell\\sdk\\external_renderer_ipc.dll`` 再按名字
取四个函数，所以放一个同名 DLL（``res/avdshim``：ModAVDExtras 发布的兼容外壳，读模拟器的
截图共享内存 ``SHM_videmulator<控制台端口>``，来源和版本见同目录的 ``README.md``）就能让
MaaCore 选中 MumuExtras，稳态 2–3 ms。

MAA 侧的连接配置按 MAA 6.18.0 源码写（``MaaWpfGui/Configuration/Single/Settings/
ConnectSettings.cs``、``ConnectionExtra/Mumu12Extra.cs``、``Models/EmulatorConnectionExtra/
MuMu12Extra.cs``、MaaCore ``Controller/AdbController.cpp``）：

- ``Config = MuMuEmulator12``：连接预设设为 MuMu，MaaCore 才会测 MumuExtras；
- ``Extras.MuMuEmulator12 = {IsEnabled, EmulatorPath, EnableBridgeConnection, InstanceIndex}``：
  **``EnableBridgeConnection`` 必须开**——GUI 只在它开着时把 ``index`` 传给 MaaCore，
  否则 MaaCore 按地址端口反推 MuMu 实例号（``127.0.0.1:20031`` 会被算成 241），
  假 DLL 就去读一块不存在的共享内存；``InstanceIndex`` 填控制台端口（假 DLL 认 ≥ 5554 的
  值为端口）；
- ``TouchMode = MaaTouch``：官方镜像上 minitouch 打不开输入设备（预研 §6.9），而 MuMu 预设
  的默认触控 ``MumuExtras`` 要真 MuMu 的输入接口，假 DLL 不提供；
- ``AutoDetect = false``：不让 MAA 自己去认模拟器改掉上面这些。

这些键和 MAS 注入的其它运行参数一样，由原生配置快照在任务结束后还原。

MAA v6.19.0 复核过：上面的新键名与取值不变；MaaCore 先找 ``nx_device\\15.0``、``nx_device\\12.0``
下的 DLL，最后才是 ``shell\\sdk``，假目录只放最后这一处也能加载；触控多了 ``MumuExtras`` 一档，
``TouchMode = MaaTouch`` 时 GUI 传给 MaaCore 的 ``touch`` 为假，仍走 maatouch。

**原生 ModAVD 连接（MAA v6.22.1-beta.1 起，正式版 v6.23.0 起）**：MAA 自己加了连接配置
``ModAVD`` 和截图方式 ``ModAvdExtras``（MaaAssistantArknights#19178），由 MaaCore 载入
``<ModAVD 根目录>\\extras\\modavd_extras.dll``（ModAVD 0.39.0 起整包自带）。按 MAA v6.23.2 源码
（``ConnectSettings.cs`` 的 ``ExtraConfigs.ModAvd`` 序列化名 ``ModAVD``、``ModAvdExtra.cs``、
``AsstProxy.cs``）写：

- ``Config = ModAVD``；
- ``Extras.ModAVD = {RootPath}``：只要根目录，实例由连接地址推出，不要实例号；
- ``TouchMode = ModAvdExtras``（「ModAVD 触控」，MAA 标为实验功能）：由同一个库经模拟器控制台发
  触控，客体里不用跑 maatouch；滑动的斜率、末端补滑、暂停下干员照 MaaTouch 的参数做
  （``ModAvdController.cpp``），库不支持触控时 MaaCore 自己退回 maatouch；
- ``AutoDetect = false``，同上。

MAA 的 ``resource\\config.json`` 连接配置里有 ``ModAVD``、根目录下也有这个库时走原生连接，
否则（旧 MAA，或没带库的旧 ModAVD）照旧走上面的假 MuMu 通道。
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from auto_mas_core.host.core import Config
from auto_mas_core.host.utils import get_logger

logger = get_logger("ModAVD MAA 截图")

SHIM_SOURCE = Config.resource_path / "avdshim" / "external_renderer_ipc.dll"

#: MAA 截图用的假 MuMu 目录（``<根>\mumu-shim\shell\sdk\external_renderer_ipc.dll``）。
MUMU_SHIM_DIR = "mumu-shim"

#: MAA 的触控模式（``TouchMode`` 枚举名，gui.new.json 存的就是名字）。
MAA_TOUCH_MODE = "MaaTouch"
#: 原生 ModAVD 连接下的触控模式。
MAA_MODAVD_TOUCH_MODE = "ModAvdExtras"
MAA_CONNECT_CONFIG = "MuMuEmulator12"

#: MAA 原生的 ModAVD 连接配置名（``ConnectSettings.Config``，也是 ``Extras`` 下的键）。
MAA_MODAVD_CONNECT_CONFIG = "ModAVD"
#: ModAVD 包里给 MaaCore 载入的截图库（相对根目录）。
MODAVD_EXTRAS_LIBRARY = Path("extras") / "modavd_extras.dll"

#: ``resource\config.json`` 里的 ``"configName": "ModAVD"``。这份文件带 ``\.`` 一类 Python
#: json 不认的转义，所以按文本找，不解析。
_NATIVE_MODAVD_CONFIG_PATTERN = re.compile(r'"configName"\s*:\s*"ModAVD"')


def maa_supports_native_modavd(maa_root: str | Path) -> bool:
    """这份 MAA 有没有原生的 ModAVD 连接配置（v6.22.1-beta.1 起）。读不到文件按没有算。"""
    try:
        text = (Path(maa_root) / "resource" / "config.json").read_text(
            encoding="utf-8-sig", errors="replace"
        )
    except OSError:
        return False
    return _NATIVE_MODAVD_CONFIG_PATTERN.search(text) is not None


def modavd_extras_library(root: str | Path) -> Path:
    """ModAVD 根目录下给 MaaCore 用的截图库。"""
    return Path(root) / MODAVD_EXTRAS_LIBRARY


def use_native_modavd(maa_root: str | Path, avd_root: str | Path) -> bool:
    """MAA 支持原生 ModAVD 连接、ModAVD 根目录里也有截图库时为真；否则走假 MuMu 通道。"""
    return (
        maa_supports_native_modavd(maa_root)
        and modavd_extras_library(avd_root).is_file()
    )


def shim_root(root: str | Path) -> Path:
    """假 MuMu 目录，MAA 的 MuMu 路径填它。"""
    return Path(root) / MUMU_SHIM_DIR


def shim_dll(root: str | Path) -> Path:
    """定位指定模拟器兼容层目录中的外部渲染通信 DLL。"""
    return shim_root(root) / "shell" / "sdk" / "external_renderer_ipc.dll"


def _sha256(path: Path) -> str:
    """计算文件 SHA256，供模拟器兼容层资源完整性检查使用。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


#: ``modavd-manifest.json`` 里外壳的路径。ModAVD 0.40.1 起整包自带外壳，就在这里。
PACKAGE_SHIM_PATH = f"{MUMU_SHIM_DIR}/shell/sdk/external_renderer_ipc.dll"


def _package_ships_shim(root: str | Path) -> bool:
    """根目录的 ``modavd-manifest.json`` 列了外壳：这份文件归 ModAVD 的包管。"""
    try:
        manifest = json.loads(
            (Path(root) / "modavd-manifest.json").read_text(encoding="utf-8-sig")
        )
    except (OSError, ValueError):
        return False
    files = manifest.get("files") if isinstance(manifest, dict) else None
    return isinstance(files, dict) and PACKAGE_SHIM_PATH in files


def ensure_mumu_shim(root: str | Path) -> Path:
    """确保 ``<根>\\mumu-shim\\shell\\sdk\\external_renderer_ipc.dll`` 在，MAA 能当 MuMu 载入。

    ModAVD 0.40.1 起整包自带这份外壳（列在 ``modavd-manifest.json`` 里），这时用包里的，
    不覆盖：换成本体的那份会和包的清单对不上，ModAVD 用 Mirror 酱增量更新时就核对失败。
    包里的被删了才补本体这份，下次 ModAVD 更新会换回包里的。

    更早的包不带外壳，照旧放本体发的那一份：随本体更新 DLL 也会变，所以不只看在不在，
    内容不同就覆盖。正在被 MAA 加载时覆盖会失败，那就留着旧的并记警告——旧的也能用，
    下次运行前再换。
    """
    target = shim_dll(root)
    if target.is_file() and _package_ships_shim(root):
        return target
    if not SHIM_SOURCE.is_file():
        raise FileNotFoundError(f"缺少截图组件 {SHIM_SOURCE}")
    if target.is_file() and _sha256(target) == _sha256(SHIM_SOURCE):
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(SHIM_SOURCE, target)
    except OSError as e:
        if target.is_file():
            logger.warning(f"更新 MAA 截图组件失败，继续使用旧文件: {e}")
            return target
        raise
    logger.info(f"已放置 MAA 截图组件: {target}")
    return target


def build_maa_connect_settings(
    root: str | Path,
    console_port: int,
    current: dict[str, Any] | None,
    adb_path: str | Path,
    *,
    native: bool = False,
) -> dict[str, Any]:
    """在 ``gui.new.json`` 当前配置的 ``Gui.ConnectSettings`` 上叠加 ModAVD 需要的项。

    ``current`` 原样保留其余键（``AdbPath``、``AddressHistory`` 等），只改下面这几项；
    返回新字典，不改入参。``adb_path`` 是 modavd 报的这条安装的 adb（``modavd list`` 的 ``adb_exe``）。
    ``native`` 为真时用 MAA 原生的 ``ModAVD`` 连接配置（见 :func:`use_native_modavd`），
    否则用假 MuMu 通道。
    """
    settings = dict(current or {})
    extras = dict(settings.get("Extras") or {})
    if native:
        connect_config = MAA_MODAVD_CONNECT_CONFIG
        modavd = dict(extras.get(MAA_MODAVD_CONNECT_CONFIG) or {})
        modavd["RootPath"] = str(Path(root))
        extras[MAA_MODAVD_CONNECT_CONFIG] = modavd
    else:
        connect_config = MAA_CONNECT_CONFIG
        mumu = dict(extras.get(MAA_CONNECT_CONFIG) or {})
        mumu.update(
            {
                "IsEnabled": True,
                "EmulatorPath": str(shim_root(root)),
                "EnableBridgeConnection": True,
                "InstanceIndex": int(console_port),
            }
        )
        extras[MAA_CONNECT_CONFIG] = mumu
    if not str(settings.get("AdbPath") or "").strip():
        # 用户的 MAA 从没配过 adb（只装了 ModAVD 的新账号）时才补 SDK 自带的 adb；
        # 已经配了的不动——换 adb 可能和雷电 / MuMu 自带的 adb 抢 5037
        settings["AdbPath"] = str(adb_path)
    settings.update(
        {
            "AutoDetect": False,
            "AlwaysAutoDetect": False,
            "Config": connect_config,
            "Extras": extras,
            "TouchMode": MAA_MODAVD_TOUCH_MODE if native else MAA_TOUCH_MODE,
        }
    )
    return settings


def screencap_fallback_status(log: str, *, native: bool = False) -> str | None:
    """ModAVD 实例上 MAA 截图回落到普通 adb 时给运行结果用的说法；没回落返回 ``None``。

    ``native`` 与 :func:`build_maa_connect_settings` 的同名参数一致：决定该选中哪种截图方式。
    """
    method = detect_screencap_fallback(log, native=native)
    if method is None:
        return None
    return (
        f"MAA 在 ModAVD 上没用上截图增强（{method}），截图回落到普通 adb 会很慢，"
        "本次判失败；请检查 MAA 的连接设置是否被改动，或 MAA 版本是否过旧"
    )


#: MAA 界面日志里「最快截图耗时: 5ms (MumuExtras)」那一行（各界面语言的写法），括号里是选中的方式。
#: MAS 每次运行都把 MAA 界面语言设成 zh-cn，其余语言是防用户在 MAA 里改回去时漏判。原文取自
#: MAA v6.18.0 的 MAA.dll 内嵌语言资源（各语言的 WPF 资源字典，格式都是 ``<前缀>: {0}ms ({1})``），
#: v6.19.0 的 MAA.dll 里五种写法都还在；按 zh-cn、zh-tw、en-us、ja-jp、ko-kr 排列。
MAA_FASTEST_SCREENCAP_PREFIXES = (
    "最快截图耗时",
    "最快截圖耗時",
    "Screenshot test tasks",
    "スクリーンショット テストには",
    "스크린샷 캡처 속도",
)
MAA_MUMU_EXTRAS_METHOD = "MumuExtras"
#: MAA 提示「MuMu 截图增强未生效」的各语言开头（同上，取自 v6.18.0 的 MAA.dll）。
MAA_MUMU_NOT_ENABLED_MARKERS = (
    "MuMu 截图增强未生效",
    "MuMu 截圖增強未生效",
    "MuMu screenshot enhancement is not working",
    "MuMu スクリーンショットの強化 が有効になっていません",
    "MuMu 스크린샷 강화 기능이 활성화되지 않았습니다",
)
#: 原生 ModAVD 连接下应选中的截图方式。
MAA_MODAVD_EXTRAS_METHOD = "ModAvdExtras"
#: MAA 提示「ModAVD 截图增强未生效」的各语言开头（取自 MAA v6.23.2 的
#: ``Connection.ModAVD.ExtrasNotEnabledMessage``，顺序同上）。
MAA_MODAVD_NOT_ENABLED_MARKERS = (
    "ModAVD 截图增强未生效",
    "ModAVD 截圖增強未生效",
    "ModAVD screenshot enhancement is not working",
    "ModAVD スクリーンショットの強化が有効になっていません",
    "ModAVD 스크린샷 강화 기능이 활성화되지 않았습니다",
)


def detect_screencap_fallback(log: str, *, native: bool = False) -> str | None:
    """从 MAA 界面日志判断 ModAVD 实例上截图有没有回落到普通 adb。

    回落了返回 MAA 实际选中的方式（给报错用），没回落或还没测完返回 ``None``。
    ModAVD 上普通 adb 截图约 250 ms，用户明确说过「不如不做」，所以一旦回落就要
    让这次运行失败，而不是静默变慢。``native`` 为真时应选中 ``ModAvdExtras``，
    否则应选中 ``MumuExtras``。
    """
    if native:
        markers, expected = MAA_MODAVD_NOT_ENABLED_MARKERS, MAA_MODAVD_EXTRAS_METHOD
        not_enabled = "ModAVD 截图增强未生效"
    else:
        markers, expected = MAA_MUMU_NOT_ENABLED_MARKERS, MAA_MUMU_EXTRAS_METHOD
        not_enabled = "MuMu 截图增强未生效"
    if any(marker in log for marker in markers):
        return not_enabled
    for line in reversed(log.splitlines()):
        if not any(prefix in line for prefix in MAA_FASTEST_SCREENCAP_PREFIXES):
            continue
        head, sep, tail = line.rpartition("(")
        method = tail.rstrip(") \r\n") if sep else ""
        if method and method != expected:
            return method
        return None
    return None
