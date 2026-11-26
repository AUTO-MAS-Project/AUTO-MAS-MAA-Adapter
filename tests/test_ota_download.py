"""以官方清单真实包名和地址覆盖 MAA 本体预下载及启动前下载。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from maa_adapter.updates import fluxdown


@pytest.mark.asyncio
@pytest.mark.parametrize("ota_missing", [False, True])
async def test_official_ota_from_maarelease_used_for_prefetch_and_download(
    monkeypatch, tmp_path, ota_missing
):
    filename = "MAAComponent-OTA-v6.23.1_v6.23.2-win-x64.zip"
    url = f"https://github.com/MaaAssistantArknights/MaaRelease/releases/download/v6.23.2/{filename}"
    full_name = "MAA-v6.23.2-win-x64.zip"
    full_url = f"https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases/download/v6.23.2/{full_name}"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        fluxdown, "read_installed_release", lambda _: ("v6.23.1+4047243", "x64")
    )
    monkeypatch.setattr(
        fluxdown,
        "request_maa_release",
        AsyncMock(
            return_value={
                "version": "v6.23.2",
                "details": {
                    "assets": [{"name": filename, "browser_download_url": url}]
                },
            }
        ),
    )
    monkeypatch.setattr(fluxdown, "use_maa_github_update", lambda *args, **kwargs: True)
    config = SimpleNamespace(
        Update=SimpleNamespace(PackageMode="incremental", Channel="beta")
    )
    root = tmp_path / "maa"
    config_dir = root / "config"
    config_dir.mkdir(parents=True)

    async def transfer(download_url, destination, **kwargs):
        if ota_missing and download_url == url:
            request = httpx.Request("GET", download_url)
            httpx.Response(404, request=request).raise_for_status()
        assert download_url == (full_url if ota_missing else url)
        destination.write_bytes(b"official package")

    monkeypatch.setattr(fluxdown, "download_file", transfer)

    [request] = await fluxdown.check_update_download(root, config)
    assert request.url == url
    prepared = await fluxdown.prepare_maa_fluxdown_update(
        root, config=config, config_dir=config_dir, download_only=True
    )
    try:
        assert isinstance(prepared, fluxdown.PreparedUpdate)
        assert prepared.package.name == (full_name if ota_missing else filename)
    finally:
        if isinstance(prepared, fluxdown.PreparedUpdate):
            fluxdown.discard_prepared_update(prepared)
