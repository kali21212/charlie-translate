# Charlie Translation Router V2

## 目标

Translation Router V2 把 Charlie Translate 的翻译能力分成“本地自动路由”和“用户主动选择的云端 AI”两条边界，避免浏览器在本地引擎不可用时静默把文本发送到互联网。

复用结论：**C｜模块复用**。V2 复用 Charlie 已有的 Chrome/Chromium Translator API 适配器、Desktop MTranServer 桥、OpenAI/Gemini/Claude 等 Provider 框架；不引入新的大型本地模型运行时。

## 默认路由

新安装和由旧默认配置迁移的用户使用 `CharlieAuto`：

```text
CharlieAuto
  │
  ├─ 1. 浏览器 Translator API 可用
  │      └─ 本地设备模型
  │
  └─ 2. 不可用/当前语言对失败
         └─ 127.0.0.1:8992
             Charlie Desktop
               └─ 内置 MTranServer / Mozilla 模型
```

路由使用**能力检测**，不根据 Chrome、Thorium 等浏览器名称猜测。浏览器没有 `Translator` 能力时直接进入 Desktop fallback。

### 隐私不变量

`CharlieAuto` **永远不自动回退到 OpenAI、Gemini、Claude、DeepSeek 或其他云端接口**。本地两级都失败时返回明确错误，由用户决定是否主动选择云服务。

此限制也覆盖辅助语言检测：浏览器 LanguageDetector 失败时，CharlieAuto 直接进入 Desktop，不调用已配置的远程语言检测服务。Desktop 回退使用固定的无 Key 本机预设，不继承用户另设的 MTran 地址、Token 或请求钩子。取消翻译后不启动下一级回退。

旧版全局默认 MTranServer 在一次性迁移中切到 `CharlieAuto`；针对具体网站显式保存的 MTranServer 规则保持不变。

## 浏览器内置 Translator API

Charlie 直接在扩展的文档/content context 调用 `LanguageDetector` / `Translator`。Manifest V3 background 是 Service Worker，不承担 Translator 推理。

浏览器可能需要首次下载语言对模型。是否支持某个语言对，以运行时 `availability()` 为准。

## Desktop fallback

Desktop 继续提供：

- `127.0.0.1:8990`：PP-OCRv5
- `127.0.0.1:8992`：Charlie 翻译桥
- Desktop 内部 `127.0.0.1:8991`：MTranServer 子进程

浏览器只连接回环地址。8992 桥不会暴露 Desktop 内部随机 Token，也不允许远程 MTran URL 偷偷替代本机服务。

当前 Desktop 内置翻译包仍是 Mozilla/Firefox Translations 的 en → zh-Hans v3.0 模型。模型与 MTranServer 继续使用固定版本和校验值，运行期不静默下载替换。

## 云端 AI

OpenAI、Gemini、Claude、DeepSeek、OpenRouter 等已有 Provider 继续保留，但默认不启用。用户必须在“翻译接口”中主动启用并选择。

OpenAI 预设保留已有官方 API 地址、模型列表接口和 `gpt-4` 模型配置；用户可从自己的账户可用模型中主动选择。Codex 应用内模型名称不作为公共 API 模型预设。

当前版本的云 API Key 仍由浏览器扩展设置保存，并在设置界面失焦后遮蔽显示。**V2 不宣称 Key 已迁移到 Windows Credential Manager/DPAPI。** 如果后续增加 Desktop Secret Vault，应作为独立安全升级实施和验收。

## 高质量本地模型

V2 **不捆绑** CTranslate2、OPUS-MT、MADLAD-400 或数 GB 模型。原因：

- 当前网页翻译优先目标是低资源、低延迟；
- MADLAD-400 3B 属于数 GB 级，默认安装收益不足以覆盖磁盘、RAM 和启动成本；
- OPUS-MT/CTranslate2 可作为以后可选下载模块单独 benchmark。

因此本版只预留“高质量本地”扩展位，不扩大默认安装包。

## 配置迁移

Translation Router V2 迁移：

- 添加 `CharlieAuto` Provider；
- 旧默认 input/selection/subtitle 的单一 MTranServer 选择迁移到 `CharlieAuto`；
- 旧全局 `*` 规则如果仍是默认 MTranServer，迁移到 `CharlieAuto`；
- 具体网站显式 MTranServer 规则不改；
- 旧 8989 无 Key 本机 MTran URL 继续迁移到 Desktop 8992；
- 用户显式启用的云 Provider、Key、自定义 URL、排序等保留。

