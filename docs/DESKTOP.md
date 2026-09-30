# Charlie Translate 桌面版

Windows x64 便携版。解压整个文件夹，双击 `CharlieTranslate.exe`，无需另装 Python、Node 或填写 Key。不要只复制 EXE：`_internal`、`models`、`translation` 是必需资源。

1. 等待「增强 OCR 就绪」。点击「框选截图」或按 **Ctrl+Alt+Q**，拖动选择桌面或其他软件上的区域；Esc / 右键取消。
2. 检查截图预览，点击「增强识字」。可以编辑原文、复制文字；识字不自动翻译。
3. 点击「翻译为中文（本机）」，程序自动启动自带的离线 MTranServer，只将原文发送到 `127.0.0.1:8991`。当前便携包包含英文到简体中文模型。
4. 「保存截图」只保存到主动选择的位置；「复制截图」写入系统剪贴板。「清空」删除界面中的图片和文字，没有截图历史。
5. 保持桌面版开启，更新后的浏览器扩展可以共用 `127.0.0.1:8990` 的增强 OCR。关闭桌面版会关闭它自己启动的服务；不会关闭其他窗口的服务。快捷键占用时仍可点击按钮截图。

## 隐私与边界

桌面截图、打开的图片、OCR 推理在本机内存中完成。截图不交给 MTranServer；翻译只发送文字。没有云 OCR、云翻译、遥测、更新检查、运行时模型下载或开机自启动。Python 运行时拒绝外部网络连接和 DNS；翻译子进程使用离线模式及禁止外部连接的启动模块。

浏览器 OCR 接口只绑定回环地址，拒绝网页 Origin、表单请求、跨域预检和异常 Host，不提供任意文件、命令或 URL 接口。它仍信任本机进程和已安装扩展，不是隔离其他恶意本机软件的安全边界。

桌面程序无法判断每张截图是否含密码、账户或其他秘密，框选后请先检查预览。系统剪贴板可能被其他软件或 Windows 剪贴板同步读取；只有主动点击复制才写入。系统保护的窗口可能返回黑图。OCR 提取文字，不解释图标。

## 开发与复现

复用结论 C：RapidOCR 3.9.2（Apache-2.0）＋ PP-OCRv5 server ONNX 模型；Pillow（MIT-CMU）用于本机截图。比较 Umi-OCR（MIT，整套 Qt/QML，存在待处理的本地接口安全报告）、NormCap（GPL-3.0-or-later，主要 Tesseract 截图识字）后，不复制整套应用。桌面界面使用 Python 标准库 Tk，沿用 Charlie 项目 GPL-3.0。

Python 3.12 Windows x64：安装 `services/ocr/requirements.lock` 固定且校验哈希的 wheel 依赖，构建工具 PyInstaller 6.22.3；模型地址和 SHA-256 在 `services/ocr/models.json`，只在准备阶段下载。Node 二进制由 `desktop/node-runtime.json` 校验；MTranServer 4.0.33 和完整依赖由 `desktop/mtran-lock.json` 固定。

准备模型到 `tmp/rapid-models`，翻译资源到 `tmp/desktop-translation`、`tmp/mtran-models`，再运行 `python desktop/build.py`。输出 `build/desktop/CharlieTranslate`，包含许可证、源码、使用说明和 `FILES.json` 校验清单。正式发布需记录对应 Git 提交及压缩包 SHA-256。

MTranServer 源码 Apache-2.0；Firefox 翻译模型与 Bergamot 引擎涉及 MPL-2.0，保留原许可证和来源。模型与第三方代码没有改写为我们的版权。来源见 `UPSTREAM.md` 与随包 `licenses/`。
