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
  canvas
    .getContext("2d")
    .drawImage(
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
  const [image, setImage] = useState("");
  const [text, setText] = useState("");
  const [translation, setTranslation] = useState("");
  const [status, setStatus] = useState(
    "框选当前网页，截图可保存；识字在本机完成。"
  );
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
          enabled.find(
            (api) => api.apiSlug === setting.tranboxSetting.apiSlugs[0]
          )?.apiSlug ||
            enabled.find((api) => api.apiType === "MTranServer")?.apiSlug ||
            enabled[0]?.apiSlug ||
            ""
        );
        setTo(setting.tranboxSetting.toLang || "zh-CN");
      })
      .catch((error) => {
        if (alive) setStatus(error.message);
      });
    return () => {
      alive = false;
      jobs.current++;
      abortRef.current?.abort();
      if (ocrRef.current)
        browser.runtime
          .sendMessage({
            action: "charlieScreenshotOcrCancel",
            args: { job: ocrRef.current },
          })
          .catch(() => undefined);
    };
  }, []);

  const cancel = () => {
    jobRef.current++;
    abortRef.current?.abort();
    if (ocrRef.current)
      browser.runtime
        .sendMessage({
          action: "charlieScreenshotOcrCancel",
          args: { job: ocrRef.current },
        })
        .catch(() => undefined);
    ocrRef.current = null;
    setBusy(false);
    setStatus("已停止，可重新操作。");
  };
  const run = async (work) => {
    if (busy) return;
    const job = ++jobRef.current;
    setBusy(true);
    try {
      await work(job);
    } catch (error) {
      if (job === jobRef.current)
        setStatus(
          error.name === "AbortError" ||
            /USER_CANCELED/.test(String(error.message || error))
            ? "保存已取消或浏览器未提供保存窗口，可使用复制截图。"
            : `操作失败：${error.message || error}。`
        );
    } finally {
      if (job === jobRef.current) setBusy(false);
    }
  };
  const capture = () =>
    run(async (job) => {
      setStatus("拖动框选网页区域，Esc 取消。");
      const result = await browser.runtime.sendMessage({
        action: SCREENSHOT_CAPTURE,
      });
      const png = await cropScreenshot(result);
      if (job !== jobRef.current) return;
      setImage(png);
      setText("");
      setTranslation("");
      setStatus("截图完成。可以保存图片，或点击本地识字。");
    });
  const imageBlob = () => {
    const bytes = Uint8Array.from(globalThis.atob(image.split(",")[1]), (ch) =>
      ch.charCodeAt(0)
    );
    return new Blob([bytes], { type: "image/png" });
  };
  const copyImage = () =>
    run(async () => {
      await navigator.clipboard.write([
        new globalThis.ClipboardItem({ "image/png": imageBlob() }),
      ]);
      setStatus("截图已复制，可粘贴到聊天、文档或图片编辑器。");
    });
  const save = () =>
    run(async () => {
      if (typeof window.showSaveFilePicker === "function") {
        const file = await window.showSaveFilePicker({
          suggestedName: "Charlie-screenshot.png",
          types: [
            { description: "PNG image", accept: { "image/png": [".png"] } },
          ],
        });
        const writer = await file.createWritable();
        await writer.write(imageBlob());
        await writer.close();
        setStatus("PNG 已保存。");
      } else {
        await browser.runtime.sendMessage({
          action: "charlieScreenshotSave",
          args: { image },
        });
        setStatus("已开始保存 PNG，请在浏览器下载记录查看。");
      }
    });
  const recognize = () =>
    run(async (job) => {
      setStatus("正在启动本地识字…");
      const request =
        globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
      ocrRef.current = request;
      try {
        const result = await browser.runtime.sendMessage({
          action: "charlieScreenshotOcr",
          args: { image, job: request },
        });
        if (job !== jobRef.current) return;
        if (result.error) throw new Error(result.error);
        setText(result.text.trim());
        setTranslation("");
        setStatus(
          result.text.trim()
            ? `${result.engine || "增强识字"} 完成。可修改原文，再点击翻译。`
            : "未识别到文字，请框选更清晰的区域。"
        );
      } finally {
        if (ocrRef.current === request) ocrRef.current = null;
      }
    });
  const translate = () =>
    run(async (job) => {
      const api = apis.find((item) => item.apiSlug === slug);
      if (!api || !text.trim()) throw new Error("请选择接口并填写原文");
      if (text.length > 12000) throw new Error("文字过长，请分段翻译");
      setTranslation("");
      setStatus(`正在使用 ${api.apiName} 翻译…`);
      const controller = new AbortController();
      abortRef.current = controller;
      for await (const chunk of handleTranslate([text], {
        from: OPT_LANGS_FROM_SPEC[api.apiType]?.get("auto") ?? "auto",
        to: OPT_LANGS_TO_SPEC[api.apiType]?.get(to) ?? to,
        fromLang: "auto",
        toLang: to,
        apiSetting: { ...api, useStream: false, useContext: false },
        usePool: false,
        signal: controller.signal,
      })) {
        if (job !== jobRef.current) return;
        setTranslation(
          Array.isArray(chunk.result)
            ? chunk.result[0]
            : chunk.result || chunk.partialText || ""
        );
      }
      if (job === jobRef.current) setStatus("翻译完成。");
    });
  const copy = async (value) => {
    try {
      await navigator.clipboard.writeText(value);
      setStatus("已复制。");
    } catch (_error) {
      setStatus("复制失败，请在文字框内手动选择并复制。");
    }
  };
  return (
    <main>
      <div className="actions">
        <button disabled={busy} onClick={capture}>
          框选截图
        </button>
        <button disabled={busy || !image} onClick={recognize}>
          本地识字
        </button>
        {busy && <button onClick={cancel}>停止</button>}
        {image && (
          <button disabled={busy} onClick={copyImage}>
            复制截图
          </button>
        )}
        {image && (
          <button disabled={busy} onClick={save}>
            保存截图
          </button>
        )}
      </div>
      <p role="status">{status}</p>
      {image && <img className="preview" src={image} alt="框选截图预览" />}
      <p className="note">
        增强识字在本机运行，不需要 Key。请保持桌面版开启，浏览器即可共用 OCR。
      </p>
      <label>
        原文
        <textarea
          value={text}
          disabled={busy}
          onChange={(event) => {
            setText(event.target.value);
            setTranslation("");
          }}
          placeholder="识字后显示原文，也可以直接输入文字"
        />
      </label>
      <div className="actions">
        <button disabled={!text} onClick={() => copy(text)}>
          复制原文
        </button>
      </div>
      <label>
        翻译接口
        <select
          disabled={busy}
          value={slug}
          onChange={(event) => setSlug(event.target.value)}
        >
          {apis.map((api) => (
            <option key={api.apiSlug} value={api.apiSlug}>
              {api.apiName}
            </option>
          ))}
        </select>
      </label>
      <label>
        目标语言
        <select
          disabled={busy}
          value={to}
          onChange={(event) => setTo(event.target.value)}
        >
          {OPT_LANGS_TO.map(([code, name]) => (
            <option key={code} value={code}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <p className="note">
        只有点击“翻译”才会将原文发送至所选接口。MTranServer
        在本机运行；选择云接口会发送文字至该服务。
      </p>
      <div className="actions">
        <button disabled={busy || !text.trim() || !slug} onClick={translate}>
          翻译
        </button>
        <button disabled={!translation} onClick={() => copy(translation)}>
          复制译文
        </button>
      </div>
      <label>
        译文
        <textarea value={translation} readOnly />
      </label>
    </main>
  );
}
