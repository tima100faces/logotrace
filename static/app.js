(() => {
  "use strict";

  const API_BASE = (() => {
    const b = document.querySelector("base");
    if (b && b.href) {
      try {
        const u = new URL(b.href, window.location.origin);
        return u.pathname.endsWith("/") ? u.pathname : u.pathname + "/";
      } catch {
        /* ignore */
      }
    }
    if (window.location.pathname.startsWith("/trace")) return "/trace/";
    return "/";
  })();

  const $ = (id) => document.getElementById(id);

  const drop = $("drop");
  const dropEmpty = $("drop-empty");
  const previewIn = $("preview-in");
  const fileInput = $("file");
  const btnClear = $("btn-clear");
  const btnRun = $("btn-run");
  const btnDownload = $("btn-download");
  const statusEl = $("status");
  const outEmpty = $("out-empty");
  const outStage = $("out-stage");
  const canvas = $("pdf-canvas");
  const zoomBar = $("zoom-bar");
  const zoomLabel = $("zoom-label");
  const btnZoomIn = $("zoom-in");
  const btnZoomOut = $("zoom-out");
  const btnZoomFit = $("zoom-fit");
  const seg = $("palette-seg");

  /** @type {File|null} */
  let currentFile = null;
  let palette = "auto";
  /** @type {string|null} */
  let pdfObjectUrl = null;
  /** @type {import('pdfjs-dist').PDFDocumentProxy|null} */
  let pdfDoc = null;
  /** @type {ArrayBuffer|null} */
  let pdfData = null;
  let fitScale = 1;
  let userZoom = 1;
  let renderToken = 0;
  let pdfjsReady = null;

  function setStatus(msg, kind) {
    statusEl.textContent = msg || "";
    statusEl.classList.remove("err", "ok");
    if (kind) statusEl.classList.add(kind);
  }

  function ensurePdfJs() {
    if (pdfjsReady) return pdfjsReady;
    pdfjsReady = new Promise((resolve, reject) => {
      const start = Date.now();
      (function tick() {
        if (window.pdfjsLib) {
          window.pdfjsLib.GlobalWorkerOptions.workerSrc =
            "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
          resolve(window.pdfjsLib);
          return;
        }
        if (Date.now() - start > 15000) {
          reject(new Error("PDF preview library failed to load"));
          return;
        }
        setTimeout(tick, 40);
      })();
    });
    return pdfjsReady;
  }

  function revokePdf() {
    if (pdfObjectUrl) {
      URL.revokeObjectURL(pdfObjectUrl);
      pdfObjectUrl = null;
    }
    pdfDoc = null;
    pdfData = null;
    userZoom = 1;
    fitScale = 1;
    const ctx = canvas.getContext("2d");
    if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    canvas.width = 0;
    canvas.height = 0;
    outStage.classList.add("hidden");
    zoomBar.classList.add("hidden");
    outEmpty.classList.remove("hidden");
    btnDownload.classList.add("hidden");
    btnDownload.removeAttribute("href");
    zoomLabel.textContent = "100%";
  }

  function setFile(file) {
    if (!file || !file.type.startsWith("image/")) {
      setStatus("Clipboard / file is not an image.", "err");
      return;
    }
    currentFile = file;
    const url = URL.createObjectURL(file);
    previewIn.onload = () => URL.revokeObjectURL(url);
    previewIn.src = url;
    previewIn.classList.remove("hidden");
    dropEmpty.classList.add("hidden");
    drop.classList.add("has-file");
    btnClear.classList.remove("hidden");
    btnRun.disabled = false;
    revokePdf();
    setStatus(""); // hint visible, no "Ready" message
  }

  function clearFile() {
    currentFile = null;
    previewIn.removeAttribute("src");
    previewIn.classList.add("hidden");
    dropEmpty.classList.remove("hidden");
    drop.classList.remove("has-file");
    btnClear.classList.add("hidden");
    btnRun.disabled = true;
    revokePdf();
    setStatus("Auto smart-detects. Pick a number for exact ink count.");
  }

  function formatBytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  }

  function fileFromBlob(blob, name) {
    const type = blob.type || "image/png";
    const ext = type.split("/")[1] || "png";
    return new File([blob], name || `paste.${ext}`, { type });
  }

  async function tryClipboardRead() {
    if (!navigator.clipboard || !navigator.clipboard.read) return false;
    try {
      const items = await navigator.clipboard.read();
      for (const item of items) {
        const type = item.types.find((t) => t.startsWith("image/"));
        if (!type) continue;
        const blob = await item.getType(type);
        setFile(fileFromBlob(blob, `clipboard.${type.split("/")[1]}`));
        return true;
      }
    } catch {
      /* ignore */
    }
    return false;
  }

  function updateZoomLabel() {
    zoomLabel.textContent = `${Math.round(userZoom * 100)}%`;
  }

  function computeFitScale(page) {
    const base = page.getViewport({ scale: 1 });
    const pad = 32;
    const aw = Math.max(120, outStage.clientWidth - pad);
    const ah = Math.max(120, outStage.clientHeight - pad);
    const sx = aw / base.width;
    const sy = ah / base.height;
    return Math.min(sx, sy, 2.5);
  }

  async function renderPage() {
    if (!pdfDoc) return;
    const token = ++renderToken;
    const page = await pdfDoc.getPage(1);
    if (token !== renderToken) return;

    fitScale = computeFitScale(page);
    const scale = fitScale * userZoom;
    const viewport = page.getViewport({ scale });
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    canvas.width = Math.floor(viewport.width * dpr);
    canvas.height = Math.floor(viewport.height * dpr);
    canvas.style.width = `${Math.floor(viewport.width)}px`;
    canvas.style.height = `${Math.floor(viewport.height)}px`;

    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, viewport.width, viewport.height);

    await page.render({ canvasContext: ctx, viewport }).promise;
    if (token !== renderToken) return;
    updateZoomLabel();
  }

  async function showPdf(blob) {
    const pdfjsLib = await ensurePdfJs();
    pdfData = await blob.arrayBuffer();
    pdfDoc = await pdfjsLib.getDocument({ data: pdfData.slice(0) }).promise;
    outEmpty.classList.add("hidden");
    outStage.classList.remove("hidden");
    zoomBar.classList.remove("hidden");
    userZoom = 1;
    await renderPage();
  }

  function setZoom(next) {
    userZoom = Math.min(6, Math.max(0.25, next));
    renderPage();
  }

  seg.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-palette]");
    if (!btn) return;
    palette = btn.getAttribute("data-palette") || "auto";
    seg.querySelectorAll(".seg-btn").forEach((b) => b.classList.toggle("active", b === btn));
  });

  drop.addEventListener("click", () => {
    if (!currentFile) fileInput.click();
  });
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (!currentFile) fileInput.click();
    }
  });
  fileInput.addEventListener("change", () => {
    const f = fileInput.files && fileInput.files[0];
    if (f) setFile(f);
    fileInput.value = "";
  });

  ["dragenter", "dragover"].forEach((ev) => {
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      e.stopPropagation();
      drop.classList.add("drag");
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      e.stopPropagation();
      drop.classList.remove("drag");
    });
  });
  drop.addEventListener("drop", (e) => {
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) setFile(f);
  });

  btnClear.addEventListener("click", (e) => {
    e.stopPropagation();
    clearFile();
  });

  window.addEventListener("paste", (e) => {
    const cd = e.clipboardData;
    if (!cd) return;
    if (cd.files && cd.files.length) {
      for (const f of cd.files) {
        if (f.type.startsWith("image/")) {
          e.preventDefault();
          setFile(f);
          return;
        }
      }
    }
    const items = cd.items;
    if (items) {
      for (const it of items) {
        if (it.type.startsWith("image/")) {
          e.preventDefault();
          const blob = it.getAsFile();
          if (blob) setFile(fileFromBlob(blob));
          return;
        }
      }
    }
  });

  window.addEventListener("keydown", (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key.toLowerCase() === "v") {
      setTimeout(() => {
        if (!currentFile) tryClipboardRead();
      }, 50);
    }
    if (!pdfDoc) return;
    if (e.key === "+" || e.key === "=") {
      e.preventDefault();
      setZoom(userZoom * 1.2);
    } else if (e.key === "-" || e.key === "_") {
      e.preventDefault();
      setZoom(userZoom / 1.2);
    } else if (e.key === "0" && mod) {
      e.preventDefault();
      setZoom(1);
    }
  });

  btnZoomIn.addEventListener("click", () => setZoom(userZoom * 1.25));
  btnZoomOut.addEventListener("click", () => setZoom(userZoom / 1.25));
  btnZoomFit.addEventListener("click", () => setZoom(1));

  outStage.addEventListener(
    "wheel",
    (e) => {
      if (!pdfDoc) return;
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      const factor = e.deltaY > 0 ? 1 / 1.12 : 1.12;
      setZoom(userZoom * factor);
    },
    { passive: false }
  );

  // Hand tool: drag to pan inside the fixed stage
  let panning = false;
  let panX = 0;
  let panY = 0;
  let panLeft = 0;
  let panTop = 0;
  outStage.style.cursor = "grab";
  outStage.addEventListener("pointerdown", (e) => {
    if (!pdfDoc || e.button !== 0) return;
    panning = true;
    panX = e.clientX;
    panY = e.clientY;
    panLeft = outStage.scrollLeft;
    panTop = outStage.scrollTop;
    outStage.setPointerCapture(e.pointerId);
    outStage.classList.add("panning");
    outStage.style.cursor = "grabbing";
    e.preventDefault();
  });
  outStage.addEventListener("pointermove", (e) => {
    if (!panning) return;
    outStage.scrollLeft = panLeft - (e.clientX - panX);
    outStage.scrollTop = panTop - (e.clientY - panY);
  });
  function endPan(e) {
    if (!panning) return;
    panning = false;
    outStage.classList.remove("panning");
    outStage.style.cursor = "grab";
    try {
      outStage.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  }
  outStage.addEventListener("pointerup", endPan);
  outStage.addEventListener("pointercancel", endPan);

  let resizeTimer = 0;
  window.addEventListener("resize", () => {
    if (!pdfDoc) return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => renderPage(), 120);
  });

  async function convert() {
    if (!currentFile) return;
    btnRun.disabled = true;
    setStatus("Vectorizing…");
    revokePdf();

    const fd = new FormData();
    fd.append("file", currentFile, currentFile.name || "logo.png");
    fd.append("palette", palette);
    fd.append("format", "pdf");

    try {
      const res = await fetch(API_BASE + "vectorize", { method: "POST", body: fd });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const j = await res.json();
          detail = j.detail || JSON.stringify(j);
        } catch {
          try {
            detail = await res.text();
          } catch {
            /* ignore */
          }
        }
        throw new Error(detail || `HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const head = new Uint8Array(await blob.slice(0, 5).arrayBuffer());
      const magic = String.fromCharCode(...head);
      if (!magic.startsWith("%PDF")) {
        throw new Error("Server did not return a PDF");
      }

      pdfObjectUrl = URL.createObjectURL(blob);
      btnDownload.href = pdfObjectUrl;
      btnDownload.classList.remove("hidden");

      await showPdf(blob);

      const mode = res.headers.get("X-LogoTrace-Colors-Mode") || "";
      const n = res.headers.get("X-LogoTrace-Colors") || "";
      setStatus(`Done · ${mode}${n ? ` ${n}` : ""} · ${(blob.size / 1024).toFixed(0)} KB`, "ok");
    } catch (err) {
      setStatus(err && err.message ? err.message : String(err), "err");
    } finally {
      btnRun.disabled = !currentFile;
    }
  }

  btnRun.addEventListener("click", convert);
})();
