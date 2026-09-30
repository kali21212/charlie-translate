import { run } from "./common";
import { isScreenshotSupported } from "./libs/client";
import { installScreenshotTools } from "./libs/screenshotTools";

// 标记全局运行上下文为 "content"，辅助 getContext() 判断运行宿主
globalThis.__KISS_CONTEXT__ = "content";

// 启动通用翻译器前端业务逻辑
run();
if (isScreenshotSupported) installScreenshotTools();
