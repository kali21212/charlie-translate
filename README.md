# Charlie Translate｜查理翻译

以本机翻译和隐私保护为重点的网页双语、划词翻译扩展。新安装默认使用 **Charlie Translation Router V2**：优先浏览器本地 Translator API，不可用时回退 Charlie Desktop / MTranServer；云服务只在用户主动选择时使用。架构和迁移边界见 [Translation Router V2](docs/TRANSLATION_ROUTER_V2.md)。

## 功能

- 网页双语对照、划词翻译、鼠标悬停翻译和输入框翻译。
- YouTube 字幕翻译、站点规则和术语词典。
- 浏览器「截图翻译」：框选网页区域后自动本地 OCR 并翻译；截图只作为内存临时输入，不保存、不做通用标注，见[使用说明](docs/SCREENSHOT.md)。
- Charlie Translation Router V2、本地 MTranServer，以及用户主动选择的 OpenAI/GPT、Gemini、Claude 等云 AI 接口。
- 敏感页面的输入翻译与自动剪贴板读取保护。
- 保留上游同步路径，使用测试、依赖审计和 CI 验证修改。

## 桌面版：全局截图与增强 OCR

Windows x64 便携版支持全局框选、可移动悬浮截图按钮、截图标注、不可逆隐私 Redact、自动复制、增强 OCR 和英文到简体中文本机翻译。完整解压后双击 `CharlieTranslate.exe`，无需安装 Python、Node、MTranServer 或填写 Key。浏览器插件可直接共用 EXE 内置 OCR 与翻译服务。安装与使用详见[桌面版说明](docs/DESKTOP.md)。

## 安装和本机翻译

Charlie 当前以源码和本地 Chrome 构建交付。

1. 安装 Node.js 22 和 Corepack，运行 `corepack pnpm@10.15.1 install --frozen-lockfile`。
2. 运行 `corepack pnpm@10.15.1 build:chrome`。
3. 在 `chrome://extensions` 打开开发者模式，选择“加载已解压的扩展程序”，加载 `build/chrome`。
4. 默认翻译接口选择 **CharlieAuto**。浏览器运行时如果提供本地 `Translator` API，Charlie 直接使用浏览器管理的本地语言模型；某语言对不可用时才连接同机 `http://127.0.0.1:8992` 的 Charlie Desktop。
5. 因此支持 Translator API 的 Chrome/Chromium 环境可以不依赖 EXE 完成本地翻译；Thorium 等 Chromium fork 只做真实 capability detection，不按浏览器名称猜测。需要 Desktop fallback、增强 OCR 或桌面截图时打开 `CharlieTranslate.exe`。
6. 两级本地引擎都不可用时会明确报错，**不会自动把文本发送到 OpenAI/Gemini/Claude 等云端**。云 AI 需在“翻译接口”里主动启用并选择。
7. 需要自建 MTranServer 或其他接口时可显式配置；已有自定义 URL/Key 和具体网站规则不会被强制覆盖。

新安装默认只启用 CharlieAuto；在线词典/联想、远程规则注入、更新检查及自动剪贴板翻译仍保持 opt-in。OpenAI 等云端接口默认关闭，保留已有模型配置，用户可主动选择账户支持的模型。

## 隐私边界和验证

敏感 URL（含 hash 路由）、密码/OTP/命名密钥字段及开放 Shadow DOM 会阻止输入翻译；操作时重新检查页面跳转和新增字段。自动剪贴板读取前检查当前标签及可访问的所有 frame；检查失败或页面变化时停止。显式划词和网页文本翻译仍可使用，这些功能不对秘密内容做语义识别。

扩展继承上游 `<all_urls>` 和 scripting 等权限，用于跨网页翻译；`clipboardRead` 仍是可选权限。未添加遥测。主动启用云服务、同步或远程规则后会向对应服务发送数据。详见 [SECURITY.md](SECURITY.md)。

开发检查：`corepack pnpm@10.15.1 test:charlie`、`test:dependency-compatibility`、`audit:dependencies`、Chrome 构建和 `git diff --check`。剩余依赖问题见 [依赖审计](docs/DEPENDENCY_AUDIT.md)。

生产依赖审计必须为 **0 漏洞**，不允许运行时例外。React Router 已升级至修复版 7.18.4；完整依赖树剩余 11 项仅属开发/构建工具，仍需要后续工具链迁移。

有效 PR、Issue 和默认分支提交可形成 GitHub 贡献记录；数量不保证任何平台的额外权限或配额。源码继续按 GPL-3.0 分发，欢迎真实、可验证的贡献。

## 开发与贡献

问题反馈请提交到 [Charlie Issues](https://github.com/kali21212/charlie-translate/issues)。开发和提交规范见 [CONTRIBUTING.md](CONTRIBUTING.md)，版本改动见 [CHANGELOG.md](CHANGELOG.md)。

## 来源与许可证

Charlie Translate 基于 [KISS Translator 简约翻译](https://github.com/fishjar/kiss-translator)二次开发，感谢原作者及贡献者。源码按 [GNU GPL-3.0](LICENSE)分发，保留适用的上游版权、许可及免责声明；分发修改版时须履行对应源码等许可证义务。

上游基线、复用范围和同步流程见 [UPSTREAM.md](UPSTREAM.md)。本仓库首页介绍 Charlie 版本；上游完整说明可在原项目查看。
