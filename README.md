<!-- auto-mas:i18n
{
  "display_name_i18n": {
    "zh_CN": "MAA 专项",
    "en": "MAA Adapter"
  },
  "description_i18n": {
    "zh_CN": "MAA 专项适配插件",
    "en": "MAA specialized script adapter"
  },
  "tags_i18n": {
    "zh_CN": [
      "专项适配",
      "明日方舟"
    ],
    "en": [
      "Script adapter",
      "Arknights"
    ]
  }
}
-->

# AUTO-MAS MAA Adapter

以主程序插件迁移合并提交 `a617ddd11bb0e2e3e55ac6980a3cf23d47fdff78` 为核对基准，全量承接 MAA 专项。旧 `app/task/MAA`、宿主内置 MAA 配置类及内置注册已移除，不提供旧导入路径转发。

## 安装与发布

发行包名为 **`auto-mas-maa-adapter`**，Python 导入名和插件 ID 为 **`maa_adapter`**。
依赖 **`auto-mas-core>=5,<6`** 与 Python 3.12；需要已合入插件框架的宿主。
插件从市场安装后，不需要单独安装 MAA 适配源码。

PyPI Trusted Publishing、构建、打标签发布及市场安装验证见 [发布说明](docs/PUBLISHING.md)。
当前 wheel 只替换后端插件，MAA 前端组件仍随匹配的桌面宿主构建交付。

## 0.1.3 更新

- 修复配置保存及每日代理次数处理，避免重试读取上一轮残留日志。
- 本体与资源预下载复用同一版本的下载缓存，遵守每日取包限制和失败等待时间。
- 正常跳过的账号不再计为失败，避免误触发“仅失败时”通知。
- 同步主程序近期的养成选关、资源休息日和理智估算修正。

## 使用

源码开发时，在宿主插件中心手动启用本插件。市场安装与旧配置升级沿用宿主的安装、启用流程。
在托管列表正常新建 MAA，使用原有的托管、账号、养成和计划界面。旧托管、账号与计划的 UID 和配置保持不变。
不再提供“创建测试托管”的临时设置入口。

## 归属与运行

- `src/maa_adapter` 持有完整模型、专项 API、配置恢复、作业平台、更新、养成、日志观察与执行逻辑。
- 主程序的 `frontend/src/views/maa` 暂时持有编辑页、计划表、养成组件、专项组合函数、元数据及图标，页面入口随插件能力开放。动态页面上线后再迁回插件。
- `i18n` 持有 MAA 专属界面词条，公共词条仍使用 core。HTTP 路径和路由名保留原有公开契约，插件停用后专项 HTTP 路径随调用门排空后卸载。
- L2 持有托管锁、预下载会话与本次进程归属，停止前先确认安装停写和配置保存；L3 使用 `UserExpander`，L4 使用 `ModeWorker`，用户锁内完成恢复。
- 自动代理继续复用宿主的模拟器、通知、历史及社区公共服务；没有创建游戏适配插件。
- 统一下载中心提供预下载文件。安装编排整体移入 L2 仍按已确认的后续任务推进；当前复用宿主公共安装执行及恢复入口，不保留旧 MAA manager。

## 源码结构

```text
src/maa_adapter/
  plugin.py          插件声明、启用预热与公共服务接线
  config/            托管、用户、计划、插件缓存及配置迁移
  tasks/             L3/L4 编排、配置入口、查看入口和共用 GUI 会话
  native/            MAA 配置下发、预设、快照、恢复与基建设置
  updates/           本体、资源、游戏更新及预下载需求
  cultivate/         养成、库存、作业来源和编辑业务
  stages/            关卡解释、缓存访问及活动时段判断
  logs/              MAA 输出解析、统计和截图
  api/               按业务拆分的 HTTP 端点及端点专用模型
  notifications.py   MAA 专属报告内容，投递仍直接使用宿主 Notify
```

配置和查看分别由 `tasks/config_session.py`、`tasks/view_session.py` 提供入口，
两者共享 `tasks/session.py` 的 GUI 运行与保存确认能力，查看不继承配置入口。
任务执行顺序仍集中在 `tasks/manager.py` 与 `tasks/auto_proxy.py`，
配置转换、养成任务构造和日志解析通过明确调用接入，不引入任务 mixin。

## 关卡数据归属

关卡号、资源关卡和材料名称全部由插件持有。启用时通过插件背景任务组首次获取
MAA 官方资源，以 `MaaPluginConfig.stage_cache` 保存正文、ETag 和检查时间，
由宿主配置框架统一持久化到 `config/plugins/maa_adapter.yaml`。
刷新失败保留已有缓存，停用会结束刷新任务，卸载按插件配置删除语义清理缓存。

插件注册 `/api/plugin/maa_adapter/stages/options` 和 `/stages/overview`，
账号及计划表的主备关卡字段均以 `select(endpoint=...)` 声明选项接口。
当前主程序前端直接使用生成的插件 API 客户端，保留现有编辑器和自定义关卡；
没有接入动态 UI。宿主不再保存关卡缓存，也不保留旧关卡号接口。

## 验证入口

独立仓库复用相邻同版本宿主的隔离夹具：

```powershell
$env:AUTO_MAS_HOST_SOURCE = "D:/Dev/AUTO-MAS"
& "$env:AUTO_MAS_HOST_SOURCE/.venv/Scripts/python.exe" -m pytest tests -q
```

宿主侧先运行 `uv run --no-sync python scripts/prepare_test_plugins.py` 准备已发布的测试插件，
再运行 `uv run --no-sync python -m pytest tests/task -k maa -q`。

浏览器通过 `frontend/e2e/run.mjs` 运行 `@plugins|@maa-plan-display|@maa-update`。
进程、网络及设备边界采用隔离替身的检查不代表真实 MAA、游戏或模拟器验收。

## 本地开发

将本仓库克隆到宿主的 `plugins/maa_adapter`，然后启动宿主并在插件中心启用。
该目录由宿主 Git 忽略，开发完成后在此独立仓库内提交、推送和发布。
主程序仓库只跟踪 `plugins/auto_mas_core`，SDK 随主程序更新。

Runtime 用户将源码放在安装根目录的 `plugins/maa_adapter`。后端代码位于 `repo`，
Runtime 更新和切换源码时保留根目录的插件目录，宿主从该目录发现用户插件。
本地源码优先于同 ID 的发行包。验证市场发行包时，先停止后端，将本地源码移出插件扫描目录后再启动。
