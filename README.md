# 国家自然科学基金结题报告下载 Skill

用于按项目批准号或项目名称检索国家自然科学基金公开结题报告，并将网站提供的逐页图片自动合成为 PDF。

## 功能

- 按批准号或完整项目名称检索
- 识别重名项目和未公开报告
- 自动探测报告总页数
- 并发下载、503 重试和断点续传
- 合并为 PDF 并校验页数
- 不绕过登录、验证码或访问权限

## 安装

将本仓库克隆到 Codex 的个人 Skills 目录：

```powershell
git clone https://github.com/<your-account>/nsfc-final-report-download.git `
  "$env:CODEX_HOME\skills\nsfc-final-report-download"
```

如果没有设置 `CODEX_HOME`，默认目录通常是 `$HOME\.codex\skills`。

## 在 Codex 中使用

```text
使用 $nsfc-final-report-download 下载项目 U1806228 的结题报告
```

也可以提供完整项目名称：

```text
使用 $nsfc-final-report-download 下载“基于海底地形特征的深海AUV同步定位与建图方法研究”的结题报告
```

## 直接运行脚本

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

按批准号下载：

```powershell
python scripts/download_report.py --grant-number U1806228
```

按项目名称下载：

```powershell
python scripts/download_report.py --title "基于海底地形特征的深海AUV同步定位与建图方法研究"
```

默认 PDF 输出到 `output/pdf/`，页面缓存保存到 `tmp/pdfs/nsfc-report-pages/`。中断后使用相同参数重新运行即可续传。

## 说明

本项目仅处理 `kd.nsfc.cn` 已公开提供的结题报告。网站接口或页面格式发生变化时，脚本可能需要更新。

