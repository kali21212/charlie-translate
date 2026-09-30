# Charlie Translate｜查理翻译

以本机翻译和隐私保护为重点的网页双语、划词翻译扩展。新安装默认使用本地 MTranServer，云服务需要主动启用，已有设置会保留。

## 功能

- 网页双语对照、划词翻译、鼠标悬停翻译和输入框翻译。
- YouTube 字幕翻译、站点规则和术语词典。
- 网页框选截图、保存 PNG、本地中英文 OCR 和截图文字翻译，见[使用说明](docs/SCREENSHOT.md)。
- 本地 MTranServer 接口，以及可选的云翻译和 AI 接口。
- 敏感页面的输入翻译与自动剪贴板读取保护。
- 保留上游同步路径，使用测试、依赖审计和 CI 验证修改。

## 安装和本机翻译

Charlie 当前以源码和本地 Chrome 构建交付。

1. 安装 Node.js 22 和 Corepack，运行 `corepack pnpm@10.15.1 install --frozen-lockfile`。
2. 运行 `corepack pnpm@10.15.1 build:chrome`。
3. 在 `chrome://extensions` 打开开发者模式，选择“加载已解压的扩展程序”，加载 `build/chrome`。
4. 按 [MTranServer 官方文档](https://github.com/xxnuo/MTranServer)安装独立服务，绑定 `127.0.0.1`，默认端口 `8989`。扩展不内置或自动安装该服务及模型。
5. 在翻译接口设置中选择 **MTranServer**，URL 为 `http://localhost:8989/kiss`。如服务配置了 `MT_API_TOKEN`，在 Key 中填写相同值。也支持 `127.0.0.1` 和 IPv6 回环地址；远程服务器需要显式选择 Custom。
6. 打开普通网页，使用 `Alt+Q` 网页翻译或选中文字后翻译。服务不可用时显示错误，不自动切换到云服务。

首次使用通常需要下载模型；预加载后，按服务文档启用 `MT_OFFLINE=true` 可离线工作。服务安装、模型质量和浏览器内效果需在目标浏览器另行验收；CI 验证客户端协议、行为和构建。

新安装默认关闭云翻译接口、在线词典/联想、远程规则注入、更新检查及自动剪贴板翻译。Chrome 内置翻译模型的可用性取决于浏览器，可手动选择。已有云服务、同步及其他配置不会被强制覆盖。

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
