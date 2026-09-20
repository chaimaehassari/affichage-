/*
 * Rendu des PDF localement (pdf.js).
 *
 * Pourquoi : le config.json synchronisé sur SFTP ne contient NI `url` NI
 * `pdf_pages` (STEP0_ANALYSE.md §3c) — contrairement à l'API web de
 * prévisualisation. Les pages d'un PDF ne sont pas non plus copiées dans
 * players/<code>/media/. Le player rend donc lui-même chaque page du PDF
 * (page = image), ~10 s par page, exactement comme PdfZone côté web.
 */
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist';
import PdfJsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?worker';

if (!GlobalWorkerOptions.workerPort) {
  GlobalWorkerOptions.workerPort = new PdfJsWorker();
}

/** Ouvre un document PDF depuis un ArrayBuffer. { numPages, destroy() }. */
export async function openPdf(arrayBuffer) {
  const task = getDocument({
    data: arrayBuffer,
    isEvalSupported: false,
    useWorkerFetch: false,
  });
  return task.promise;
}

/**
 * Rend la page `pageNumber` dans un canvas à la taille du conteneur
 * (object-fit cover : on remplit le cadre, on rogne l'excédent).
 */
export async function renderPdfPageToCanvas(pdf, pageNumber, canvas, width, height) {
  const page = await pdf.getPage(pageNumber);
  const base = page.getViewport({ scale: 1 });
  const scale = Math.max(width / base.width, height / base.height);
  const viewport = page.getViewport({ scale });
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const cw = Math.max(1, Math.round(width));
  const ch = Math.max(1, Math.round(height));
  canvas.width = Math.round(cw * dpr);
  canvas.height = Math.round(ch * dpr);
  canvas.style.width = `${cw}px`;
  canvas.style.height = `${ch}px`;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const transform = dpr === 1 ? null : [dpr, 0, 0, dpr, 0, 0];
  await page.render({ canvasContext: ctx, viewport, transform }).promise;
  page.cleanup();
}