迁移仅替换使用已知默认本机地址且无 Key 的 MTranServer 选择。显式自定义地址或带 Token 的 MTranServer 选择保持原样。设置与全局规则在同一存储锁内读取并提交；任一写入失败时回滚，重试不会重复迁移。

## 验收门

发布前必须通过：

1. Browser Translator 优先成功路径；
2. Browser Translator 失败 → Desktop MTran fallback；
3. 两级本地均失败时确认没有云端请求；
4. 配置/规则迁移保持显式用户选择；
5. Desktop OCR/Redact/截图回归；
6. 完整浏览器测试、dependency compatibility、dependency audit、Chrome build；
7. Desktop build 与便携包 readback；
8. Thorium/Chrome 实机 capability detection，不以浏览器名称推断。

## 本次源码收口验证（2026-10-01）

本次从 `feat/translation-router-v2-20261001` 的 `dbb86090f15e0d87d16e8b1da9e37a59c8c61d48` 及其未提交改动续做，版本为 **2.3.0**（Translation Router V2）。复用现有模块，没有重新引入外部代码或新增模型依赖。

| 检查 | 结果 |
| --- | --- |
| `test:charlie` | 27 套件、667 项通过，含本地路由、取消、无远程语言检测、迁移保留及回滚 |
| dependency compatibility | 真实 WebDAV XML、URI 解码、selector parser 检查通过 |
| dependency audit | prod 0；全量 11 项既有构建/开发期例外（3 high、8 moderate），未新增运行期例外 |
| Chrome build | 固定 pnpm 10.15.1 构建通过；产物 Manifest 与源码版本一致 |
| Desktop tests | 29 项通过；原先跳过的真实中英文 OCR 项另行启用固定模型后通过，共 30 项 |
| Desktop build / readback | 便携目录构建通过；3,375 个文件大小及 SHA-256、31 个源码文件和使用说明逐项回读通过 |
| Windows version updater | 同版本 `version:set -- 2.3.0` 通过，确认所有 Manifest 和 `.env` 一致 |
| 自审复审 | 修复后台残留引用、间接远程检测、自定义 MTran 选择和迁移原子性问题；新增内容密钥模式扫描与 `git diff --check` 通过 |

本地验证日志保存在忽略目录 `tmp/`，不进入 Git 提交；原有测试日志保留。构建产物位于 `build/chrome` 和 `build/desktop/CharlieTranslate`。上述“源码收口验证”阶段当时只提交当前开发分支，尚未推送、发布、覆盖现用程序或修改 upstream；后续实机部署结果见下一节。

## V2.3.0 实机发布验收（2026-10-01）

本轮在不修改源码的前提下，对提交 `4eca67a20dad884b41740d2a54d6e7d7f6cc45de` 的构建产物完成 Windows / Thorium 实机验收，并将通过验收的产物部署到 `D:\f`。现用浏览器会话未被强制重启。

