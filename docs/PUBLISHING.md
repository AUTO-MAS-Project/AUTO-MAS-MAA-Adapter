# 发布 auto-mas-maa-adapter

本仓库发布名为 `auto-mas-maa-adapter`，Python 导入名和插件 ID 均为 `maa_adapter`。
当前版本为 `0.1.7`，面向已完成游戏管理插件迁移的 AUTO-MAS 宿主，Python 为 3.12。
旧 `automas_script_maa` / `script_maa` 来源适配保留在 Git 历史，不与本包同时构建。

## 首次发布准备

1. 准备已完成游戏管理插件迁移的宿主，确认内置 core 满足 `>=5.9.0b1,<6`。
   市场安装器会向依赖解析器提供当前宿主 core 的本地元数据，并复用宿主 SDK 源码；
   **通过市场安装不要求先将 core SDK 发布到 PyPI**，也不要删除包的 SDK 依赖。
   独立使用 pip 安装时才需要额外提供 SDK wheel 或已发布的兼容 SDK。
   尚未包含本轮插件框架的公开宿主，不能用于验证这个包。
2. 使用个人 PyPI 账号登录并启用双重验证，在账户 **Publishing** 页面新增 pending publisher：
   - PyPI project name：`auto-mas-maa-adapter`
   - Owner：`AUTO-MAS-Project`
   - Repository name：`AUTO-MAS-MAA-Adapter`
   - Workflow name：`publish.yml`（文件名，不是工作流显示名称）
   - Environment name：`pypi`

   这里的 Owner 是 GitHub 仓库所有者；即使使用个人 PyPI 账号，仍填写 `AUTO-MAS-Project`。
   PyPI 个人账号与 GitHub Owner 不要求同名，组织获批后可再移交 PyPI 项目。
3. 在 GitHub 仓库 Settings → Environments 创建 `pypi` 环境，允许预期的发布标签。
   可以设置维护者审核；工作流只给发布任务授予 `id-token: write`。
4. 确认 Actions 已启用，并将校验通过的迁移代码纳入用于发布的分支。
   正常分支推送只构建校验，只有 `v*` 标签会上传 PyPI。

Trusted Publishing 使用 GitHub OIDC，不需要在仓库配置 `PYPI_TOKEN`。
Pending publisher 不会预留包名，只有首次发布成功才创建 PyPI 项目。

## 构建和发布

本地构建不需要安装宿主运行依赖：

```powershell
uv build
uvx --from twine twine check --strict dist/*
```

在仓库根目录的 `CHANGELOG.md` 中按 `## [版本] - 日期` 记录本版用户可见的改动。插件市场通过 PyPI 元数据中的 `Changelog` 链接收录最近五个发行版本的说明。

发布时，`pyproject.toml` 中的版本与标签必须一致。
`v0.1.0` 已指向第一次失败的发布提交，不能靠重新运行该标签发布修正后的代码。
修复当前元数据后，下一次发布应先通过插件发布流程推进版本，再创建匹配的新标签；不移动旧标签。
当前发布版本为 `0.1.7`，确认所选提交包含本轮代码及元数据后执行：

```powershell
git tag v0.1.7
git push origin v0.1.7
```

进入 Actions 的「构建并发布 PyPI 包」，确认构建、元数据校验和发布三个步骤成功。
不要给旧代码打这个标签，也不要为修复已上传文件重用同一版本号。
后续版本按本仓库的发布节奏修改版本，再创建对应的新标签。

工作流只上传 wheel 与源码包，不会运行真实 MAA、模拟器或账号任务。
宿主插件框架已合入 `dev`；发布 CI 只验证可独立执行的分发包构建，运行契约在匹配宿主源码环境验证。

## 通过插件市场安装

1. 准备含本轮迁移代码的独立测试宿主，使用新的测试配置环境，仅保留 core。
2. 该环境不能同时通过 `plugins/maa_adapter` 自动发现本地源码。
   本地源码可能覆盖已安装发行版，不能以这种状态证明 PyPI 安装成功。
3. 插件市场选择能查询到新包的 PyPI 源并刷新，找到「MAA 专项」。
   Keywords 包含市场门禁 `auto-mas-plugin` 与唯一 ID `auto-mas-id:maa_adapter`。
   README 开头的 `auto-mas:i18n` HTML 注释统一声明 `display_name_i18n`、`description_i18n` 和 `tags_i18n`；
   PyPI JSON、源码发现和已安装包都读取这份正文，`project.urls` 只声明真实 HTTP/HTTPS 链接。
4. 安装并启用，核对包名 `auto-mas-maa-adapter`、版本、安装来源及插件状态，再新建 MAA 托管。
   若镜像未同步，可暂时选择官方 PyPI，不能把镜像尚未同步误判为发布失败。
5. 核对关卡选项、配置/查看会话、插件禁用与重新启用；真实自动代理另按账号和模拟器验证流程执行。

wheel 包含 Python 代码、预设 JSON、语言资源、类型标记和许可证。
`frontend/` 包含在源码分发包，当前仍由宿主前端构建收集，wheel 不动态替换桌面渲染页面。
因此测试宿主必须已随附匹配的 MAA 编辑界面。

## 本地运行测试

测试复用同版本宿主的真实配置隔离夹具，不附带另一份宿主框架。
默认寻找相邻的 `../AUTO-MAS`，也可显式指定：

```powershell
$env:AUTO_MAS_HOST_SOURCE = "D:/Dev/AUTO-MAS"
& "$env:AUTO_MAS_HOST_SOURCE/.venv/Scripts/python.exe" -m pytest tests -q
```

测试优先导入本仓库 `src/maa_adapter`，进程、网络和设备由测试边界替代。
SDK 开发、调试和静态检查跟随同版本主程序及 SDK 源码，不单独交付宿主类型桩。

## 官方参考

- [创建 PyPI Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [通过 Trusted Publishing 发布](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
- [Python 包构建与发布](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
