---
name: nsfc-final-report-download
description: Download a publicly available National Natural Science Foundation of China (NSFC) final project report by grant number or project title and assemble the site's page images into a verified PDF. Use for 国家自然科学基金结题报告下载、项目结题报告全文获取，或按批准号/项目名称保存公开结题报告。Do not use to bypass login, CAPTCHA, access controls, or unavailable reports.
---

# 国家自然科学基金结题报告下载

使用 `scripts/download_report.py` 完成项目检索、报告页面下载和 PDF 合成。该脚本适配 `kd.nsfc.cn` 当前公开接口，并处理其 DES 加密检索响应、逐页 PNG 报告格式、间歇性 503、断点续传和页数边界检测。

## 工作流

1. 获取批准号或完整项目名称。两者都有时优先使用批准号，减少重名风险。
2. 调用工作区依赖加载工具，使用返回的 Python 运行时。脚本需要 `cryptography`、`Pillow` 和 `pypdf`。
3. 运行下载器：

   ```powershell
   & '<python-path>' '<skill-dir>\scripts\download_report.py' --grant-number U1806228 --output-dir '<workspace>\output\pdf'
   ```

   只有项目名称时使用 `--title '<项目名称>'`。需要查看匹配但不下载时加 `--lookup-only`。
4. 若返回多个候选，不要猜测。向用户列出批准号、项目名称、负责人和依托单位，请用户选择后再运行。
5. 脚本打印 `OUTPUT_PDF=...`、`PAGE_COUNT=...` 和项目元数据。确认输出 PDF 页数等于 `PAGE_COUNT`。
6. 按 PDF 技能的创建与验证要求处理最终文件：在首次创建前登记 artifact 操作，使用 Poppler 渲染首页、中间页和末页，目视确认非空白、方向正确、顺序连续、文字与图表清晰。
7. 最终答复给出批准号、页数和 PDF 文件引用。

## 约束

- 仅下载网站公开提供且检索结果标记有结题报告的内容。
- 遇到登录、验证码、权限提示、无报告或接口结构变化时停止并说明具体阻塞；不得规避访问控制。
- 保留脚本的缓存目录直至 PDF 校验完成。下载中断后用相同参数重跑，脚本会跳过已完成页面。
- 默认输出名为 `国家自然科学基金结题报告_<批准号>.pdf`；不要用项目名称直接作为文件名，以免特殊字符或超长路径导致失败。
- `--insecure` 仅在本机证书链导致 TLS 校验失败、且站点主机仍为 `kd.nsfc.cn` 时使用。
