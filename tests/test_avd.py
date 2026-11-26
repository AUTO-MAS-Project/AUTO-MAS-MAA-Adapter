"""ModAVD 实例上 MAA 的连接设置：原生 ModAVD 连接与假 MuMu 通道的选择、截图回落判断。"""

from pathlib import Path

from maa_adapter.native.avd import (
    MAA_CONNECT_CONFIG,
    MAA_MODAVD_CONNECT_CONFIG,
    build_maa_connect_settings,
    detect_screencap_fallback,
    maa_supports_native_modavd,
    screencap_fallback_status,
    shim_root,
    use_native_modavd,
)

# MAA v6.23.2 resource/config.json 的写法：连接配置在 ``connection`` 列表里，文件里还有
# Python json 不认的 ``\.`` 转义（PowerShell / Python 都解析不了，MaaCore 能）。
NATIVE_CONFIG_JSON = r"""{
    "connection": [
        { "configName": "General", "eventId": "a\.b" },
        {
            "configName": "ModAVD",
            "baseConfig": "General"
        }
    ]
}"""
OLD_CONFIG_JSON = """{
    "connection": [
        { "configName": "General" },
        { "configName": "MuMuEmulator12", "baseConfig": "General" }
    ]
}"""


def _maa_root(tmp_path: Path, config_text: str | None) -> Path:
    root = tmp_path / "maa"
    (root / "resource").mkdir(parents=True)
    if config_text is not None:
        (root / "resource" / "config.json").write_text(config_text, encoding="utf-8")
    return root


def _avd_root(tmp_path: Path, *, with_library: bool) -> Path:
    root = tmp_path / "ModAVD"
    root.mkdir()
    if with_library:
        (root / "extras").mkdir()
        (root / "extras" / "modavd_extras.dll").write_bytes(b"MZ")
    return root


def test_native_modavd_detected_from_config_text(tmp_path: Path) -> None:
    assert maa_supports_native_modavd(_maa_root(tmp_path, NATIVE_CONFIG_JSON))


def test_old_maa_without_modavd_config(tmp_path: Path) -> None:
    assert not maa_supports_native_modavd(_maa_root(tmp_path, OLD_CONFIG_JSON))


def test_missing_config_counts_as_unsupported(tmp_path: Path) -> None:
    assert not maa_supports_native_modavd(_maa_root(tmp_path, None))


def test_native_requires_library_in_modavd_root(tmp_path: Path) -> None:
    maa = _maa_root(tmp_path, NATIVE_CONFIG_JSON)
    assert not use_native_modavd(maa, _avd_root(tmp_path, with_library=False))


def test_native_used_when_maa_and_library_ready(tmp_path: Path) -> None:
    maa = _maa_root(tmp_path, NATIVE_CONFIG_JSON)
    assert use_native_modavd(maa, _avd_root(tmp_path, with_library=True))


def test_old_maa_keeps_shim_even_with_library(tmp_path: Path) -> None:
    maa = _maa_root(tmp_path, OLD_CONFIG_JSON)
    assert not use_native_modavd(maa, _avd_root(tmp_path, with_library=True))


def test_native_connect_settings(tmp_path: Path) -> None:
    root = tmp_path / "ModAVD"
    current = {
        "Address": "127.0.0.1:20001",
        "AdbPath": r"C:\adb\adb.exe",
        "Config": "General",
        "AutoDetect": True,
        "TouchMode": "MiniTouch",
        "Extras": {
            MAA_CONNECT_CONFIG: {"IsEnabled": False, "EmulatorPath": r"D:\MuMu"},
            MAA_MODAVD_CONNECT_CONFIG: {"RootPath": "", "Other": 1},
        },
    }
    settings = build_maa_connect_settings(
        root, 20000, current, root / "adb.exe", native=True
    )

    assert settings["Config"] == "ModAVD"
    assert settings["TouchMode"] == "ModAvdExtras"
    assert settings["AutoDetect"] is False
    assert settings["AlwaysAutoDetect"] is False
    assert settings["Extras"]["ModAVD"] == {"RootPath": str(root), "Other": 1}
    # MuMu 那份不动：原生连接用不上它，用户真有 MuMu 时也不该被改
    assert settings["Extras"][MAA_CONNECT_CONFIG] == {
        "IsEnabled": False,
        "EmulatorPath": r"D:\MuMu",
    }
    # 已经配过的 adb 和地址不动
    assert settings["AdbPath"] == r"C:\adb\adb.exe"
    assert settings["Address"] == "127.0.0.1:20001"
    # 不改入参
    assert current["Config"] == "General"
    assert current["Extras"][MAA_MODAVD_CONNECT_CONFIG]["RootPath"] == ""


def test_shim_connect_settings_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "ModAVD"
    settings = build_maa_connect_settings(root, 20030, {}, root / "adb.exe")

    assert settings["Config"] == MAA_CONNECT_CONFIG
    assert settings["TouchMode"] == "MaaTouch"
    assert settings["AdbPath"] == str(root / "adb.exe")
    assert settings["Extras"][MAA_CONNECT_CONFIG] == {
        "IsEnabled": True,
        "EmulatorPath": str(shim_root(root)),
        "EnableBridgeConnection": True,
        "InstanceIndex": 20030,
    }
    assert MAA_MODAVD_CONNECT_CONFIG not in settings["Extras"]


# MAA 界面日志的写法（Asst.Connection.FastestWayToScreencap：``最快截图耗时: {0}ms ({1})``）
NATIVE_OK_LOG = (
    "[12:11:50] 正在连接模拟器\n[12:11:50] 最快截图耗时: 1ms (ModAvdExtras)\n"
)
SHIM_OK_LOG = "[12:11:50] 最快截图耗时: 3ms (MumuExtras)\n"
FALLBACK_LOG = "[12:11:50] 最快截图耗时: 168ms (RawByNc)\n"


def test_native_screencap_ok() -> None:
    assert detect_screencap_fallback(NATIVE_OK_LOG, native=True) is None
    assert screencap_fallback_status(NATIVE_OK_LOG, native=True) is None


def test_native_screencap_fallback_to_adb() -> None:
    assert detect_screencap_fallback(FALLBACK_LOG, native=True) == "RawByNc"
    status = screencap_fallback_status(FALLBACK_LOG, native=True)
    assert status is not None and "RawByNc" in status


def test_native_expects_modavd_extras_not_mumu() -> None:
    assert detect_screencap_fallback(SHIM_OK_LOG, native=True) == "MumuExtras"


def test_native_not_enabled_message() -> None:
    log = "ModAVD 截图增强未生效，请在 ｢设置 - 连接设置 - 连接配置｣ 检查 ModAVD 根目录和连接地址\n"
    assert detect_screencap_fallback(log, native=True) == "ModAVD 截图增强未生效"


def test_native_not_enabled_message_other_language() -> None:
    log = "ModAVD screenshot enhancement is not working. Check the ModAVD root\n"
    assert detect_screencap_fallback(log, native=True) == "ModAVD 截图增强未生效"


def test_shim_detection_unchanged() -> None:
    assert detect_screencap_fallback(SHIM_OK_LOG) is None
    assert detect_screencap_fallback(NATIVE_OK_LOG) == "ModAvdExtras"
    assert detect_screencap_fallback("MuMu 截图增强未生效\n") == "MuMu 截图增强未生效"


def test_screencap_not_measured_yet() -> None:
    assert detect_screencap_fallback("[12:11:49] 正在连接模拟器\n", native=True) is None
