#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vision.py — 把图片交给具备视觉能力的模型，拿回文本描述/分析结果。

设计目标：
- 零第三方依赖，仅用 Python 标准库（urllib + base64 + json）。
- 兼容任意 OpenAI Responses API 端点（默认指向本机 cpa 代理）。
- 同时支持本地文件（base64 编码）与公网 URL（原样透传）。
- 单图 / 多图独立 / 多图联合 三种模式。
"""

import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request

DEFAULTS = {
    "base_url": "http://127.0.0.1:8317/v1",
    "api_key": "sk-r8Z87oUgrcTZyGszs",
    "model": "gpt-5.5",
    "detail": "auto",
    "max_tokens": "1024",
    "reasoning": "medium",
    "timeout": "120",
}

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
URL_PREFIXES = ("http://", "https://")


def env(key, default):
    v = os.environ.get(key)
    return v if v else default


def die(code, msg):
    print(msg, file=sys.stderr)
    sys.exit(code)


def is_url(s):
    return s.lower().startswith(URL_PREFIXES)


def guess_mime(path):
    m, _ = mimetypes.guess_type(path)
    return m or "image/png"


def file_to_data_url(path):
    if not os.path.isfile(path):
        die(3, f"图片文件不存在: {path}")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    mime = guess_mime(path)
    return f"data:{mime};base64,{b64}"


def build_image_block(src):
    """构造一个 input_image 内容块。本地文件转 data URL，URL 原样透传。"""
    if is_url(src):
        return {"type": "input_image", "image_url": src}
    return {"type": "input_image", "image_url": file_to_data_url(src)}


def split_args(argv):
    """把命令行参数拆成 (images, prompt)。

    规则：
    - 以 http(s):// 开头或能对应到已存在文件/有图片扩展名的，视为图片。
    - 第一个非图片参数起，到结尾，全部作为 prompt（允许中间带空格）。
    """
    images = []
    prompt_parts = []
    in_prompt = False
    for a in argv:
        if in_prompt:
            prompt_parts.append(a)
            continue
        is_img = is_url(a) or os.path.isfile(a)
        if not is_img:
            _, ext = os.path.splitext(a)
            is_img = ext.lower() in ALLOWED_IMAGE_EXTS
        if is_img:
            images.append(a)
        else:
            in_prompt = True
            prompt_parts.append(a)
    prompt = " ".join(prompt_parts).strip()
    return images, prompt


def build_one(image, prompt, detail):
    """构造单张图片 + prompt 的 input（一个 message）。"""
    return [
        {
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                build_image_block(image),
            ],
        }
    ]


def build_joint(images, prompt, detail):
    """多图联合：一张 prompt + 所有图片放进同一个 message。"""
    content = [{"type": "input_text", "text": prompt}]
    for img in images:
        content.append(build_image_block(img))
    return [{"type": "message", "role": "user", "content": content}]


def extract_text(resp_json):
    """从 Responses API 返回里抽出最终文本。"""
    out = resp_json.get("output") or []
    texts = []
    for item in out:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "output_text":
                    t = c.get("text")
                    if t:
                        texts.append(t)
    return "\n".join(texts).strip()


def request(base_url, api_key, payload, timeout):
    url = base_url.rstrip("/") + "/responses"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        die(2, f"请求失败 HTTP {e.code}:\n{err_body}")
    except urllib.error.URLError as e:
        die(2, f"网络错误: {e.reason}")


def main():
    parser = argparse.ArgumentParser(
        prog="vision.py",
        description="把图片交给视觉模型理解，返回文本。当前模型不识图时的兜底工具。",
        add_help=True,
    )
    parser.add_argument("args", nargs="*", help="图片路径/URL 与可选 prompt")
    parser.add_argument("--joint", action="store_true",
                        help="多图时放进同一次请求让模型联合分析")
    parser.add_argument("--detail", default=None,
                        choices=["auto", "low", "high"],
                        help="图片采样精度，覆盖 VISION_DETAIL")
    parser.add_argument("--model", default=None, help="模型名，覆盖 VISION_MODEL")
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="返回文本上限，覆盖 VISION_MAX_TOKENS")
    parser.add_argument("--reasoning", default=None,
                        choices=["minimal", "low", "medium", "high"],
                        help="推理强度，覆盖 VISION_REASONING（模型不支持时自动忽略）")
    parser.add_argument("--timeout", type=int, default=None,
                        help="请求超时秒数，覆盖 VISION_TIMEOUT")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印 payload 不发请求")
    parser.add_argument("--raw", action="store_true",
                        help="额外把原始 JSON 响应打到 stderr")
    args = parser.parse_args()

    if not args.args:
        parser.print_help()
        die(3, "\n错误: 至少需要一个图片参数（路径或 URL）")

    images, prompt = split_args(args.args)

    if not images:
        die(3, "未识别到任何图片参数。请提供本地路径或 http(s):// URL。")

    base_url = env("VISION_BASE_URL", DEFAULTS["base_url"])
    api_key = env("VISION_API_KEY", DEFAULTS["api_key"])
    model = args.model or env("VISION_MODEL", DEFAULTS["model"])
    detail = args.detail or env("VISION_DETAIL", DEFAULTS["detail"])
    max_tokens = args.max_tokens or int(env("VISION_MAX_TOKENS", DEFAULTS["max_tokens"]))
    reasoning = args.reasoning or env("VISION_REASONING", DEFAULTS["reasoning"])
    timeout = args.timeout or int(env("VISION_TIMEOUT", DEFAULTS["timeout"]))

    if not (base_url and api_key and model):
        die(1, "配置不完整。请设置 VISION_BASE_URL / VISION_API_KEY / VISION_MODEL 环境变量。")

    # 校验非 URL 图片是否存在
    for img in images:
        if not is_url(img) and not os.path.isfile(img):
            die(3, f"图片文件不存在: {img}")

    # 多图：联合模式放进一次请求；否则逐张独立请求、逐条收集。
    if args.joint or len(images) == 1:
        payload = {"input": build_joint(images, prompt, detail)}
        payload["model"] = model
        payload["max_output_tokens"] = max_tokens
        payload["reasoning"] = {"effort": reasoning}
        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        resp_json = request(base_url, api_key, payload, timeout)
        if args.raw:
            print(json.dumps(resp_json, ensure_ascii=False, indent=2), file=sys.stderr)
        text = extract_text(resp_json)
        if not text:
            die(2, "请求成功但未解析到文本输出。用 --raw 查看完整响应。")
        print(text)
        return

    # 多图独立：逐张发请求
    if args.dry_run:
        payloads = [{"input": build_one(img, prompt, detail),
                     "model": model, "max_output_tokens": max_tokens,
                     "reasoning": {"effort": reasoning}} for img in images]
        print(json.dumps(payloads, ensure_ascii=False, indent=2))
        return

    for i, img in enumerate(images, 1):
        payload = {"input": build_one(img, prompt, detail)}
        payload["model"] = model
        payload["max_output_tokens"] = max_tokens
        payload["reasoning"] = {"effort": reasoning}
        resp_json = request(base_url, api_key, payload, timeout)
        if args.raw:
            print(json.dumps(resp_json, ensure_ascii=False, indent=2), file=sys.stderr)
        text = extract_text(resp_json)
        prefix = f"[图{i}: {img}]"
        print(f"{prefix}\n{text}\n" if text else f"{prefix}\n（未解析到文本）\n")


if __name__ == "__main__":
    main()
