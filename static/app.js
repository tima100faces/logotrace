(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const drop = $("drop");
  const dropEmpty = $("drop-empty");
  const previewIn = $("preview-in");
  const fileInput = $("file");
  const fileLabel = $("file-label");
  const btnClear = $("btn-clear");
  const btnRun = $("btn-run");
  const btnDownload = $("btn-download");
  const statusEl = $("status");
  const outEmpty = $("out-empty");
  const pdfFrame = $("pdf-frame");
  const seg = $("palette-seg");

  /** @type {File|null} */
  let currentFile = null;
  let palette = "auto";
  /** @type {string|null} */
  let pdfObjectUrl = null;

  function setStatus(msg, kind) {
    statusEl.textContent = msg || "";
    statusEl.classList.remove("err", "ok");
    if (kind) statusEl.classList.add(kind);
  }

  function revokePdf() {
    if (pdfObjectUrl) {
      URL.revokeObjectURL(pdfObjectUrl);
      pdfObjectUrl = null;
    }
    pdfFrame.src = "about:blank";
    pdfFrame.classList.add("hidden");
    outEmpty.classList.remove("hidden");
    btnDownload.classList.add("hidden");
    btnDownload.removeAttribute("href");
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
    fileLabel.textContent = `${file.name || "pasted-image"} · ${formatBytes(file.size)}`;
    btnClear.classList.remove("hidden");
    btnRun.disabled = false;
    revokePdf();
    setStatus("Ready to convert.");
  }

  function clearFile() {
    currentFile = null;
    previewIn.removeAttribute("src");
    previewIn.classList.add("hidden");
    dropEmpty.classList.remove("hidden");
    drop.classList.remove("has-file");
    fileLabel.textContent = "No file";
    btnClear.classList.add("hidden");
    btnRun.disabled = true;
    revokePdf();
    setStatus("");
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
      /* permission / unsupported — fall through to paste event */
    }
    return false;
  }

  // Segmented control
  seg.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-palette]");
    if (!btn) return;
    palette = btn.getAttribute("data-palette") || "auto";
    seg.querySelectorAll(".seg-btn").forEach((b) => b.classList.toggle("active", b === btn));
  });

  // Drop / click
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

  // Paste: global so it works without focusing the drop zone
  window.addEventListener("paste", (e) => {
    const cd = e.clipboardData;
    if (!cd) return;
    // Prefer image items
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

  // Optional: Ctrl/Cmd+Shift+V could force clipboard API — regular V uses paste event
  window.addEventListener("keydown", (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key.toLowerCase() === "v") {
      // Let paste event handle; if nothing fires, try async read shortly after
      setTimeout(() => {
        if (!currentFile) tryClipboardRead();
      }, 50);
    }
  });

  async function convert() {
    if (!currentFile) return;
    btnRun.disabled = true;
    setStatus("Converting…");
    revokePdf();

    const fd = new FormData();
    fd.append("file", currentFile, currentFile.name || "logo.png");
    fd.append("palette", palette);
    fd.append("format", "pdf");

    try {
      const res = await fetch("/vectorize", { method: "POST", body: fd });
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
      pdfFrame.src = pdfObjectUrl;
      pdfFrame.classList.remove("hidden");
      outEmpty.classList.add("hidden");
      btnDownload.href = pdfObjectUrl;
      btnDownload.classList.remove("hidden");

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
