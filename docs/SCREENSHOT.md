# 截图与翻译

Chrome 网页悬浮翻译按钮的菜单提供「截图与翻译」，打开后是可拖动、可关闭的工具窗。

1. 点击「框选截图」，拖动选择当前可见区域，松开完成；Esc 取消。
2. 检查预览，点击「复制截图」粘贴到聊天或文档；「保存截图」优先打开保存窗口，不支持时使用浏览器下载目录，无需翻译服务。
3. 选择英文、简体中文或混合识字，点击「本地识字」。结果可以编辑；小字、孤立文字和复杂背景可能漏识别。
4. 检查原文，选择已启用的接口和目标语言，再点击「翻译」。支持复制原文或译文。

OCR 引擎和模型随 Chrome 构建打包，使用时不从 CDN 下载或上传截图。只有点击「翻译」才将文字交给所选接口。MTranServer 必须单独启动，默认 URL `http://localhost:8989/kiss`，未设置服务 Token 时 Key 留空；选择云接口会发送文字至该服务。

仅支持普通 HTTP/HTTPS 网页的当前可见区域，不支持整桌面、滚动长截图、浏览器内部页面或其他应用。敏感 URL、密码/OTP/密钥字段或无法完成检查的页面禁止截图。导航、缩放、滚动、目标窗口或活动标签变化会丢弃截图。这些检查不能识别图片中所有秘密，保存或翻译前请检查内容。

更新本地版本后，重新加载扩展并刷新网页。工具无译文时先确认 MTranServer 正在运行；「翻译已开启」只是开关状态。

## 开发与来源

复用结论 C：只复用 Tesseract.js OCR，不复制完整扩展。检查了 Tesseract.js（Apache-2.0，浏览器识字）、Scribe.js（AGPL-3.0，文档处理范围更大）和 ocr-it（MIT，独立扩展）；后两者不并入代码。检查了 Tesseract.js 最近提交、发布和未解决的 SIMD/模型、大图片问题。这里固定已验证的 6.0.1 和普通 LSTM 核心，限制面积、运行时间和并发，不使用 relaxed-SIMD。

`pnpm-lock.yaml` 固定引擎包及完整性，`ocr-assets.json` 固定 tessdata_fast 源提交与 SHA-256。构建逐项验签，产物 `ocr/` 保留引擎、核心、模型许可证及来源。WASM 来自官方 npm 编译产物，未宣称全面审计引擎。源码：[Tesseract.js](https://github.com/naptha/tesseract.js)、[core](https://github.com/naptha/tesseract.js-core)、[tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast)。

`test:charlie` 覆盖缩放裁剪、标签切换、导航丢弃、敏感字段和菜单通道。`test:screenshot-ocr` 使用本地中英文图片运行真实 OCR。浏览器验收另验证框选、WASM、下载和真实翻译。

浮窗属于网页中的工具界面，页面脚本可能读取其中显示的图片与文字，因此仅用于普通页面和可展示内容。OCR 在仅扩展可访问的 offscreen 页面运行，用完关闭；新增 offscreen 权限只提供本地 DOM/Worker，不上传图片。

新增 downloads 权限用于主动保存 PNG；代码不读取下载历史。

部分内置浏览器会取消扩展下载或不提供保存窗口，此时使用复制截图；不得把取消反馈当作保存成功。
