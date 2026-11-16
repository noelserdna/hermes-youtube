// Worker del correo: autenticidad (solo la Authentication-Results de Cloudflare), respuestas automáticas, cola en KV,
// secreto en la API y envío con Reply-To al buzón e In-Reply-To.
import * as W from "../correo/worker.js";
let fallos = 0; const ok = (c, m) => { console.log((c ? "ok   " : "FAIL ") + m); if (!c) fallos = 1; };
const kv = new Map(); const enviados = [];
const env = { CORREO_SECRETO: "s3", BUZON: "buzon@x.dev", REMITENTE: "hermes@yt.x.dev",
  CORREO: { get: async (k, t) => kv.has(k) ? (t === "json" ? JSON.parse(kv.get(k)) : kv.get(k)) : null,
            put: async (k, v) => kv.set(k, v), delete: async (k) => kv.delete(k),
            list: async ({ prefix }) => ({ keys: [...kv.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name })) }) },
  EMAIL: { send: async (m) => { enviados.push(m); return { messageId: "<abc@cf>" }; } } };
const mime = (extra = "") => `From: Ana <ana@gmail.com>\r\nTo: buzon@x.dev\r\nSubject: APROBAR abc\r\nMessage-ID: <m1@gmail.com>\r\n${extra}\r\nAPROBAR abc123\r\n`;
const msg = (ar, extra = "") => ({ rawSize: 300, from: "ana@gmail.com", headers: new Headers({ "authentication-results": ar, ...Object.fromEntries(extra ? [extra.split(": ")] : []) }),
  raw: new Response(mime(extra)).body });
ok(W.autentico("mx.cloudflare.net; spf=pass; dkim=pass; dmarc=pass"), "auténtico: la de Cloudflare con dmarc=pass");
ok(!W.autentico("mx.otro.net; dmarc=pass, mx.cloudflare.net; dmarc=pass"), "una Authentication-Results falsa delante no cuela");
ok(!W.autentico("mx.cloudflare.net; spf=pass; dmarc=fail"), "dmarc=fail no");
ok(await W.recibir(msg("mx.cloudflare.net; dmarc=pass"), env) === "ok" && [...kv.keys()].some((k) => k.startsWith("in:")), "uno auténtico se guarda");
ok(await W.recibir(msg("mx.cloudflare.net; dmarc=fail"), env) === "no-autentico", "uno no auténtico se descarta");
ok(await W.recibir(msg("mx.cloudflare.net; dmarc=pass", "Auto-Submitted: auto-replied"), env) === "auto-submitted", "una respuesta automática (vacaciones) se descarta");
const req = (path, method = "GET", body, auth = "Bearer s3") => W.default.fetch(new Request("https://x" + path, { method, headers: { authorization: auth }, body: body && JSON.stringify(body) }), env);
ok((await req("/pendientes", "GET", undefined, "Bearer malo")).status === 401, "sin el secreto, 401");
const p = await (await req("/pendientes")).json();
ok(p.correos.length === 1 && p.correos[0].de === "ana@gmail.com" && p.correos[0].message_id === "<m1@gmail.com>" && p.descartados_hoy["no-autentico"] === 1, "pendientes: el correo con remitente y Message-ID; los descartados contados");
await req("/hecho", "POST", { ids: [p.correos[0].id] });
ok((await (await req("/pendientes")).json()).correos.length === 0, "hecho: sale de la cola");
const r = await (await req("/enviar", "POST", { to: "ana@gmail.com", subject: "Puerta", text: "x", in_reply_to: "<m1@gmail.com>" })).json();
const e = enviados[0];
ok(r.ok && e.from.email === "hermes@yt.x.dev" && e.replyTo === "buzon@x.dev" && e.headers["In-Reply-To"] === "<m1@gmail.com>" && e.headers["Auto-Submitted"] === "auto-generated", "enviar: desde el subdominio, Reply-To al buzón, en el hilo y marcado automático");
process.exit(fallos);
