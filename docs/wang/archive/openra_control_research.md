# OpenRA 游戏控制调研

## 结论摘要

结论先说：

1. **当前 `GameAPI` / Copilot TCP API 没有“重启一局 / 重置对局”接口。**
2. **仓库里已经有“进程级重启”能力**：旧 `web-console` 的 service API 可以 `stop -> start` 重启 OpenRA 进程。
3. **OpenRA 本体内部有“Restart mission”能力**，但它会**重新播随机种子**，不是严格意义上的“精确复位”。
4. **最适合自动化测试的复位方式是 `Game.LoadSave=<baseline>`**：重启进程时直接载入一个基线存档，状态最可控。
5. **OpenRA 自带较强的 developer/debug/cheat 能力**，包括加钱、瞬建、全科技、无限电、清/重置迷雾等，但这些是**游戏内 developer command / debug panel**，不是当前 Copilot `GameAPI` 暴露出来的远程接口。

## 1. 游戏重启 / 重置能力

### 1.1 当前远程 API 没有 restart/reset

当前 Copilot 命令注册表只暴露了单位控制、生产管理和查询，没有任何 `restart_game` / `reset_match` / `load_save` 之类的 handler：

- [ServerCommands.cs](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/OpenRA.Mods.Common/ServerCommands.cs#L1547)
- [ServerCommands.cs](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/OpenRA.Mods.Common/ServerCommands.cs#L1568)

可见的命令面主要是：

- `move_actor`
- `camera_move`
- `select_unit`
- `form_group`
- `attack`
- `deploy`
- `occupy`
- `repair`
- `stop`
- `set_rally_point`
- `place_building`
- `manage_production`

以及查询：

- `query_actor`
- `query_wait_info`
- `query_path`
- `query_can_produce`
- `query_production_queue`
- `query_control_points`
- `match_info_query`
- `map_query`
- `fog_query`
- `unit_attribute_query`
- `player_baseinfo_query`
- `screen_info_query`
- `query_players`

所以如果目标是“测试时快速复位一局”，**现有 GameAPI 不够，需要额外接一层新命令**。

### 1.2 OpenRA 本体内部有 Restart 按钮

OpenRA 单机 regular world 的 ingame menu 里有 restart button：

- [IngameMenuLogic.cs](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/OpenRA.Mods.Common/Widgets/Logic/Ingame/IngameMenuLogic.cs#L338)

它最终调用：

- [Game.cs](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/OpenRA.Game/Game.cs#L271)

但这里有一个很重要的细节：

- `Game.RestartGame()` 会重设 `lobbyInfo.GlobalSettings.RandomSeed`

也就是：

- 它可以“重新开同一张图 / 同一任务”
- 但**不是 deterministic reset**
- 如果后续测试依赖完全一致的初始状态，这条路不够稳

### 1.3 OpenRA 支持启动时自动载入存档

`OpenCodeAlert/start.sh` 默认就支持传 `Game.LoadSave=...`：

- [start.sh](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/start.sh#L5)
- [start.sh](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/start.sh#L23)
- [start.sh](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/start.sh#L32)

游戏启动时会检查这个设置并尝试直接载入 `.orasav`：

- [Game.cs](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/OpenRA.Game/Game.cs#L550)
- [Game.cs](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/OpenRA.Game/Game.cs#L1048)

这意味着现在其实已经有一条**最适合自动化的复位路线**：

- 准备一个基线存档 `baseline.orasav`
- 重启 OpenRA 进程
- 启动时传 `Game.LoadSave=baseline`

相比 `RestartGame()`，这条路更接近“精确回到同一状态”。

## 2. OpenCodeAlert 子模块里的启动 / 控制脚本

`OpenCodeAlert/` 里和启动控制直接相关的脚本主要是：

- [start.sh](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/start.sh)
- [launch-game.sh](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/launch-game.sh)
- [launch-game-withoutpython.sh](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/launch-game-withoutpython.sh)
- [launch-dedicated.sh](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/launch-dedicated.sh)
- [utility.sh](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/utility.sh)

### 2.1 `start.sh`

这是当前最直接的游戏启动包装器。它会把这些参数传给底层 launcher：

- `Game.Mod`
- `Game.LoadSave`
- `Game.CopilotPort`
- `Game.CopilotDebug`
- `Game.IsAgentMode`

也就是说，**它已经是“测试启动入口”**，只是目前没有额外包装成“复位到某个基线”的专用脚本。

### 2.2 `launch-game.sh`

这是实际启动 OpenRA 客户端的脚本：

- [launch-game.sh](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/launch-game.sh#L38)

它最终执行：

- `dotnet .../OpenRA.dll ... Game.Mod=... "$@"`

没有内建“restart current match”的 shell 逻辑，它只是**启动器**。

### 2.3 `launch-dedicated.sh`

这是 dedicated server 启动脚本：

- [launch-dedicated.sh](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/launch-dedicated.sh#L34)

它支持设置：

- `Mod`
- `Map`
- `ListenPort`
- `EnableSingleplayer`
- `RecordReplays`

并且放在一个 `while true` 里持续拉起 server。它更适合 server/CI 场景，不是当前本地 GUI 测试主链。

### 2.4 `utility.sh`

只是启动 `OpenRA.Utility.dll`：

- [utility.sh](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/utility.sh#L10)

当前仓库里我没有看到基于它实现“快速重置当前对局”的现成脚本。

## 3. 现有启动方式

### 3.1 `web-console/start-vnc.sh` 不负责启动游戏

- [start-vnc.sh](/Users/kamico/work/theseed/THE-Seed-OpenRA/web-console/start-vnc.sh)

这个脚本只负责：

- 启动 `Xvfb`
- 启动 `x11vnc`
- 启动 `websockify`
- 启动静态 `http.server`

它**不启动 OpenRA 本体**，所以它不是“游戏重置脚本”。

### 3.2 旧 web-console 的 service API 有进程级 start/stop/restart

真正负责启动/停止游戏的是：

- [service.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/web-console/api/service.py)

其中：

- [service.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/web-console/api/service.py#L140) `start_game()` 用 `nohup ./start.sh`
- [service.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/web-console/api/service.py#L157) `stop_game()` 用 `pkill -f OpenRA.dll`
- [service.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/web-console/api/service.py#L177) `restart_game()` 做 `stop -> sleep -> start`

所以**进程级重启能力已经存在**，只是它现在做的是“重启 OpenRA 进程”，不是“在进程内重开当前对局”。

### 3.3 当前前端里的 `reset_all` 不是游戏复位

旧 console 前端有个“新对局”按钮：

- [index.html](/Users/kamico/work/theseed/THE-Seed-OpenRA/web-console/index.html#L35)
- [app.js](/Users/kamico/work/theseed/THE-Seed-OpenRA/web-console/js/app.js#L1460)

但它发的是：

- `type: 'enemy_control'`
- `payload: { action: 'reset_all' }`

从现有代码看，这个更像：

- 清前端聊天/日志
- 清 AI 上下文
- 重启敌方 AI

**不是 OpenRA 游戏状态 reset。**

## 4. GameAPI 现有控制能力

`GameAPI` 的公开方法里，和“控制”最相关的能力包括：

- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L203) 相机移动
- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L265) 生产单位
- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L373) 单位移动
- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L674) 部署单位
- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L731) 攻击目标
- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L786) 修理单位
- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L805) 停止单位
- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L870) 查询生产队列
- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L927) 放置建筑
- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L951) 生产队列 `pause/cancel/resume`
- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L1165) 地图查询
- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L1193) 玩家基地资源/电力查询
- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L1218) 屏幕信息查询
- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L1272) 控制点查询
- [game_api.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/openra_api/game_api.py#L1296) 比赛信息查询

### 4.1 `control_point_query`

底层 server 侧会返回：

- 控制点名称
- `x / y`
- 是否有 buff
- buff 列表（单位类型 / buff 类型 / buff 名）

见：

- [ServerCommands.cs](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/OpenRA.Mods.Common/ServerCommands.cs#L1476)

### 4.2 `match_info_query`

底层 server 侧会返回：

- `selfScore`
- `enemyScore`
- `remainingTime`

见：

- [ServerCommands.cs](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/OpenRA.Mods.Common/ServerCommands.cs#L1505)

### 4.3 关键缺口

这些能力虽然已经覆盖了“玩一局”的大部分单位/生产/查询控制，但**完全没有覆盖“重启 / 重置 / 载入基线局面”**。

也就是说：

- `GameAPI` 适合**对局内控制**
- 不适合**对局生命周期控制**

## 5. 游戏作弊 / 调试命令

OpenRA 本体里这部分能力其实很强。

### 5.1 游戏内 Debug 面板

debug panel UI 已内置这些操作：

- `Instant Build Speed`
- `Build Everything`
- `Build Anywhere`
- `Unlimited Power`
- `Instant Charge Time`
- `Give $20,000`
- `Grow Resources`
- `Clear Shroud`
- `Reset Shroud`

见：

- [ingame-debug.yaml](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/mods/common/chrome/ingame-debug.yaml#L1)
- [DebugMenuLogic.cs](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/OpenRA.Mods.Common/Widgets/Logic/Ingame/DebugMenuLogic.cs#L22)

这些按钮底层会发出相应的 `Dev*` order。

### 5.2 聊天框 developer commands

聊天命令注册表包括：

- `visibility`
- `give-cash`
- `give-cash-all`
- `instant-build`
- `build-anywhere`
- `unlimited-power`
- `enable-tech`
- `fast-charge`
- `all`
- `crash`
- `levelup`
- `player-experience`
- `power-outage`
- `kill`
- `dispose`
- `agent-mode`

见：

- [DevCommands.cs](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/OpenRA.Mods.Common/Commands/DevCommands.cs#L83)

这些命令底层对应的效果包括：

- 加钱 / 全员加钱
- 瞬建
- 全科技
- 无限电
- 全图视野 / 重置迷雾
- 杀死选中单位
- 删除选中单位
- 切换 `agent-mode`

见：

- [DeveloperMode.cs](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/OpenRA.Mods.Common/Traits/Player/DeveloperMode.cs#L133)

### 5.3 限制

这些 debug / cheat 能力目前是：

- **游戏内 UI / chat command**
- 受 `DeveloperMode` 开关约束

`DeveloperMode` 默认只有在单人局或 lobby cheats 打开时启用：

- [DeveloperMode.cs](/Users/kamico/work/theseed/THE-Seed-OpenRA/OpenCodeAlert/OpenRA.Mods.Common/Traits/Player/DeveloperMode.cs#L124)

所以它们**不等于现有远程 API 已可直接调用**。

## 6. 对后续自动化测试的建议

### 推荐方案 A：进程级重启 + `Game.LoadSave=<baseline>`

这是我认为最稳的方案。

做法：

1. 准备一个基线 `.orasav`
2. 停掉 OpenRA 进程
3. 重新执行：
   - `DISPLAY=:99 ./OpenCodeAlert/start.sh Game.Mod=copilot Game.LoadSave=<baseline> Game.CopilotPort=7445 ...`

优点：

- 状态最可控
- 比 `RestartGame()` 更接近 deterministic reset
- 不需要先扩展 Copilot TCP API

缺点：

- 需要重启进程，速度不如进程内 reset

### 推荐方案 B：新增一个 Copilot reset 命令

如果后续一定要做“无进程重启”的快速复位，建议在 `CopilotCommandServer` 新增 lifecycle handler，例如：

- `restart_game`
- `load_save`
- `restart_from_baseline`

它们内部可以调用：

- `Game.RestartGame()`，或者
- `CreateAndStartLocalServer(...)`，或者
- `TryLoadGameSave(...)` 对应的逻辑

但要注意：

- 直接走 `RestartGame()` 不是 deterministic
- 真想做稳定测试，最好还是显式 `load_save`

### 推荐方案 C：不重开局，只用 developer cheats 拉状态

比如：

- 给钱
- 瞬建
- 清迷雾
- 切全科技

这对一些能力测试很有用，但它更适合：

- 构造局内条件
- 加速某类测试

不适合替代完整 reset，因为：

- 很难回到完全一致的状态
- 地图、随机数、单位残骸、战斗历史等都还在

## 最终建议

如果目标真的是“**让后续测试可以自动化重置游戏状态**”，我的建议排序是：

1. **短期可直接落地**：复用现有 `stop/start`，增加 `Game.LoadSave=<baseline>` 启动参数
2. **中期体验更好**：在 Copilot TCP API 新增 `load_save` / `restart_from_baseline` 命令
3. **辅助提速**：把 developer cheats 作为测试夹具，不把它们当 reset 主路径

一句话总结：

**现在最现实可用的是“进程级重启”，现在最稳的自动化 reset 是“进程级重启 + baseline save”。**
