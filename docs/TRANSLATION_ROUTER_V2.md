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

本地验证日志保存在忽略目录 `tmp/`，不进入 Git 提交；原有测试日志保留。构建产物位于 `build/chrome` 和 `build/desktop/CharlieTranslate`。本次只提交当前开发分支，未推送、发布、覆盖现用程序或修改 upstream。

Chrome/Thorium 实机加载、实际语言模型可用性和新 EXE 运行验收仍待执行；上述自动化测试与产物回读不代表该实机发布门已通过。
