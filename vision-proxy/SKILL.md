---
name: vision-proxy
description: Delegate image understanding to a vision-capable model when the current model cannot see images. Use this skill PROACTIVELY whenever the user attaches, pastes, references by path, or links an image (PNG/JPG/GIF/WEBP/BMP) and the current model lacks vision — e.g. glm-5.2/glm-5.1/deepseek-v4 and other text-only models — so the assistant can still read screenshots, parse UI mockups, extract text from photos, interpret charts/diagrams, compare images, and answer any "what's in this picture" question. Also trigger when an upstream tool like playwright-cli, screenshot, or markitdown produces an image the model must inspect, when the user says "看下这张图", "识别图中文字", "这个截图里是什么", "describe this image", "what does this show", or drops a local image path / URL without further instruction. Works with any OpenAI Responses-API-compatible endpoint via configurable base URL, API key, and model; supports local files (base64), public URLs, and multi-image batches.
---

# Vision Proxy

让不支持视觉的文本模型（如 glm-5.2、deepseek-v4 等）也能"看懂"图片：把图片委托给一个具备视觉能力的模型（默认 cpa 代理的 gpt-5.5，走 OpenAI Responses API），拿回文本描述/分析结果，再由当前模型据此完成后续任务。

## 为什么需要这个 skill

很多强大的编码/推理模型（包括当前会话可能使用的 glm-5.2-ali）本身没有视觉输入能力。当用户贴图、截图、或引用图片路径时，这类模型会"失明"——既无法读取图片内容，也容易在不知情的情况下凭空猜测，给出错误结论。这个 skill 就是为这种"失明"场景兜底：通过一个可配置的视觉模型 API 把图片内容转成文字，让当前模型重新具备图像理解能力。

## 何时触发（重要）

只要满足以下任一条件，就应主动使用本 skill，无需用户明说"用 vision skill"：

- 用户消息中包含图片附件、粘贴的图片、本地图片路径（如 `~/Downloads/x.png`、`./screenshot.png`）或图片 URL
- 用户使用 playwright-cli 截图、markitdown 转换、或其它工具产出了需要查看的图片文件
- 用户说"看下这张图""图里写了什么""这个截图是什么意思""帮我识别""describe/describe this image""what's in this""read the text in the image""OCR 一下"等
- 当前模型确认不支持图像输入，但任务又依赖图像内容
- 用户让你"对比这两张图""看看布局对不对""图表说明了什么"

不要把图片理解任务硬塞给当前文本模型——它看不到，会编造。交给视觉模型去读。

## 配置

通过环境变量配置，无硬编码厂商绑定。脚本启动时会读取这些变量，缺失时给出明确提示。

| 变量 | 必需 | 默认值 | 说明 |
|---|---|---|---|
| `VISION_BASE_URL` | 是 | `http://127.0.0.1:8317/v1` | OpenAI 兼容的 API 根地址（到 `/v1`） |
| `VISION_API_KEY` | 是 | `sk-xxx` | API 密钥 |
| `VISION_MODEL` | 是 | `gpt-5.5` | 具备视觉能力的模型名 |
| `VISION_DETAIL` | 否 | `auto` | 图片采样精度：`low`/`high`/`auto` |
| `VISION_MAX_TOKENS` | 否 | `1024` | 返回文本上限 |
| `VISION_REASONING` | 否 | `medium` | 推理强度：`minimal`/`low`/`medium`/`high`（模型不支持时自动忽略） |
| `VISION_TIMEOUT` | 否 | `120` | 单次请求超时秒数 |

> 默认值面向本机 cpa 代理 + gpt-5.5，开箱即用。换其它 OpenAI 兼容网关只需改 `VISION_BASE_URL`/`VISION_API_KEY`/`VISION_MODEL`。

## 工作流程

1. 识别图片来源：本地文件路径、或公网 URL（http/https 开头）。
2. 决定提示语（prompt）：用户给了明确问题就用用户的；没给就用通用"详细描述这张图片的内容"。
3. 运行 `scripts/vision.py`，把图片 + 提示语交给视觉模型。
4. 脚本返回纯文本结果，直接用于后续推理与回答。

## 命令

脚本位于本 skill 目录下的 `scripts/vision.py`，单文件、无第三方依赖（仅用 Python 标准库）。

