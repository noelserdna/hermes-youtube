// Correo de hermes-youtube: un buzón para todo el sistema.
//  · email(): lo que llega al buzón (BUZON) (Email Routing → este Worker). Solo se acepta si Cloudflare lo da por
//    auténtico (primera Authentication-Results de mx.cloudflare.net con dmarc=pass) y no es una respuesta automática.
//    Se guarda en KV (in:<ts>:<id>, 14 días) para que el plugin lo recoja; lo descartado se cuenta (no se guarda el texto).
//  · fetch(), con el secreto compartido: GET /pendientes · POST /hecho {ids} · POST /enviar {to, subject, text, html,
//    in_reply_to} (sale desde REMITENTE con Reply-To al buzón; Auto-Submitted: auto-generated).
// Decidir no se decide aquí: lo hace el plugin por código (el código único de cada botón), nunca un modelo.
import PostalMime from "postal-mime";

const json = (d, s = 200) => new Response(JSON.stringify(d), { status: s, headers: { "content-type": "application/json" } });
const MAX_BYTES = 1024 * 1024;
const TTL = 14 * 86400;

function igual(a, b) {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

export function autentico(cabecera) {
  // Headers.get une varias cabeceras con «, »: la PRIMERA es la de Cloudflare (la antepone Email Routing)
  const primera = String(cabecera || "").split(/,\s*(?=[a-z0-9.-]+;)/i)[0].trim().toLowerCase();
  return primera.startsWith("mx.cloudflare.net") && /\bdmarc=pass\b/.test(primera);
}

export function automatico(h, de) {
  const g = (k) => String(h.get(k) || "").toLowerCase();
  if (g("auto-submitted") && g("auto-submitted") !== "no") return "auto-submitted";
  if (/\b(bulk|list|junk|auto_reply)\b/.test(g("precedence"))) return "precedence";
  if (g("x-autoreply") || g("x-autorespond") || g("x-auto-response-suppress")) return "x-autoreply";
  if (g("list-id") || g("list-unsubscribe")) return "lista";
  if (g("return-path").trim() === "<>") return "rebote";
  if (/^(mailer-daemon|postmaster|no-?reply|bounce)/i.test(String(de || ""))) return "remitente-automatico";
  return "";
}

async function contar(env, motivo) {
  const k = `descartados:${new Date().toISOString().slice(0, 10)}`;
  const d = (await env.CORREO.get(k, "json")) || {};
  d[motivo] = (d[motivo] || 0) + 1;
  await env.CORREO.put(k, JSON.stringify(d), { expirationTtl: TTL });
}

export async function recibir(message, env) {
  if (message.rawSize > MAX_BYTES) { await contar(env, "grande"); return "grande"; }
  if (!autentico(message.headers.get("authentication-results"))) { await contar(env, "no-autentico"); return "no-autentico"; }
  const auto = automatico(message.headers, message.from);
  if (auto) { await contar(env, auto); return auto; }
  const p = await PostalMime.parse(message.raw);
  const id = `${Date.now()}-${crypto.randomUUID().slice(0, 8)}`;
  const item = { id, ts: new Date().toISOString(), de: String(p.from?.address || message.from || "").toLowerCase(),
                 asunto: String(p.subject || "").slice(0, 300), texto: String(p.text || "").slice(0, 20000),
                 message_id: p.messageId || message.headers.get("message-id") || "", in_reply_to: p.inReplyTo || "" };
  await env.CORREO.put(`in:${id}`, JSON.stringify(item), { expirationTtl: TTL });
  return "ok";
}

export default {
  async email(message, env, ctx) {
    ctx.waitUntil(recibir(message, env));
  },
  async fetch(req, env) {
    const auth = req.headers.get("authorization") || "";
    if (!env.CORREO_SECRETO || !igual(auth, `Bearer ${env.CORREO_SECRETO}`)) return json({ error: "no autorizado" }, 401);
    const url = new URL(req.url);
    if (url.pathname === "/pendientes" && req.method === "GET") {
      const l = await env.CORREO.list({ prefix: "in:", limit: 50 });
      const out = [];
      for (const k of l.keys) { const v = await env.CORREO.get(k.name, "json"); if (v) out.push(v); }
      const descartados = (await env.CORREO.get(`descartados:${new Date().toISOString().slice(0, 10)}`, "json")) || {};
      return json({ correos: out, descartados_hoy: descartados });
    }
    if (url.pathname === "/hecho" && req.method === "POST") {
      const { ids = [] } = await req.json();
      for (const id of ids) await env.CORREO.delete(`in:${id}`);
      return json({ ok: true, borrados: ids.length });
    }
    if (url.pathname === "/enviar" && req.method === "POST") {
      const d = await req.json();
      if (!d.to || !d.subject || !(d.text || d.html)) return json({ error: "faltan to, subject y text/html" }, 400);
      const headers = { "Auto-Submitted": "auto-generated" };
      if (d.in_reply_to) { headers["In-Reply-To"] = d.in_reply_to; headers["References"] = d.in_reply_to; }
      try {
        const r = await env.EMAIL.send({ from: { email: env.REMITENTE, name: env.NOMBRE || "hermes-youtube" }, to: d.to,
                                         replyTo: env.BUZON, subject: String(d.subject).slice(0, 300),
                                         text: d.text || undefined, html: d.html || undefined, headers });
        return json({ ok: true, messageId: r.messageId });
      } catch (e) {
        return json({ ok: false, error: String(e.code || e.message || e).slice(0, 200) }, 502);
      }
    }
    return json({ error: "no existe" }, 404);
  },
};
