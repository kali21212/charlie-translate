import { createRoot } from "react-dom/client";
import Screenshot from "../views/Screenshot";
import { screenshotStyles } from "../views/Screenshot/styles";
import browser from "webextension-polyfill";
import { normalizeRegion } from "./screenshotGeometry";
import { isSensitivePage } from "./securityGuard";
import {
  SCREENSHOT_SELECT,
  SCREENSHOT_VERIFY,
  SCREENSHOT_SHOW,
} from "./screenshotCapture";

let host;
let selectionBusy = false;
const token =
  globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
const snapshot = () => ({
  token,
  href: window.location.href,
  width: window.innerWidth,
  height: window.innerHeight,
  scrollX: window.scrollX,
  scrollY: window.scrollY,
  scale: window.visualViewport?.scale || 1,
});
const unchanged = (before) => {
  const now = snapshot();
  return (
    before &&
    Object.keys(now).every((key) => before[key] === now[key]) &&
    !isSensitivePage(window.location.href, document)
  );
};

export function openScreenshotTools() {
  if (window !== window.top || !/^https?:$/.test(window.location.protocol))
    return;
  if (host?.isConnected) {
    host.style.display = "block";
    return;
  }
  host = document.createElement("div");
  host.style.cssText =
    "all:initial;position:fixed;right:18px;bottom:18px;width:min(440px,94vw);height:min(650px,90vh);z-index:2147483646;display:block";
  const root = host.attachShadow({ mode: "open" });
  const body = document.createElement("div");
  body.style.cssText =
    "height:calc(100% - 36px);overflow:auto;background:#f6f8fc;color:#183153;font:14px system-ui,sans-serif;border-radius:0 0 14px 14px";
  const style = document.createElement("style");
  style.textContent = screenshotStyles;
  const reactRoot = createRoot(body);
  reactRoot.render(<Screenshot />);
  const header = document.createElement("div");
  header.style.cssText =
    "height:36px;display:flex;align-items:center;justify-content:space-between;padding:0 12px;background:#183153;color:white;font:14px sans-serif;border-radius:14px 14px 0 0;cursor:move;touch-action:none";
  header.textContent = "Charlie · 截图与翻译";
  const close = document.createElement("button");
  close.textContent = "关闭";
  close.onclick = () => {
    reactRoot.unmount();
    host.remove();
    host = null;
  };
  header.append(close);
  header.onpointerdown = (event) => {
    if (event.target === close) return;
    const box = host.getBoundingClientRect();
    const start = { x: event.clientX, y: event.clientY };
    header.setPointerCapture(event.pointerId);
    header.onpointermove = (move) => {
      host.style.right = "auto";
      host.style.bottom = "auto";
      host.style.left = `${Math.max(0, Math.min(window.innerWidth - box.width, box.left + move.clientX - start.x))}px`;
      host.style.top = `${Math.max(0, Math.min(window.innerHeight - box.height, box.top + move.clientY - start.y))}px`;
    };
    header.onpointerup = header.onpointercancel = () => {
      header.onpointermove = null;
    };
  };
  root.append(style, header, body);
  document.documentElement.append(host);
}

async function selectRegion() {
  if (selectionBusy) throw new Error("正在框选，请先完成或取消");
  if (isSensitivePage(window.location.href, document))
    throw new Error("敏感页面已禁止截图，请在普通网页使用");
  selectionBusy = true;
  if (host) host.style.display = "none";
  const before = snapshot();
  const overlay = document.createElement("div");
  overlay.style.cssText =
    "position:fixed;inset:0;z-index:2147483647;cursor:crosshair;background:rgba(0,0,0,.16);touch-action:none";
  const shadow = overlay.attachShadow({ mode: "closed" });
  const box = document.createElement("div");
  box.style.cssText =
    "position:absolute;border:2px solid #66baff;box-sizing:border-box;background:transparent;pointer-events:none";
  const hint = document.createElement("div");
  hint.textContent = "拖动框选截图区域 · Esc 取消";
  hint.style.cssText =
    "position:absolute;top:16px;left:16px;background:#183153;color:white;padding:10px;border-radius:8px;font:14px sans-serif;pointer-events:none";
  shadow.append(box, hint);
  document.documentElement.append(overlay);
  return new Promise((resolve, reject) => {
    let start;
    let timer;
    const finish = (error, region) => {
      clearTimeout(timer);
      document.removeEventListener("keydown", escape, true);
      overlay.remove();
      selectionBusy = false;
      if (error) reject(error);
      else
        requestAnimationFrame(() =>
          requestAnimationFrame(() => resolve({ ...before, region }))
        );
    };
    const escape = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        finish(new Error("已取消截图"));
      }
    };
    document.addEventListener("keydown", escape, true);
    timer = setTimeout(() => finish(new Error("框选超时，请重试")), 60000);
    overlay.onpointerdown = (event) => {
      if (event.button !== 0 || !event.isTrusted) return;
      event.preventDefault();
      event.stopPropagation();
      start = { x: event.clientX, y: event.clientY };
      overlay.setPointerCapture(event.pointerId);
    };
    overlay.onpointermove = (event) => {
      if (!start) return;
      const region = normalizeRegion(
        start,
        { x: event.clientX, y: event.clientY },
        before.width,
        before.height
      );
      Object.assign(box.style, {
        left: `${region.x}px`,
        top: `${region.y}px`,
        width: `${region.width}px`,
        height: `${region.height}px`,
      });
    };
    overlay.onpointerup = (event) => {
      if (!start || !event.isTrusted) return;
      const region = normalizeRegion(
        start,
        { x: event.clientX, y: event.clientY },
        before.width,
        before.height
      );
      finish(
        !unchanged(before) || region.width < 4 || region.height < 4
          ? new Error("区域过小或页面已变化，请重新框选")
          : null,
        region
      );
    };
    overlay.onpointercancel = () => finish(new Error("已取消截图"));
  });
}

export function installScreenshotTools() {
  if (window !== window.top || !/^https?:$/.test(window.location.protocol))
    return;
  browser.runtime.onMessage.addListener((message, sender) => {
    if (sender.id !== browser.runtime.id) return undefined;
    if (message.action === "charlieScreenshotOpen") {
      openScreenshotTools();
      return Promise.resolve(true);
    }
    if (message.action === SCREENSHOT_SELECT) return selectRegion();
    if (message.action === SCREENSHOT_VERIFY)
      return Promise.resolve(unchanged(message.args));
    if (message.action === SCREENSHOT_SHOW) {
      if (host) host.style.display = "block";
      return Promise.resolve(true);
    }
    return undefined;
  });
}