### 单张本地图片

```bash
python ~/.agents/skills/vision-proxy/scripts/vision.py ~/Desktop/screenshot.png "描述这张截图的内容"
```

### 单张图片 URL

```bash
python ~/.agents/skills/vision-proxy/scripts/vision.py "https://example.com/chart.png" "这个图表展示了什么数据？"
```

### 多张图片（批量，同一个 prompt 对每张图各跑一次）

```bash
python ~/.agents/skills/vision-proxy/scripts/vision.py img1.png img2.png "对比这两张图的不同"
```

> 注意：批量模式是逐张独立请求、逐条返回，适合"分别描述"。若需要把多张图放在同一次请求里让模型联合分析，用 `--joint`：

```bash
python ~/.agents/skills/vision-proxy/scripts/vision.py --joint img1.png img2.png "这两张图有什么区别？"
```

### 不带 prompt（使用默认"详细描述图片内容"）

```bash
python ~/.agents/skills/vision-proxy/scripts/vision.py ~/Downloads/photo.jpg
```

### 覆盖配置（临时换模型/端点）

```bash
VISION_MODEL=gpt-5.4 python ~/.agents/skills/vision-proxy/scripts/vision.py img.png "分析布局问题"
```

### 只打印将发送的 payload，不真正请求（调试用）

```bash
python ~/.agents/skills/vision-proxy/scripts/vision.py img.png "测试" --dry-run
```

## 参数说明

```
vision.py [--joint] [--detail auto|low|high] [--model NAME]
          [--max-tokens N] [--reasoning minimal|low|medium|high]
          [--timeout S] [--dry-run] [--raw]
          <image> [<image> ...] [prompt]
```

- 第一个非 flag 参数起为图片；最后一个图片之后的纯文本视为 prompt。
- `--joint`：把多张图片放进同一次请求，让模型联合理解。
- `--detail`：覆盖 `VISION_DETAIL`。
- `--raw`：除模型返回的文本外，额外打印原始 JSON 响应到 stderr（调试用）。
- 退出码：`0` 成功；`1` 配置缺失；`2` 请求失败；`3` 参数错误。

## 使用建议

- 优先用用户的原话作为 prompt，比通用"描述图片"信息量大得多。
- 截图/UI 类图片，`--detail high` 能看清小字与像素级布局；普通照片 `auto` 即可。
- 文字提取（OCR）场景，prompt 写"逐字提取图中所有可见文字，保持原有排版"效果最好。
- 返回文本较长时，脚本不做截断，由当前模型自行消化。
- 图片很大（>10MB）时建议先压缩再传入，避免 base64 体积过大拖慢请求。

## 从 opencode 会话数据库提取用户附件图片

当用户在 **opencode** / **openchamber** 中直接粘贴/拖入图片附件，但未提供本地文件路径时，图片以 base64 data URL 形式存储在 opencode 的 SQLite 数据库里，磁盘上找不到对应文件。此时需要先从数据库提取图片，再交给 vision-proxy。

### 存储结构

opencode 把会话消息和附件存在 SQLite 数据库：

- **数据库路径**：`~/.local/share/opencode/opencode.db`（`$XDG_DATA_HOME/opencode/opencode.db`）
- **核心表**：
  - `session`：会话元数据，字段 `id`、`title`、`time_created`
  - `message`：消息，字段 `id`、`session_id`、`data`（JSON）
  - `part`：消息组成部分（文本/文件/工具调用等），字段 `id`、`session_id`、`message_id`、`data`（JSON）
- **图片附件**：存储在 `part` 表的 `data` 字段，JSON 结构为 `{ "type": "file", "url": "data:image/png;base64,...", "filename": "image-1.png", "mime": "image/png" }`
- **会话 ID 格式**：`ses_xxxxxxxxxxxxXXXXXXXXXX`（前缀 `ses_`）

### 提取步骤

#### 1. 定位当前会话 ID

当前会话 ID 可从环境变量或最新会话获取：

```bash
# 从环境变量获取（Trellis 上下文）
echo "$TRELLIS_CONTEXT_ID"  # 形如 opencode_ses_xxxx，去掉 opencode_ 前缀即会话 ID

# 或查看最近的会话
sqlite3 ~/.local/share/opencode/opencode.db \
  "SELECT id, title, datetime(time_created/1000, 'unixepoch', 'localtime') FROM session ORDER BY time_created DESC LIMIT 5;"
```