| 实机检查 | 结果 |
| --- | --- |
| Windows Desktop | 新构建 EXE 启动通过；悬浮入口可见；8990/8992 由 EXE 启动，首次翻译后 8991 子进程按需启动 |
| Desktop 翻译 | 8992 `/health` 通过；真实 en → zh-Hans 翻译通过 |
| Desktop OCR | 8990 PP-OCRv5 health 通过；生成的真实 PNG 文本 `HELLO 2026 LOCAL OCR` 被准确识别 |
| 回环安全边界 | 8990/8991/8992 仅监听 `127.0.0.1`；缺少 Charlie header 或伪造普通网页 Origin 的访问均返回 403 |
| Thorium 152 | 独立实机 Profile 成功加载 V2.3.0；扩展上下文暴露 `Translator` / `LanguageDetector` |
| Thorium 本地模型 | en → zh-Hans 首次状态为 `downloadable`；在真实用户手势条件下完成浏览器本地模型下载并成功翻译 |
| CharlieAuto Fresh State | 新 Profile 中 input / selection / subtitle 全部为 `CharlieAuto`，且唯一默认启用 Provider 为 CharlieAuto |
| Desktop fallback | Thorium 扩展上下文访问 Desktop 8992 返回 200；浏览器本地能力与 Desktop fallback 同时可见 |
| Chrome 154 手工 UI 加载 | 在隔离 Profile 的 `chrome://extensions` 开启开发者模式并通过“加载未打包的扩展程序”选择 `build/chrome`；重启后 Service Worker、Options 与网页 Content Script 均正常加载 |
| Chrome 154 浏览器本地路由 | Desktop 完全关闭时，扩展上下文 `Translator` / `LanguageDetector` 均为 `available`；真实网页通过 CharlieAuto 完成 en → zh-CN 双语插入，未要求 EXE |
| Chrome 154 Desktop fallback | 以启动参数禁用 `TranslationAPI,LanguageDetectionAPI` 后，扩展确认两项能力为 `undefined`；开启已部署 EXE 后，同一网页仍通过 CharlieAuto 完成翻译，证明 8992 fallback 生效 |
| 双本地失败 / 零云回退 | 清空翻译缓存、使用全新未缓存文本、禁用浏览器 Translator 且关闭 Desktop；Service Worker 只尝试 `http://127.0.0.1:8992/kiss` 并收到 `ERR_CONNECTION_REFUSED`，没有任何 OpenAI / Gemini / Claude / Google Translate 等远程请求；页面日志明确提示“不会自动切换到云端” |
| 部署回读 | `D:\f\Charlie-Translate-Desktop-V1\CharlieTranslate.exe` SHA-256 与构建产物完全一致；浏览器目录 Manifest 为 2.3.0 / MV3 |
| 部署后运行 | 从 `D:\f` 启动的新 EXE 再次完成 OCR health、真实本地翻译及 8990/8991/8992 回环监听验收 |
| 隐私扫描 | 发布扩展中未发现本机构建路径、项目源码路径或私人身份标识字符串 |

实机部署验收阶段的 EXE SHA-256 为 `E584014E0065CBA39A569823DD6116E5E5CBC4C75A6CA5107DFB54E65952BDDF`。该值用于记录当时 `D:\f` staging/deployment 验收证据，不再作为 GitHub Release 资产的长期权威校验值。

正式 Release 的资产校验以该 Release 附带的 `SHA256SUMS.txt` 为准；Windows 便携包内的 `SOURCE.txt` 固定记录其对应的 Git exact-head，避免文档哈希与后续可重复构建形成循环依赖。

部署前旧版本以目录重命名方式保留为一次性 rollback：

- `D:\f\Charlie-Translate-Desktop-V1-pre-v2.3.0-20261001-105652`
- `D:\f\Charlie-Translate-V1-chrome-router-fixed-pre-v2.3.0-20261001-105652`

Google Chrome 154 的命令行 `--load-extension` 在本机未可靠激活 Charlie，因此不把该快捷路径当作有效验收依据。随后已改用真实 `chrome://extensions` 开发者模式 UI 手工加载 `build/chrome`，并在浏览器重启后完成 Service Worker、Options、网页翻译、浏览器本地模型、Desktop fallback 及双本地失败零云回退的完整实机链路验证。

当前结论：**V2.3.0 RELEASED / POST_RELEASE_READBACK_PASS**。功能主线已合并，便携包 `SOURCE.txt` provenance 已固定，发布前与最终 `main` exact-head CI 均通过。

## V2.3.0 正式发布回读（2026-10-01）

- Git tag：`v2.3.0` → `9ad401b0bb400f5c9428798f2352e9ae3e53b0c7`
- GitHub Release：`Charlie Translate v2.3.0 - Translation Router V2`
- Release source commit：`9ad401b0bb400f5c9428798f2352e9ae3e53b0c7`
- Final Windows EXE SHA-256：`225D8431D753FA69F587621FF39266C9F32311328A2E046EF0008ACB929FDD4B`
- Desktop ZIP SHA-256：`1f11d122c10f4bcdc4909ebbb049221f90442638d3cadd17a30aa6a0481f120c`
- Extension ZIP SHA-256：`b11887a316396e0681ca0fa4ee50908750e1d2891f10ecc0ee0822e48a3eb8e2`
- GitHub Release asset digest 与本地 `SHA256SUMS.txt` 一致；发布包内 `SOURCE.txt` 回读指向同一 source commit。
- 最终 Windows 便携构建使用 Python 3.12.10 / PyInstaller 6.22.3 重新生成并完成文件清单哈希、真实本地翻译、PP-OCRv5、8990/8991/8992 loopback 与正常退出后端口关闭复验。

`v2.3.0` tag 保持指向发布源代码提交；后续仅文档类 post-release closeout 可以位于 tag 之后的 `main`，不得改写已经发布的 tag。
