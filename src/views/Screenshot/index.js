import { useEffect, useRef, useState } from "react";
import browser from "webextension-polyfill";
import { bitmapRegion } from "../../libs/screenshotGeometry";
import { SCREENSHOT_CAPTURE } from "../../libs/screenshotCapture";
import { getSettingWithDefault } from "../../libs/storage";
import { handleTranslate } from "../../apis/trans";
import {
  OPT_LANGS_TO,
  OPT_LANGS_FROM_SPEC,
  OPT_LANGS_TO_SPEC,
} from "../../config";

export async function cropScreenshot(capture) {
  const image = new Image();
  image.src = capture.image;
  await image.decode();
  const crop = bitmapRegion(capture.region, capture, {
    width: image.naturalWidth,
    height: image.naturalHeight,
  });
  const canvas = document.createElement("canvas");
  canvas.width = crop.width;
  canvas.height = crop.height;
  canvas.getContext("2d").drawImage(
    image,
    crop.x,
    crop.y,
    crop.width,
    crop.height,
    0,
    0,
    crop.width,
    crop.height
  );
  return canvas.toDataURL("image/png");
}

export default function Screenshot() {
  const [text, setText] = useState("");
  const [translation, setTranslation] = useState("");
  const [status, setStatus] = useState("框选网页区域后自动 OCR 并翻译；截图只作为临时输入。");
  const [busy, setBusy] = useState(false);
  const [apis, setApis] = useState([]);
  const [slug, setSlug] = useState("");
  const [to, setTo] = useState("zh-CN");
  const ocrRef = useRef(null);
  const abortRef = useRef(null);
  const jobRef = useRef(0);
  useEffect(() => {
    let alive = true;
    const jobs = jobRef;
    getSettingWithDefault()
      .then((setting) => {
        if (!alive) return;
        const enabled = setting.transApis.filter((api) => !api.isDisabled);
        setApis(enabled);
        setSlug(
          enabled.find((api) => api.apiSlug === setting.tranboxSetting.apiSlugs[0])?.apiSlug ||
            enabled.find((api) => api.apiType === "MTranServer")?.apiSlug ||
            enabled[0]?.apiSlug ||
            ""
        );
        setTo(setting.tranboxSetting.toLang || "zh-CN");
      })
      .catch((error) => alive && setStatus(error.message));
    return () => {
      alive = false;
      jobs.current++;
      abortRef.current?.abort();
      if (ocrRef.current) {
        browser.runtime
          .sendMessage({
            action: "charlieScreenshotOcrCancel",
            args: { job: ocrRef.current },
          })
          .catch(() => undefined);
      }
    };
  }, []);

  const stop = () => {
    jobRef.current++;
    abortRef.current?.abort();
    if (ocrRef.current) {
      browser.runtime
        .sendMessage({
          action: "charlieScreenshotOcrCancel",
          args: { job: ocrRef.current },
        })
        .catch(() => undefined);
    }
    ocrRef.current = null;
    setBusy(false);
    setStatus("已停止，可重新截图翻译。");
  };
  const translateText = async (source, job) => {
    const api = apis.find((item) => item.apiSlug === slug);
    if (!api) throw new Error("没有可用翻译接口");
    if (!source.trim()) throw new Error("未识别到文字");
    if (source.length > 12000) throw new Error("文字过长，请缩小截图范围");
    const controller = new AbortController();
    abortRef.current = controller;
    let translated = "";
    setStatus(`正在使用 ${api.apiName} 翻译…`);
    for await (const chunk of handleTranslate([source], {
      from: OPT_LANGS_FROM_SPEC[api.apiType]?.get("auto") ?? "auto",
      to: OPT_LANGS_TO_SPEC[api.apiType]?.get(to) ?? to,
      fromLang: "auto",
      toLang: to,
      apiSetting: { ...api, useStream: false, useContext: false },
      usePool: false,
      signal: controller.signal,
    })) {
      if (job !== jobRef.current) return "";
      translated = Array.isArray(chunk.result)
        ? chunk.result[0]
        : chunk.result || chunk.partialText || "";
      setTranslation(translated);
    }
    return translated;
  };

  const screenshotTranslate = async () => {
    if (busy || !slug) return;
    const job = ++jobRef.current;
    setBusy(true);
    setText("");
    setTranslation("");
    try {
      setStatus("拖动框选需要翻译的网页区域，Esc 取消。");
      const capture = await browser.runtime.sendMessage({ action: SCREENSHOT_CAPTURE });
      const image = await cropScreenshot(capture);
      if (job !== jobRef.current) return;
      setStatus("正在本机 OCR…");
      const request = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
      ocrRef.current = request;
      const result = await browser.runtime.sendMessage({
        action: "charlieScreenshotOcr",
        args: { image, job: request },
      });
      ocrRef.current = null;
      if (job !== jobRef.current) return;
      if (result.error) throw new Error(result.error);
      const source = result.text.trim();
      setText(source);
      if (!source) {
        setStatus("未识别到文字，请重新框选更清晰的区域。");
        return;
      }
      const translated = await translateText(source, job);
      if (job === jobRef.current && translated) {
        setStatus("截图翻译完成。截图未保存，也不会进入图片编辑流程。");
      }
    } catch (error) {
      if (job === jobRef.current) {
        const canceled =
          error.name === "AbortError" || /取消|USER_CANCELED/.test(String(error.message || error));
        setStatus(canceled ? "截图翻译已取消。" : `操作失败：${error.message || error}。`);
      }
    } finally {
      if (job === jobRef.current) setBusy(false);
    }
  };

  const copy = async (value) => {
    try {
      await navigator.clipboard.writeText(value);
      setStatus("文字已复制。");
    } catch (_error) {
      setStatus("复制失败，请在文字框内手动选择并复制。");
    }
  };
  return (
    <main>
      <div className="actions">
        <button disabled={busy || !slug} onClick={screenshotTranslate}>
          截图翻译
        </button>
        {busy && <button onClick={stop}>停止</button>}
      </div>
      <p role="status">{status}</p>
      <p className="note">
        浏览器版只负责翻译：框选 → 本地 OCR → 自动翻译 → 出结果。
        截图只在内存中作为临时 OCR 输入，不提供保存、复制图片或标注功能。
      </p>
      <label>
        翻译接口
        <select disabled={busy} value={slug} onChange={(event) => setSlug(event.target.value)}>
          {apis.map((api) => (
            <option key={api.apiSlug} value={api.apiSlug}>
              {api.apiName}
            </option>
          ))}
        </select>
      </label>
      <label>
        目标语言
        <select disabled={busy} value={to} onChange={(event) => setTo(event.target.value)}>
          {OPT_LANGS_TO.map(([code, name]) => (
            <option key={code} value={code}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <label>
        OCR 原文
        <textarea value={text} readOnly placeholder="截图 OCR 后显示原文" />
      </label>
      <div className="actions">
        <button disabled={!text} onClick={() => copy(text)}>复制原文</button>
      </div>
      <label>
        译文
        <textarea value={translation} readOnly placeholder="翻译结果" />
      </label>
      <div className="actions">
        <button disabled={!translation} onClick={() => copy(translation)}>复制译文</button>
      </div>
    </main>
  );
}
