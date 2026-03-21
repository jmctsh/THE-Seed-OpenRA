# OpenRA 美术资源调研与 HD 替换可行性报告

> **Agent**: space | **日期**: 2026-02-28 | **项目**: THE-Seed-OpenRA

---

## 目录

1. [调研背景与目标](#1-调研背景与目标)
2. [资源存储架构](#2-资源存储架构)
3. [文件格式详解](#3-文件格式详解)
4. [资产完整清单](#4-资产完整清单)
5. [引擎 HD 支持能力](#5-引擎-hd-支持能力)
6. [AI 图片生成定价分析](#6-ai-图片生成定价分析)
7. [费用估算](#7-费用估算)
8. [推荐管线方案](#8-推荐管线方案)
9. [风险与注意事项](#9-风险与注意事项)
10. [结论](#10-结论)
11. [附录](#附录)

---

## 1. 调研背景与目标

### 1.1 背景

THE-Seed-OpenRA 项目使用 OpenRA 引擎运行红色警戒游戏，原版美术资源为 1996 年的低分辨率像素风格（主要精灵仅 24x24 ~ 50x50 像素）。希望通过 AI 图片生成技术批量替换美术资源，制作高清版本。

### 1.2 调研目标

| # | 问题 | 状态 |
|---|------|------|
| 1 | 资源存储格式和组织方式 | ✅ 已完成 |
| 2 | 资产总量和尺寸分布 | ✅ 已完成 |
| 3 | 替换是否必须像素对齐 | ✅ 已完成——不需要 |
| 4 | HD 高清版技术可行性 | ✅ 已完成——完全可行 |
| 5 | AI 生成成本评估 | ✅ 已完成 |
| 6 | 批量管线可行性 | ✅ 已完成 |

---

## 2. 资源存储架构

### 2.1 目录结构

```
mods/{mod_name}/
├── mod.yaml              # 清单文件：声明格式、加载顺序、包路径
├── bits/                 # 精灵文件（.shp, .tem, .sno, .des 等）
├── uibits/               # UI 资源（chrome.png, glyphs.png 等，含 2x/3x）
├── sequences/            # YAML 动画序列定义（帧映射）
│   ├── infantry.yaml
│   ├── vehicles.yaml
│   ├── aircraft.yaml
│   ├── ships.yaml
│   ├── structures.yaml
│   ├── decorations.yaml
│   └── misc.yaml
├── tilesets/             # 地形集定义（YAML）
└── rules/               # 游戏规则（YAML，引用 sequence 名称）
```

### 2.2 资源加载流程

```
mod.yaml [Packages] 声明搜索路径
    ↓
FileSystem 挂载目录 + MIX 归档包
    ↓
SpriteLoader 按 [SpriteFormats] 顺序尝试解析
    ↓
SequenceSet 读取 sequences/*.yaml，映射帧到动画
    ↓
SpriteCache → SheetBuilder 打包到纹理图集
    ↓
GPU 渲染
```

### 2.3 资源覆盖机制

同名文件按 Packages 搜索路径优先级覆盖——后加载的包覆盖先加载的。这意味着 **只需将替换文件放入 mod 的 `bits/` 目录即可覆盖原版 MIX 包内的同名资源**，无需修改原始包。

---

## 3. 文件格式详解

### 3.1 精灵格式

| 格式 | loader 名称 | 用途 | 颜色深度 | 压缩 |
|------|-----------|------|---------|------|
| **SHP (TD/RA1)** | `ShpTD` | 单位、建筑、步兵 | 8-bit 调色板索引 | LCW/XOR |
| **SHP (TS/RA2)** | `ShpTS` | 部分兼容资源 | 8-bit 调色板索引 | RLE-zero |
| **SHP (D2)** | `ShpD2` | Dune 2 兼容 | 8-bit | — |
| **SHP (Remastered)** | `ShpRemastered` | C&C Remastered 资源 | RGBA | — |
| **TMP (RA)** | `TmpRA` | RA 地形瓦片 | 8-bit | — |
| **TMP (TD)** | `TmpTD` | TD 地形瓦片 | 8-bit | — |
| **TMP (TS)** | `TmpTS` | TS 地形瓦片（含深度） | 8-bit | — |
| **PNG Sheet** | `PngSheet` | 现代 mod 推荐 | Indexed8/RGBA32 | PNG |
| **TGA** | `Tga` | 真彩色纹理 | RGB24/RGBA32 | — |
| **DDS** | `Dds` | DirectDraw 纹理 | 多种 | 硬件压缩 |
| **VXL/HVA** | — | 3D 体素模型+动画 (TS) | — | — |

### 3.2 各 Mod 使用的格式

| Mod | SpriteFormats 配置 |
|-----|-------------------|
| **Red Alert (ra)** | `ShpD2, ShpTD, TmpRA, TmpTD, ShpTS` |
| **Tiberian Dawn (cnc)** | `ShpTD, TmpTD, ShpTS, TmpRA` |
| **Tiberian Sun (ts)** | `ShpTS, TmpTS, ShpTD` |
| **Dune 2000 (d2k)** | `R8, ShpTD, PngSheet` |
| **Mod SDK 示例** | `PngSheet`（仅 PNG） |

### 3.3 归档格式

| 格式 | 说明 |
|------|------|
| **MIX** | 原版 Westwood 归档，无压缩，哈希查找。原版游戏资源都在 MIX 包内 |
| **Pak / BigFile / MegFile** | 其他 Westwood 系列格式 |
| **ZIP** | 通用压缩包支持 |

### 3.4 动画序列定义 (Sequence YAML)

```yaml
# 示例：红警收割机
harv:
  Defaults:
    Filename: harv.shp          # 精灵文件
  idle:
    Facings: 32                  # 32 个朝向
    UseClassicFacings: True
  harvest:
    Start: 32                    # 从第 32 帧开始
    Length: 8                    # 8 帧动画
    Facings: 8
  dock:
    Start: 96
    Length: 8
  icon:
    Filename: harvicon.shp       # 建造图标用独立文件
    Start: 0
```

核心属性：

| 属性 | 说明 |
|------|------|
| `Filename` | 精灵文件名 |
| `Start` / `Length` | 帧范围 |
| `Facings` | 朝向数量（1/8/16/32） |
| `Tick` | 每帧毫秒数（默认 40） |
| `Scale` | **缩放比例**（HD 关键属性） |
| `Offset` | 渲染偏移量 |
| `ShadowStart` | 阴影帧起始索引 |
| `FlipX` / `FlipY` | 镜像翻转 |
| `Combine` | 从多个文件拼接帧 |
| `TilesetFilenames` | 按地貌类型切换文件 |

---

## 4. 资产完整清单

### 4.1 总量概览

| 维度 | 数值 |
|------|------|
| Mod 数量 | 7 个（ra, cnc, ts, d2k, common, modcontent, copilot） |
| 总文件数 | **2,524 个** |
| 总磁盘大小 | **45 MB** |
| 精灵文件 (SHP) | 215 个，1.8 MB |
| 地形文件 (TMP 系列) | 546 个，2.5 MB |
| PNG 文件 | 327 个，12 MB |
| 调色板/二进制 | 187 个，11 MB |
| 序列定义 | 16 个 YAML，9,414 行 |

### 4.2 RA + CNC 合计（主要关注目标）

| 维度 | RA | CNC | 合计 |
|------|-----|-----|------|
| 角色/Actor | 296 | 271 | **567** |
| 动画序列 | 1,092 | 826 | **1,918** |
| 估算总帧数 | ~12,968 | ~10,639 | **~23,607** |
| 独立精灵文件 | 481 | 352 | **~700** |

### 4.3 按类别详细清单

#### 步兵 (Infantry)

| 项目 | RA | CNC |
|------|-----|-----|
| 角色数 | 23 | 9 |
| 序列数 | 327 | 154 |
| 估算帧数 | ~6,188 | ~3,610 |
| **像素尺寸** | **50 x 39** | **50 x 39** |

典型步兵结构：8 朝向 × (站立 + 跑步 + 射击 + 趴下 + 6 种死亡) ≈ 380~530 帧/角色

代表性角色：
- `e1` 步枪兵、`e2` 火箭兵、`e3` 火焰兵、`e4` 特种兵
- `dog` 军犬（含跑/吃/跳 15 序列，~265 帧）
- `shok` 磁暴步兵、`e6` 工程师、`spy` 间谍
- CNC 特有：`rmbo` 突击队员、恐龙系列（`trex`, `steg`, `rapt`, `tric`）

#### 载具 (Vehicles)

| 项目 | RA | CNC |
|------|-----|-----|
| 角色数 | 30（含 8 残骸） | 31（含 15 残骸） |
| 序列数 | 81 | 83 |
| 估算帧数 | ~1,525 | ~1,722 |

**确认尺寸**：

| 载具 | 尺寸 | 文件 |
|------|------|------|
| 供给卡车 | **24 x 24** | truk.shp |
| 火焰坦克 | **36 x 36** | ftrk.shp |
| 干扰车 | **40 x 40** | mgg.shp |
| 收割机 | **48 x 48** | harv.shp |
| MCV | **48 x 48** | mcv.shp |
| 轻/中/重/猛犸坦克 | ~32x32~48x48 | 1tnk~4tnk.shp |

多数载具为 32 朝向，带炮塔的还有独立炮塔精灵（额外 32 帧）。

#### 飞机 (Aircraft)

| 项目 | RA | CNC |
|------|-----|-----|
| 角色数 | 10 | 5 |
| 估算帧数 | ~262 | ~228 |

**确认尺寸**：

| 飞机 | 尺寸 |
|------|------|
| 长弓阿帕奇 | **46 x 29** |
| 雌鹿直升机 | **56 x 56** |
| 雅克攻击机 | **40 x 40** |
| 支奴干运输机 | **48 x 48** |
| 黑鹰 | **32 x 21** |

直升机有独立旋翼覆盖层精灵（`lrotor.shp`, `rrotor.shp`）。

#### 舰船 (Ships) — 仅 RA

| 项目 | 数值 |
|------|------|
| 角色数 | 6 |
| 估算帧数 | ~133 |

含巡洋舰、驱逐舰、PT 快艇（带独立炮塔精灵）和登陆艇。

#### 建筑 (Structures)

| 项目 | RA | CNC |
|------|-----|-----|
| 角色数 | 37 | 30 (+3 残骸) |
| 序列数 | 220 | 177 |
| 估算帧数 | ~2,037 | ~1,546 |

**确认尺寸**（按占地面积）：

| 占地 | 尺寸 | 代表建筑 |
|------|------|----------|
| 1x1 | **24 x 24** | 矿仓 (silo)、围墙 |
| 1x2 | **24 x 48** | 裂缝产生器 (gap) |
| 2x1 | **48 x 24** | SAM 导弹塔 |
| 2x2 | **48 x 48** | 兵营、科技中心、停机坪 |
| 3x2 | **72 x 48** | 战车工厂、机场、雷达站 |
| 3x3 | **72 x 72** | 建造厂、高级电厂 |
| 4x2 | **96 x 48** | CNC 机场 |
| 2x3 | **48 x 72** | CNC 圣殿 (Hand of Nod) |
| 图标 | **64 x 48** | 所有建造图标 |

每个建筑典型包含：idle、damaged-idle、make（建造动画）、bib（地基）序列。

#### 装饰与地形物 (Decorations)

| 项目 | RA | CNC |
|------|-----|-----|
| 角色数 | 120 | — |
| 估算帧数 | ~840 | — |

- 树木 22 种（含焚毁残骸变体）
- 村庄建筑 37 种（2 帧：完好 + 损坏）
- 特殊动画：风车 (60x60, 8 帧)、灯塔 (60x60, 16 帧)
- 基础尺寸 **24 x 24**

#### 特效与杂项 (Misc)

| 项目 | RA | CNC |
|------|-----|-----|
| 角色数 | 70 | — |
| 估算帧数 | ~1,983 | — |

- 爆炸效果 19 种
- 火焰/烟雾效果
- 弹道精灵（32 朝向）
- 资源矿石 8 种
- 箱子 9 种
- UI 元素：pips (4x4)、军衔 (12x12)

#### 地形瓦片 (Terrain Tiles)

| 扩展名 | 文件数 | 大小 | 地貌类型 |
|--------|--------|------|----------|
| .jun | 211 | 1.1 MB | 丛林 |
| .des | 183 | 872 KB | 沙漠 |
| .tem | 97 | 428 KB | 温带 |
| .sno | 38 | 160 KB | 雪地 |
| .int | 13 | 52 KB | 室内 |
| .win | 4 | 16 KB | 冬季 |
| **合计** | **546** | **2.5 MB** | — |

所有瓦片基础尺寸 **24 x 24**。

#### UI / Chrome

| 资源 | 分辨率 | 文件 |
|------|--------|------|
| CNC Chrome 3x | 4096 x 2048 | cnc/uibits/chrome-3x.png |
| CNC Chrome 2x | 2048 x 1024 | cnc/uibits/chrome-2x.png |
| CNC Chrome 1x | 1024 x 512 | cnc/uibits/chrome.png |
| RA Sidebar | 512 x 512 | ra/uibits/sidebar.png |
| RA Dialog | 1024 x 512 | ra/uibits/dialog.png |
| RA Glyphs 3x | 1024 x 1024 | ra/uibits/glyphs-3x.png |
| RA Loadscreen 3x | 2048 x 1024 | ra/uibits/loadscreen-3x.png |

UI 已有 1x/2x/3x 三套分辨率，引擎根据 DPI 自动选择。

### 4.4 尺寸分布热力图

```
像素范围          文件占比       说明
─────────────────────────────────────────────
  4x4 ~ 16x16    ███            ~5%    pips, 军衔, 小 UI
 24x24 ~ 32x32   ████████████   ~45%   地形, 小载具, 围墙, 矿仓
 36x36 ~ 56x56   ██████████     ~35%   步兵, 多数载具, 飞机
 60x60 ~ 96x48   ████           ~10%   建筑, 特殊装饰
  64x48 (icon)   ██             ~5%    建造图标
─────────────────────────────────────────────
UI PNG           独立           256x256 ~ 4096x4096
```

**核心发现**：约 80% 的精灵尺寸在 **24x24 ~ 56x56 像素**之间。

---

## 5. 引擎 HD 支持能力

### 5.1 Scale 属性

每个动画序列支持独立 `Scale` 属性：

```csharp
// OpenRA.Mods.Common/Graphics/DefaultSpriteSequence.cs
[Desc("Adjusts the rendered size of the sprite")]
protected static readonly SpriteSequenceField<float> Scale = new(nameof(Scale), 1);
```

渲染管线全程支持 Scale：`Animation.Render()` → `SpriteRenderable` → `SpriteRenderer.DrawSprite()` → GPU

**用法示例**：

```yaml
e1:
  Defaults:
    Scale: 0.5              # 精灵是 2x 分辨率，缩放回正常占位
  idle:
    Filename: e1-hd.png     # 100x78 的 HD 精灵（原版 50x39 的 2 倍）
    Facings: 8
```

### 5.2 TileSize 可配置

```csharp
// OpenRA.Game/Map/MapGrid.cs
public readonly Size TileSize = new(24, 24);  // 默认值，可在 mod 中覆盖
```

屏幕坐标公式：`screen_px = TileSize × world_units / TileScale`

### 5.3 已验证先例：TiberianDawnHD

官方 TiberianDawnHD mod 已实现完整的高清化：

| 对比项 | 原版 | HD 版 | 倍率 |
|--------|------|-------|------|
| 地形瓦片 | 24 x 24 | 128 x 128 | **5.33x** |
| TileSize | 24, 24 | 128, 128 | — |
| 纹理图集 | 2048 x 2048 | 4096 x 4096 | 4x |

关键实现：
- `RemasterSpriteSequence` 自定义加载器
- `classicUpscaleFactor = RemasteredTileSize / TileSize` 自动缩放旧资源
- HD 精灵 `Scale: 1.0`，旧精灵自动乘放大系数

### 5.4 两种 HD 路线对比

| 维度 | 方案 A：保持 TileSize + Scale | 方案 B：改 TileSize（仿 TiberianDawnHD） |
|------|------|------|
| 复杂度 | 低——只改精灵文件 + YAML | 高——需自定义 SpriteSequence loader |
| 兼容性 | 完全兼容，可逐步替换 | 需全量替换或写兼容层 |
| 效果 | 单位更清晰，地形不变 | 全面 HD，地形也高清 |
| 工作量 | 替换精灵 + 每个 sequence 加 Scale | 替换全部资源 + 自定义引擎模块 |
| 推荐 | ✅ **阶段一首选** | 阶段二再考虑 |

---

## 6. AI 图片生成定价分析

### 6.1 Google Gemini "Nano Banana" 系列

| 模型 | ID | 最小输出 | 512px | 1024px | 4096px | Batch 折扣 |
|------|-----|---------|-------|--------|--------|-----------|
| **Nano Banana 2** | `gemini-3.1-flash-image-preview` | 512px | $0.045 | $0.067 | $0.151 | **50% off** |
| Nano Banana | `gemini-2.5-flash-image` | 1024px | — | $0.039 | 不支持 | 50% off |
| Nano Banana Pro | `gemini-3-pro-image-preview` | 1024px | — | $0.134 | $0.240 | 50% off |

定价基于 output token 数，与分辨率正相关。

### 6.2 Google Imagen 4

| 模型 | 单价 | 特点 |
|------|------|------|
| **Imagen 4 Fast** | **$0.02/张** | 固定价，不分辨率 |
| Imagen 4 Standard | $0.04/张 | |
| Imagen 4 Ultra | $0.06/张 | |

### 6.3 竞品对比

| 方案 | 单价 (1024px) | 供应商 | 备注 |
|------|-------------|--------|------|
| **Flux Schnell** | **$0.004** | BFL / 第三方 | 最便宜，开源权重 |
| Flux Dev | $0.033 | BFL | 开源 |
| Stable Diffusion 3.5 | $0.025 | Stability AI | 可自部署（免费） |
| **Imagen 4 Fast** | **$0.02** | Google | 固定价 |
| **Gemini 3.1 Flash Batch** | **$0.022** (512px) | Google | 需等 2-24h |
| DALL-E 3 | $0.04 | OpenAI | |
| GPT Image 1 | $0.04~0.167 | OpenAI | 按质量分档 |
| Flux Pro 1.1 | $0.052 | BFL | |

### 6.4 关键限制

> **所有云端模型最小输出 512px。**
>
> 一张 24x24 的地形瓦片和一张 512x512 的图收费相同。
> 但这正好意味着——可以免费获得"高清版"，生成后缩小即可。

---

## 7. 费用估算

### 7.1 去重分析

23,607 总帧并非全部需要 AI 重绘。大量帧是朝向旋转和简单变体：

| 原始数据 | 数量 |
|----------|------|
| 总帧数 | 23,607 |
| 减去朝向旋转帧（8/16/32 向可从 1 帧生成） | -16,000 |
| 减去镜像/翻转帧 | -2,000 |
| 减去阴影帧 | -1,500 |
| 减去简单变体（损坏态=叠加处理） | -1,000 |
| **需 AI 重绘的独立图像** | **~800 ~ 1,200 张** |

### 7.2 按类别估算独立图像数

| 类别 | 独立图像（估） | 说明 |
|------|-------------|------|
| 步兵 | ~200 | 32 角色 × ~6 基础姿态（去朝向） |
| 载具 | ~80 | 含残骸，去朝向后每载具 1-2 基础图 |
| 飞机 | ~20 | 去朝向，含旋翼 |
| 舰船 | ~15 | 含炮塔 |
| 建筑 | ~150 | 每建筑 2-3 态（完好/建造/损坏）|
| 建造图标 | ~70 | 独立 64x48 图标 |
| 装饰/地形物 | ~150 | 树/建筑/岩石 |
| 地形瓦片 | ~200 | 按模板去重后 |
| 特效/弹道 | ~80 | 爆炸/火焰/烟雾关键帧 |
| UI | ~30 | chrome/sidebar/glyphs 图集 |
| **合计** | **~1,000 张** | — |

### 7.3 成本矩阵（单轮生成）

| 方案 | 小图 ×950 | 大图 (UI) ×50 | 单轮总计 |
|------|----------|-------------|---------|
| **Flux Schnell** | $3.80 | $0.20 | **$4** |
| **Imagen 4 Fast** | $19.00 | $1.00 | **$20** |
| **Gemini 3.1 Flash Batch** | $20.90 | $3.80 | **$25** |
| Gemini 3.1 Flash 标准 | $42.75 | $7.55 | **$50** |
| Gemini 3 Pro Batch | $63.65 | $6.00 | **$70** |
| DALL-E 3 | $38.00 | $4.00 | **$42** |

### 7.4 考虑迭代（Prompt 调优 + 质量筛选）

预计需要 **3~5 轮迭代**（调 prompt / 筛选质量 / 风格统一）：

| 方案 | 3 轮 | 5 轮 | 备注 |
|------|------|------|------|
| **Flux Schnell** | **$12** | **$20** | 最省钱，质量可能需要更多轮 |
| **Imagen 4 Fast** | **$60** | **$100** | 性价比最优 |
| **Gemini 3.1 Flash Batch** | **$75** | **$125** | Google 最新，质量好 |
| Gemini 3 Pro Batch | $210 | $350 | 最高质量，价格也最高 |

### 7.5 推荐预算

| 策略 | 预算 | 方案 |
|------|------|------|
| 💰 极致省钱 | **$20~50** | Flux Schnell，自行多轮筛选 |
| ⚖️ 性价比（推荐） | **$60~150** | Imagen 4 Fast 或 Gemini 3.1 Flash Batch |
| 🎨 最高质量 | **$200~400** | Gemini 3 Pro Batch，少量迭代 |

---

## 8. 推荐管线方案

### 8.1 总体架构

```
阶段 1: 提取                          阶段 2: 生成                    阶段 3: 后处理                阶段 4: 回写
─────────────────                    ──────────────                  ────────────                ──────────
MIX 归档 ──→ 提取到散文件               分类+prompt 模板                缩放到目标尺寸               PNG → SHP 转换
SHP/TMP  ──→ 转换为 PNG               ──→ API 批量调用               调色板匹配                   更新 sequence YAML
序列 YAML ─→ 解析帧信息                ──→ 质量自动筛选               帧序列重组                   验证完整性
                                      ──→ 人工抽检                  朝向旋转生成
                                                                   阴影帧生成
```

### 8.2 具体步骤

#### Step 1: 资源提取

```bash
# 提取 MIX 包内容
OpenRA.Utility ra --extract conquer.mix
OpenRA.Utility ra --extract temperat.mix

# SHP → PNG 批量转换
for shp in mods/ra/bits/*.shp; do
    OpenRA.Utility ra --png "$shp" temperat.pal --noshadow
done

# 导出完整序列图集（用于参考）
OpenRA.Utility ra --dump-sequence-sheets temperat.pal temperat
```

#### Step 2: 资产分析与分类

编写 Python 脚本解析所有 sequence YAML：
- 输出每个 actor 的帧清单、尺寸、朝向数
- 计算需要生成的独立图像数
- 生成 prompt 模板（按类别）

#### Step 3: AI 批量生成

```python
# 伪代码
for asset in asset_list:
    prompt = template.format(
        type=asset.category,        # "infantry", "vehicle", "building"
        name=asset.name,            # "rifle soldier", "heavy tank"
        style="isometric pixel art, Red Alert style, clean edges",
        size="512x512",
        facing="front-facing, 3/4 top-down view"
    )
    result = api.generate(prompt, model="imagen-4-fast")
    save(result, f"output/{asset.name}_base.png")
```

#### Step 4: 后处理管线

```
基础图 (512x512)
  ├→ 缩放到目标 HD 尺寸（如 100x78 = 原版 2x）
  ├→ 调色板量化（256 色，保留玩家颜色重映射区 240-255）
  ├→ 朝向旋转（从正面生成 8/16/32 向）
  ├→ 阴影帧生成（半透明投影）
  └→ 帧序列打包
```

#### Step 5: 回写与验证

```bash
# PNG → SHP
OpenRA.Utility ra --shp frame0000.png frame0001.png ...

# 或直接使用 PNG 工作流
# 更新 mod.yaml: SpriteFormats 加入 PngSheet
# 更新 sequences YAML: 加 Scale 和新 Filename

# 验证
OpenRA.Utility ra --check-missing-sprites
```

### 8.3 优先级建议

| 阶段 | 内容 | 工作量 | 视觉收益 |
|------|------|--------|---------|
| **P0** | 载具 + 建筑（最显眼） | ~230 图 | ⭐⭐⭐⭐⭐ |
| **P1** | 步兵 | ~200 图 | ⭐⭐⭐⭐ |
| **P2** | 建造图标 + UI | ~100 图 | ⭐⭐⭐ |
| **P3** | 装饰/地形物 | ~150 图 | ⭐⭐⭐ |
| **P4** | 地形瓦片 | ~200 图 | ⭐⭐（数量大但视觉单调） |
| **P5** | 特效/弹道 | ~80 图 | ⭐⭐ |

---

## 9. 风险与注意事项

### 9.1 技术风险

| 风险 | 严重性 | 缓解措施 |
|------|--------|----------|
| 调色板索引不匹配（玩家颜色失效） | 高 | 后处理时严格保留 240-255 索引区 |
| 精灵偏移错位（锚点不对） | 中 | 保持原始精灵中心对齐，测试每个 actor |
| 帧数不匹配（动画播放异常） | 高 | 严格按 sequence YAML 定义生成对应帧数 |
| 风格不统一（AI 生成每张都不一样） | 中 | 统一 prompt 模板 + style reference 图 + 种子锁定 |
| 旋转帧质量差（AI 生成侧面不一致） | 中 | 用 3D 渲染或专门的多视角生成模型 |
| 纹理图集超限 | 低 | 增大 BgraSheetSize 到 4096 |

### 9.2 美术风险

| 风险 | 说明 | 缓解 |
|------|------|------|
| 丢失原版美学 | AI 可能"太现代"、失去像素怀旧感 | 在 prompt 中明确风格参考 |
| 单位辨识度降低 | HD 化后轮廓变化可能影响游戏可读性 | 保持原始比例和颜色特征 |
| 阴影/透明不一致 | 原版阴影用特殊调色板索引 | 后处理统一生成阴影层 |

### 9.3 法律风险

| 风险 | 说明 |
|------|------|
| 原版资源版权 | 原版资源属于 EA，提取仅供参考。HD 版应为全新创作 |
| AI 生成物版权 | 各平台政策不同，商用需确认 TOS |

---

## 10. 结论

### 10.1 可行性判定

| 维度 | 结论 |
|------|------|
| **技术可行性** | ✅ 完全可行。引擎原生支持 Scale、PNG 工作流、变尺寸精灵 |
| **资产规模** | ✅ 可控。去重后约 1,000 张独立图，45MB 总量 |
| **成本** | ✅ 合理。$60~150 即可完成一轮完整生成 |
| **工具链** | ✅ 完备。OpenRA.Utility 提供 SHP↔PNG 双向转换 + 批量导出 |
| **先例** | ✅ TiberianDawnHD 已验证 5.33x 高清化路径 |

### 10.2 推荐行动

1. **立即可做**：用 `OpenRA.Utility --dump-sequence-sheets` 导出全部资源作为参考素材
2. **编写管线工具**：Python 脚本自动化「解析 YAML → 生成 prompt → 调 API → 后处理 → 打包」
3. **小规模验证**：先选 5~10 个载具做 PoC，验证全流程后再批量铺开
4. **预算 $100~150**：选 Imagen 4 Fast 或 Gemini 3.1 Flash Batch，覆盖 3 轮迭代

---

## 附录

### A. 内置工具命令速查

```bash
# 精灵 → PNG
OpenRA.Utility {mod} --png SPRITEFILE PALETTE [--noshadow] [--nopadding]

# PNG → SHP
OpenRA.Utility {mod} --shp PNG [PNG ...]

# 批量导出序列图集
OpenRA.Utility {mod} --dump-sequence-sheets PALETTE TILESET-OR-MAP

# 从 MIX 提取
OpenRA.Utility {mod} --extract FILENAME [FILENAME...]

# 调色板重映射
OpenRA.Utility {mod} --remap SRCMOD:PAL DESTMOD:PAL SRC.shp DST.shp

# PNG metadata
OpenRA.Utility {mod} --png-sheet-import PNGFILE
OpenRA.Utility {mod} --png-sheet-export PNGFILE

# 验证
OpenRA.Utility {mod} --check-missing-sprites
```

### B. 关键源码路径

| 文件 | 说明 |
|------|------|
| `OpenRA.Game/Graphics/SpriteLoader.cs` | 精灵加载接口 |
| `OpenRA.Game/Graphics/SpriteCache.cs` | 精灵缓存 |
| `OpenRA.Game/Graphics/SequenceSet.cs` | 序列集（含 Scale 定义） |
| `OpenRA.Game/Map/MapGrid.cs` | TileSize 定义 |
| `OpenRA.Mods.Common/Graphics/DefaultSpriteSequence.cs` | 默认序列实现 |
| `OpenRA.Mods.Common/SpriteLoaders/PngSheetLoader.cs` | PNG 加载器 |
| `OpenRA.Mods.Cnc/SpriteLoaders/ShpTDLoader.cs` | SHP(TD) 加载器 |
| `OpenRA.Mods.Cnc/UtilityCommands/ConvertPngToShpCommand.cs` | PNG→SHP 工具 |
| `OpenRA.Mods.Common/UtilityCommands/ConvertSpriteToPngCommand.cs` | SHP→PNG 工具 |
| `OpenRA.Mods.Common/UtilityCommands/DumpSequenceSheetsCommand.cs` | 批量导出工具 |

### C. Sequence YAML 关键属性速查

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `Filename` | string | actor 名 | 精灵文件 |
| `Start` | int | 0 | 起始帧 |
| `Length` | int | 1 | 帧数（`*` = 全部） |
| `Facings` | int | 1 | 朝向数 |
| `Tick` | int | 40 | 每帧毫秒 |
| `Scale` | float | 1.0 | **缩放比例** |
| `Offset` | float3 | 0,0,0 | XYZ 偏移 |
| `ShadowStart` | int | -1 | 阴影帧起始 |
| `FlipX` / `FlipY` | bool | false | 镜像 |
| `Frames` | int[] | null | 显式帧列表 |
| `Combine` | MiniYaml | null | 多文件帧拼接 |
| `TilesetFilenames` | dict | null | 按地貌切换文件 |
| `UseClassicFacings` | bool | false | Westwood 旋转修正 |

### D. 参考链接

- [OpenRA Modding Guide (Wiki)](https://github.com/OpenRA/OpenRA/wiki/Modding-Guide)
- [OpenRA Sprite Sequences (Docs)](https://docs.openra.net/en/release/sprite-sequences/)
- [TiberianDawnHD (GitHub)](https://github.com/OpenRA/TiberianDawnHD)
- [OpenRA Mod SDK (GitHub)](https://github.com/OpenRA/OpenRAModSDK)
- [Using PNG Artwork (The OpenRA Book)](https://www.openra.net/book/modding/pngartwork/pngartwork.html)
- [Gemini API Image Generation Pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Imagen 4 Documentation](https://cloud.google.com/vertex-ai/generative-ai/pricing)