#### 2. 查找当前会话的图片附件

```bash
sqlite3 ~/.local/share/opencode/opencode.db \
  "SELECT id, json_extract(data, '$.type'), json_extract(data, '$.mime'), json_extract(data, '$.filename')
   FROM part
   WHERE session_id='ses_XXXXXXXXXX'
     AND json_extract(data, '$.type')='file'
   ORDER BY time_created;"
```

#### 3. 解码 base64 保存为本地文件

```bash
# 单张图片
mkdir -p /tmp/opencode/vision
sqlite3 ~/.local/share/opencode/opencode.db \
  "SELECT json_extract(data, '$.url')
   FROM part
   WHERE session_id='ses_XXXXXXXXXX'
     AND json_extract(data, '$.type')='file'
     AND json_extract(data, '$.filename')='image-1.png'
   LIMIT 1;" \
  | sed 's/^data:image\/png;base64,//' \
  | base64 -d > /tmp/opencode/vision/image-1.png
```

> **注意 MIME 类型**：`data:image/png;base64,` 中的 `image/png` 要根据实际 `$.mime` 字段调整 sed 替换规则。更稳妥的写法是用 Python 处理 data URL。

#### 4. 交给 vision-proxy 分析

```bash
python ~/.agents/skills/vision-proxy/scripts/vision.py \
  /tmp/opencode/vision/image-1.png \
  "详细描述这张图片的内容" --detail high --max-tokens 2048
```

### 一键提取脚本（推荐）

把步骤 3-4 合并，直接从数据库取图交给视觉模型，无需中间文件。适合写进 shell 函数或 alias：

```bash
# 用法：ocimage <session_id> <filename> [vision-prompt]
ocimage() {
  local sid="$1" fname="$2" prompt="${3:-详细描述这张图片的内容}"
  local tmpdir="${TMPDIR:-/tmp}/opencode/vision"
  mkdir -p "$tmpdir"
  local out="$tmpdir/${fname}"
  python3 - "$sid" "$fname" "$out" <<'PY'
import sqlite3, base64, sys, os, re, json
sid, fname, out = sys.argv[1], sys.argv[2], sys.argv[3]
db = os.path.expanduser("~/.local/share/opencode/opencode.db")
con = sqlite3.connect(db)
row = con.execute(
    "SELECT json_extract(data,'$.url') FROM part WHERE session_id=? "
    "AND json_extract(data,'$.type')='file' AND json_extract(data,'$.filename')=? LIMIT 1",
    (sid, fname)).fetchone()
con.close()
if not row or not row[0]:
    sys.exit("未找到图片附件")
url = row[0]
m = re.match(r"data:([^;]+);base64,(.*)", url, re.S)
if not m:
    sys.exit("不是 base64 data URL")
data = base64.b64decode(m.group(2))
with open(out, "wb") as f: f.write(data)
print(out)
PY
  python ~/.agents/skills/vision-proxy/scripts/vision.py "$out" "$prompt" --detail high
}
```

### 判断当前模型是否需要走此流程

- 用户消息中出现 `[image-N.png]` 但没有本地路径，且当前模型报错"does not support image input" → 需要从数据库提取。
- 用户明确给出本地路径（如 `~/Downloads/x.png`）→ 直接走标准命令，无需数据库提取。
- 用户给出 http(s) URL → 直接走标准命令。

### 注意事项

- opencode 数据库可能较大（本例约 950MB），查询时务必带 `session_id` 和 `LIMIT`，避免全表扫描。
- 多个附件按 `time_created` 排序，文件名可能重复（如多张 `image-1.png` 来自不同会话），用 session_id 限定范围。
- 数据库有 `-wal` 和 `-shm` 伴随文件，查询是只读操作不会影响 opencode 运行。
- 旧版 opencode（2026 年 2 月前）使用文件系统 JSON 存储（`storage/part/<message_id>/<part_id>.json`），新版已迁移到 SQLite。若 SQLite 查不到，可退回 `~/.local/share/opencode/storage/part/` 查找。

## 资源

- 脚本：[scripts/vision.py](./scripts/vision.py)
