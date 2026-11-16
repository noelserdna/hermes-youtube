// hermes-youtube — pestaña «YouTube» del panel web de Hermes (medio dashboard).
// Sin build: IIFE con el SDK del panel (window.__HERMES_PLUGIN_SDK__). La API está en plugin_api.py.
(function () {
  "use strict";
  const SDK = window.__HERMES_PLUGIN_SDK__;
  const { React } = SDK;
  const { useState, useEffect, useCallback } = SDK.hooks;
  const { Button, Badge } = SDK.components;
  const h = React.createElement;
  const API = "/api/plugins/hermes-youtube";
  const get = (r) => SDK.fetchJSON(API + r);
  const BORDE = "1px solid var(--color-border)";
  const caja = { border: BORDE, borderRadius: 8, padding: 14, marginBottom: 12 };
  const tenue = { color: "var(--color-muted-foreground)", fontSize: 13 };

  function usarDatos(ruta, cada) {
    const [datos, setDatos] = useState(null);
    const [error, setError] = useState("");
    const cargar = useCallback(() => get(ruta).then((d) => { setDatos(d); setError(""); }).catch((e) => setError(String(e.message || e))), [ruta]);
    useEffect(() => { cargar(); if (!cada) return; const t = setInterval(cargar, cada); return () => clearInterval(t); }, [cargar, cada]);
    return [datos, error, cargar];
  }

  function Disco() {
    const [s] = usarDatos("/sistema", 60000);
    if (!s || !s.disco || !s.disco.length) return null;
    return h("div", { style: { display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 } }, s.disco.map((d) =>
      h(Badge, { key: d.punto, variant: d.aviso ? "destructive" : "outline" },
        (d.aviso ? "⚠️ " : "💾 ") + "Disco" + (s.disco.length > 1 ? " " + d.punto : "") + ": " + d.usado_pct + " % usado · " +
        String(d.libres_gb).replace(".", ",") + " GB libres de " + Math.round(d.total_gb))));
  }

  function Canales() {
    const [canales, error] = usarDatos("/canales", 15000);
    if (error) return h("p", { style: tenue }, error);
    if (!canales) return h("p", { style: tenue }, "Cargando…");
    if (!canales.length) return h("div", null, h(Disco), h("p", null, "Aún no hay ningún canal. Pídeselo a la coordinadora: «da de alta mi canal …»."));
    return h("div", null, h(Disco), canales.map((c) => h("div", { key: c.slug, style: caja },
      h("div", { style: { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" } },
        h("strong", null, c.nombre), h("span", { style: tenue }, "presenta: " + (c.presentador || "—")),
        h(Badge, { variant: "outline" }, c.idioma),
        c.pausado ? h(Badge, { variant: "destructive" }, "en pausa") : null,
        c.puertas ? h(Badge, null, "🚪 " + c.puertas) : null),
      h("div", { style: { ...tenue, marginTop: 6 } }, "Pilares: " + (c.pilares.join(", ") || "sin definir")),
      h("div", { style: { ...tenue, marginTop: 2 } }, "Tiene: " + (c.capacidades.join(", ") || "nada cargado aún")),
      c.encargos.length
        ? h("ul", { style: { margin: "8px 0 0 18px" } }, c.encargos.map((e) => h("li", { key: e.id }, e.nombre + " · " + e.estado +
            (e.puerta ? " · puerta " + e.puerta.indice + "/" + e.puerta.total + ": " + e.puerta.tipo + (e.puerta.papel ? " (decide: " + e.puerta.papel + ")" : "") : "") +
            (e.ronda ? " · ronda " + e.ronda : ""))))
        : h("div", { style: { ...tenue, marginTop: 6 } }, "Nada en marcha."))));
  }

  function Puerta({ p }) {
    // Solo lectura por ahora: las puertas se deciden en Telegram (el panel todavía no decide).
    return h("div", { style: caja },
      h("strong", null, p.titulo),
      h("div", { style: tenue }, [p.total > 1 ? "Puerta " + (p.indice + 1) + " de " + p.total : "", p.papel ? "decide: " + p.papel : "",
        p.ronda ? "ronda " + p.ronda : "", p.datos_pendientes ? p.datos_pendientes + " dato(s) por verificar" : ""].filter(Boolean).join(" · ")),
      h("pre", { style: { whiteSpace: "pre-wrap", fontFamily: "inherit", margin: "8px 0", maxHeight: 320, overflow: "auto" } }, p.texto),
      p.estado === "abierta" ? h("p", { style: tenue }, "Se decide en Telegram.")
      : p.estado === "decidida" ? h("span", null, "🕒 Decidido por " + p.decidio + ": «" + p.decision.verbo + "». Se ejecuta al acabar la ventana.")
      : h("p", { style: { color: "var(--color-destructive)" } }, "⚠️ " + (p.error || p.estado)));
  }

  function Decisiones() {
    const [ps, error] = usarDatos("/puertas", 10000);
    if (error) return h("p", { style: tenue }, error);
    if (!ps) return h("p", { style: tenue }, "Cargando…");
    if (!ps.length) return h("p", null, "No hay nada pendiente de decidir.");
    return h("div", null, ps.map((p) => h(Puerta, { key: p.id, p })));
  }

  // Irán aquí en un paso posterior: vídeos con su estado y su ronda, verificación de datos, publicados y acciones.
  const SECCIONES = [["Canales", Canales], ["Decisiones", Decisiones]];

  function Pagina() {
    const [sec, setSec] = useState(0);
    return h("div", { style: { padding: 16, maxWidth: 960 } },
      h("h1", { style: { fontSize: 20, fontWeight: 600, marginBottom: 4 } }, "YouTube"),
      h("p", { style: { ...tenue, marginBottom: 12 } }, "Tus canales, lo que tienen en marcha y lo que espera tu decisión. Para pedir trabajo, habla con la coordinadora."),
      h("div", { style: { display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" } },
        SECCIONES.map(([n], i) => h(Button, { key: n, size: "sm", variant: i === sec ? "default" : "ghost", onClick: () => setSec(i) }, n))),
      h(SECCIONES[sec][1]));
  }
  Pagina.partes = { Canales, Decisiones };
  window.__HERMES_PLUGINS__.register("hermes-youtube", Pagina);
})();
