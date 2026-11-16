// hermes-youtube — pestaña «YouTube» del panel web de Hermes (medio dashboard).
// Sin build: IIFE con el SDK del panel (window.__HERMES_PLUGIN_SDK__). La API está en plugin_api.py.
(function () {
  "use strict";
  const SDK = window.__HERMES_PLUGIN_SDK__;
  const { React } = SDK;
  const { useState, useEffect, useCallback, useRef } = SDK.hooks;
  const { Button, Badge, Input } = SDK.components;
  const h = React.createElement;
  const API = "/api/plugins/hermes-youtube";
  const get = (r) => SDK.fetchJSON(API + r);
  const enviar = (r, c, metodo) => SDK.fetchJSON(API + r, { method: metodo || "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(c || {}) });
  const BORDE = "1px solid var(--color-border)";
  const caja = { border: BORDE, borderRadius: 8, padding: 14, marginBottom: 12 };
  const tenue = { color: "var(--color-muted-foreground)", fontSize: 13 };
  const fila = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" };
  const celda = { padding: "6px 8px", borderBottom: BORDE, textAlign: "left", verticalAlign: "top" };
  const fallo = (e) => String((e && (e.detail || e.message)) || e);
  const campo = (props) => (Input ? h(Input, props) : h("input", { ...props, style: { border: BORDE, borderRadius: 6, padding: "6px 8px", ...(props.style || {}) } }));

  function usarDatos(ruta, cada) {
    const [datos, setDatos] = useState(null);
    const [error, setError] = useState("");
    const cargar = useCallback(() => (ruta ? get(ruta).then((d) => { setDatos(d); setError(""); }).catch((e) => setError(fallo(e))) : Promise.resolve()), [ruta]);
    useEffect(() => { setDatos(null); cargar(); if (!cada) return; const t = setInterval(cargar, cada); return () => clearInterval(t); }, [cargar, cada]);
    return [datos, error, cargar];
  }

  // El canal sobre el que se trabaja: botones con los canales; se elige el primero.
  function usarCanal() {
    const [canales] = usarDatos("/canales", 0);
    const [canal, setCanal] = useState("");
    useEffect(() => { if (canales && canales.length && !canal) setCanal(canales[0].slug); }, [canales]);
    const selector = !canales ? h("p", { style: tenue }, "Cargando…")
      : !canales.length ? h("p", null, "Aún no hay ningún canal.")
      : canales.length === 1 ? null
      : h("div", { style: { ...fila, marginBottom: 12 } }, canales.map((c) =>
          h(Button, { key: c.slug, size: "sm", variant: c.slug === canal ? "default" : "outline", onClick: () => setCanal(c.slug) }, c.nombre)));
    return [canal, selector, (canales || []).find((c) => c.slug === canal)];
  }

  function Aviso({ texto, malo }) {
    return texto ? h("p", { style: { ...tenue, color: malo ? "var(--color-destructive)" : tenue.color, margin: "6px 0" } }, texto) : null;
  }

  function Disco() {
    const [s] = usarDatos("/sistema", 60000);
    if (!s || !s.disco || !s.disco.length) return null;
    return h("div", { style: { ...fila, marginBottom: 12 } }, s.disco.map((d) =>
      h(Badge, { key: d.punto, variant: d.aviso ? "destructive" : "outline" },
        (d.aviso ? "⚠️ " : "💾 ") + "Disco" + (s.disco.length > 1 ? " " + d.punto : "") + ": " + d.usado_pct + " % usado · " +
        String(d.libres_gb).replace(".", ",") + " GB libres de " + Math.round(d.total_gb))));
  }

  function Canales() {
    const [canales, error] = usarDatos("/canales", 15000);
    if (error) return h(Aviso, { texto: error, malo: true });
    if (!canales) return h("p", { style: tenue }, "Cargando…");
    if (!canales.length) return h("div", null, h(Disco), h("p", null, "Aún no hay ningún canal. Pídeselo a la coordinadora: «da de alta mi canal …»."));
    return h("div", null, h(Disco), canales.map((c) => h("div", { key: c.slug, style: caja },
      h("div", { style: fila },
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

  // ── vídeos: cada uno con su estado, su ronda y a quién espera ──
  const ESPERA = { marketing: "marketing", datos: "quien verifica los datos", presentador: "quien presenta" };
  function Videos() {
    const [canal, selector] = usarCanal();
    const [vs, error] = usarDatos(canal ? "/videos/" + canal : "", 15000);
    return h("div", null, selector,
      error ? h(Aviso, { texto: error, malo: true })
      : !canal ? null
      : !vs ? h("p", { style: tenue }, "Cargando…")
      : !vs.length ? h("p", null, "Todavía no hay ningún vídeo. Pide una propuesta de temas en «Acciones».")
      : h("div", { style: { overflowX: "auto" } }, h("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: 14 } },
          h("thead", null, h("tr", null, ["Título", "Pilar", "Estado", "Ronda", "Espera a / incidencia"].map((t) => h("th", { key: t, style: celda }, t)))),
          h("tbody", null, vs.map((v) => h("tr", { key: v.encargo },
            h("td", { style: celda }, v.titulo || v.encargo),
            h("td", { style: celda }, v.pilar || "—"),
            h("td", { style: celda }, h(Badge, { variant: v.estado_id === "descartado" ? "destructive" : "outline" }, v.estado)),
            h("td", { style: celda }, v.ronda ? v.ronda + " de " + v.rondas_max : "—"),
            h("td", { style: celda }, v.incidencia ? "⚠️ " + v.incidencia
              : v.puerta ? "🚪 " + (ESPERA[v.puerta.papel] || "una decisión") + " (" + v.puerta.tipo + ")"
              : v.preparando ? "preparándose" : "—")))))));
  }

  // ── datos por verificar: uno a uno, por quien tiene el papel de esa puerta ──
  function Dato({ puerta, d, puedes, hecho }) {
    const [valor, setValor] = useState(d.valor || "");
    const [error, setError] = useState("");
    const poner = (estado) => enviar("/datos/" + puerta + "/" + encodeURIComponent(d.id), { estado, valor })
      .then(() => { setError(""); hecho(); }).catch((e) => setError(fallo(e)));
    const marca = { pendiente: "⏳ pendiente", verificado: "✅ verificado", corregido: "✏️ corregido", eliminado: "🗑 eliminado" }[d.estado] || d.estado;
    return h("div", { style: { borderTop: BORDE, padding: "10px 0" } },
      h("div", { style: fila }, h("strong", null, d.dato), h(Badge, { variant: d.estado === "pendiente" ? "default" : "outline" }, marca + (d.valor ? " → " + d.valor : ""))),
      d.frase ? h("div", { style: { marginTop: 4 } }, "Frase del guion: «" + d.frase + "»") : null,
      h("div", { style: tenue }, [d.motivo ? "Por qué hay que verificarlo: " + d.motivo : "", d.fuente ? "Fuente: " + d.fuente : "",
        d.versiones && d.versiones.length ? "Versiones que no coinciden: " + d.versiones.join(" · ") : ""].filter(Boolean).join(" · ")),
      puedes ? h("div", { style: { ...fila, marginTop: 8 } },
        h(Button, { size: "sm", variant: "outline", onClick: () => poner("verificado") }, "✅ Verificado"),
        campo({ value: valor, placeholder: "el valor correcto", "aria-label": "Valor correcto de " + d.dato, onChange: (e) => setValor(e.target.value), style: { maxWidth: 260 } }),
        h(Button, { size: "sm", variant: "outline", onClick: () => poner("corregido") }, "✏️ Corregir"),
        h(Button, { size: "sm", variant: "ghost", onClick: () => poner("eliminado") }, "🗑 Eliminar")) : null,
      h(Aviso, { texto: error, malo: true }));
  }

  function Datos() {
    const [ps, error, recargar] = usarDatos("/datos", 15000);
    const [msg, setMsg] = useState("");
    if (error) return h(Aviso, { texto: error, malo: true });
    if (!ps) return h("p", { style: tenue }, "Cargando…");
    if (!ps.length) return h("p", null, "No hay datos por verificar.");
    const aprobar = (p) => enviar("/datos/" + p.puerta + "/aprobar").then(() => { setMsg("Datos verificados: se firma al acabar la ventana para deshacer."); recargar(); })
      .catch((e) => setMsg(fallo(e)));
    return h("div", null, h(Aviso, { texto: msg }), ps.map((p) => h("div", { key: p.puerta, style: caja },
      h("div", { style: fila }, h("strong", null, p.titulo), h(Badge, { variant: "outline" }, p.canal),
        h(Badge, { variant: p.pendientes ? "default" : "outline" }, p.pendientes ? p.pendientes + " por verificar" : "todos verificados")),
      p.puedes ? null : h("p", { style: tenue }, "Estos datos los verifica quien tiene el papel «" + (p.papel || "datos") + "» en el canal."),
      p.datos.map((d) => h(Dato, { key: d.id, puerta: p.puerta, d, puedes: p.puedes, hecho: recargar })),
      p.puedes ? h("div", { style: { marginTop: 10 } },
        h(Button, { size: "sm", disabled: !!p.pendientes, onClick: () => aprobar(p) }, "✅ Datos verificados"),
        p.pendientes ? h("span", { style: { ...tenue, marginLeft: 8 } }, "Se activa cuando no quede ninguno pendiente.") : null) : null)));
  }

  // ── publicados: la lista con la que se avisa de temas parecidos ──
  function Publicados() {
    const [canal, selector] = usarCanal();
    const [ps, error, recargar] = usarDatos(canal ? "/publicados/" + canal : "", 0);
    const vacio = { id: "", titulo: "", pilar: "", url: "", fecha: "" };
    const [f, setF] = useState(vacio);
    const [msg, setMsg] = useState("");
    const guardar = () => enviar("/publicados/" + canal, f).then(() => { setF(vacio); setMsg(""); recargar(); }).catch((e) => setMsg(fallo(e)));
    const quitar = (id) => enviar("/publicados/" + canal + "/" + encodeURIComponent(id), null, "DELETE").then(() => { setMsg(""); recargar(); }).catch((e) => setMsg(fallo(e)));
    const entrada = (k, texto, ancho) => campo({ key: k, value: f[k], placeholder: texto, "aria-label": texto, onChange: (e) => setF({ ...f, [k]: e.target.value }), style: { maxWidth: ancho } });
    return h("div", null, selector, !canal ? null : h("div", null,
      h("div", { style: caja },
        h("strong", null, f.id ? "Editar un vídeo publicado" : "Añadir un vídeo publicado"),
        h("div", { style: { ...fila, marginTop: 8 } }, entrada("titulo", "Título", 320), entrada("pilar", "Pilar", 140), entrada("url", "Dirección del vídeo", 260), entrada("fecha", "Fecha (AAAA-MM-DD)", 170),
          h(Button, { size: "sm", onClick: guardar }, f.id ? "Guardar" : "Añadir"),
          f.id ? h(Button, { size: "sm", variant: "ghost", onClick: () => setF(vacio) }, "Cancelar") : null),
        h(Aviso, { texto: msg, malo: true })),
      error ? h(Aviso, { texto: error, malo: true })
      : !ps ? h("p", { style: tenue }, "Cargando…")
      : !ps.length ? h("p", null, "Aún no hay ningún vídeo publicado apuntado.")
      : ps.map((p) => h("div", { key: p.id, style: { ...caja, ...fila } },
          h("strong", null, p.titulo), p.pilar ? h(Badge, { variant: "outline" }, p.pilar) : null, h("span", { style: tenue }, p.fecha || ""),
          p.url ? h("a", { href: p.url, target: "_blank", rel: "noreferrer", style: tenue }, p.url) : null,
          h(Button, { size: "sm", variant: "outline", onClick: () => setF({ ...vacio, ...p }) }, "Editar"),
          h(Button, { size: "sm", variant: "ghost", onClick: () => quitar(p.id) }, "Quitar")))));
  }

  // ── acciones de marketing ──
  function Exportado({ texto }) {
    const ref = useRef(null);
    const [copiado, setCopiado] = useState("");
    const seleccionar = () => { if (ref.current) { ref.current.focus(); ref.current.select(); } };
    const copiar = () => {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(texto).then(() => setCopiado("Copiado."), () => { seleccionar(); setCopiado("No se pudo copiar solo: el texto queda seleccionado, cópialo con el teclado."); });
      } else { seleccionar(); setCopiado("El texto queda seleccionado: cópialo con el teclado."); }
    };
    return h("div", { style: { marginTop: 10 } },
      h("textarea", { ref, readOnly: true, value: texto, rows: 14, "aria-label": "Texto exportado", onFocus: (e) => e.target.select(),
        style: { width: "100%", border: BORDE, borderRadius: 6, padding: 8, fontFamily: "inherit", fontSize: 14 } }),
      h("div", { style: fila }, h(Button, { size: "sm", onClick: copiar }, "Copiar"), h("span", { style: tenue }, copiado)));
  }

  function Acciones() {
    const [canal, selector, datosCanal] = usarCanal();
    const [vs, , recargar] = usarDatos(canal ? "/videos/" + canal : "", 0);
    const [tema, setTema] = useState("");
    const [pilar, setPilar] = useState("");
    const [msg, setMsg] = useState("");
    const [malo, setMalo] = useState(false);
    const [url, setUrl] = useState({});
    const [exp, setExp] = useState(null);
    const di = (t, m) => { setMsg(t); setMalo(!!m); };
    const hacer = (p, bien) => p.then((r) => { di(bien(r)); recargar(); }).catch((e) => di(fallo(e), true));
    const propuesta = () => hacer(enviar("/acciones/" + canal + "/propuesta"), (r) => r.duplicado ? "Ya había una propuesta en marcha: no lanzo otra." : "Propuesta de temas en marcha.");
    const temaPropio = () => hacer(enviar("/acciones/" + canal + "/tema", { tema, pilar }), (r) => { setTema(""); return r.duplicado ? "Ese tema ya estaba en marcha." : "Título y miniatura en marcha para ese tema."; });
    const marcar = (v, estado) => hacer(enviar("/acciones/" + canal + "/marcar", { encargo: v.encargo, estado, url: url[v.encargo] || "" }), () => "«" + v.titulo + "» queda como " + estado + ".");
    const exportar = (v, parte) => get("/exportar/" + canal + "/" + v.encargo + "/" + parte).then((r) => { setExp({ titulo: v.titulo, parte, texto: r.texto }); di(""); }).catch((e) => di(fallo(e), true));
    const aprobados = (vs || []).filter((v) => ["aprobado", "grabado", "publicado"].indexOf(v.estado_id) >= 0);
    const pilares = (datosCanal && datosCanal.pilares_id) || [];
    return h("div", null, selector, !canal ? null : h("div", null,
      h("p", { style: tenue }, "Estas acciones son de quien lleva marketing en el canal."),
      h(Aviso, { texto: msg, malo }),
      h("div", { style: caja }, h("strong", null, "Pedir una propuesta de temas"),
        h("div", { style: { marginTop: 8 } }, h(Button, { size: "sm", onClick: propuesta }, "💡 Pedir propuesta"))),
      h("div", { style: caja }, h("strong", null, "Tema propio"),
        h("div", { style: { ...fila, marginTop: 8 } },
          campo({ value: tema, placeholder: "El tema, en una frase", "aria-label": "Tema", onChange: (e) => setTema(e.target.value), style: { maxWidth: 380 } }),
          pilares.length
            ? h("select", { value: pilar, "aria-label": "Pilar", onChange: (e) => setPilar(e.target.value), style: { border: BORDE, borderRadius: 6, padding: "6px 8px" } },
                [h("option", { key: "", value: "" }, "Sin pilar")].concat(pilares.map((p) => h("option", { key: p, value: p }, p))))
            : campo({ value: pilar, placeholder: "Pilar (opcional)", "aria-label": "Pilar", onChange: (e) => setPilar(e.target.value), style: { maxWidth: 160 } }),
          h(Button, { size: "sm", disabled: !tema.trim(), onClick: temaPropio }, "✍️ Preparar título y miniatura"))),
      h("div", { style: caja }, h("strong", null, "Vídeos aprobados: marcar y exportar"),
        !vs ? h("p", { style: tenue }, "Cargando…")
        : !aprobados.length ? h("p", { style: tenue }, "Todavía no hay ningún vídeo aprobado.")
        : aprobados.map((v) => h("div", { key: v.encargo, style: { borderTop: BORDE, padding: "10px 0" } },
            h("div", { style: fila }, h("strong", null, v.titulo), h(Badge, { variant: "outline" }, v.estado)),
            h("div", { style: { ...fila, marginTop: 6 } },
              h(Button, { size: "sm", variant: "outline", onClick: () => marcar(v, "grabado") }, "🎬 Grabado"),
              campo({ value: url[v.encargo] || "", placeholder: "Dirección del vídeo publicado", "aria-label": "Dirección de " + v.titulo, onChange: (e) => setUrl({ ...url, [v.encargo]: e.target.value }), style: { maxWidth: 260 } }),
              h(Button, { size: "sm", variant: "outline", onClick: () => marcar(v, "publicado") }, "📺 Publicado")),
            h("div", { style: { ...fila, marginTop: 6 } }, h("span", { style: tenue }, "Exportar:"),
              [["guion", "Guion"], ["titulo", "Título"], ["descripcion", "Descripción"], ["miniatura", "Miniatura"]].map(([k, t]) =>
                h(Button, { key: k, size: "sm", variant: "ghost", onClick: () => exportar(v, k) }, t))))),
        exp ? h("div", null, h("div", { style: { ...tenue, marginTop: 10 } }, "«" + exp.titulo + "» · " + exp.parte), h(Exportado, { key: exp.titulo + exp.parte, texto: exp.texto })) : null)));
  }

  function Puerta({ p }) {
    // Solo lectura: estas puertas se deciden por correo o en Telegram; los datos, en «Datos por verificar».
    return h("div", { style: caja },
      h("strong", null, p.titulo),
      h("div", { style: tenue }, [p.total > 1 ? "Puerta " + (p.indice + 1) + " de " + p.total : "", p.papel ? "decide: " + p.papel : "",
        p.ronda ? "ronda " + p.ronda : "", p.datos_pendientes ? p.datos_pendientes + " dato(s) por verificar" : ""].filter(Boolean).join(" · ")),
      h("pre", { style: { whiteSpace: "pre-wrap", fontFamily: "inherit", margin: "8px 0", maxHeight: 320, overflow: "auto" } }, p.texto),
      p.estado === "abierta" ? h("p", { style: tenue }, p.tipo === "datos" ? "Se verifica en «Datos por verificar»." : "Se decide por correo o en Telegram.")
      : p.estado === "decidida" ? h("span", null, "🕒 Decidido por " + p.decidio + ": «" + p.decision.verbo + "». Se ejecuta al acabar la ventana.")
      : h("p", { style: { color: "var(--color-destructive)" } }, "⚠️ " + (p.error || p.estado)));
  }

  function Decisiones() {
    const [ps, error] = usarDatos("/puertas", 10000);
    if (error) return h(Aviso, { texto: error, malo: true });
    if (!ps) return h("p", { style: tenue }, "Cargando…");
    if (!ps.length) return h("p", null, "No hay nada pendiente de decidir.");
    return h("div", null, ps.map((p) => h(Puerta, { key: p.id, p })));
  }

  const SECCIONES = [["Canales", Canales], ["Vídeos", Videos], ["Datos por verificar", Datos], ["Publicados", Publicados], ["Acciones", Acciones], ["Decisiones", Decisiones]];

  function Pagina() {
    const [sec, setSec] = useState(0);
    return h("div", { style: { padding: 16, maxWidth: 960 } },
      h("h1", { style: { fontSize: 20, fontWeight: 600, marginBottom: 4 } }, "YouTube"),
      h("p", { style: { ...tenue, marginBottom: 12 } }, "Tus canales, sus vídeos, los datos por verificar y lo que espera una decisión."),
      h("div", { style: { ...fila, marginBottom: 16 } },
        SECCIONES.map(([n], i) => h(Button, { key: n, size: "sm", variant: i === sec ? "default" : "ghost", onClick: () => setSec(i) }, n))),
      h(SECCIONES[sec][1]));
  }
  Pagina.partes = { Canales, Videos, Datos, Publicados, Acciones, Decisiones };
  window.__HERMES_PLUGINS__.register("hermes-youtube", Pagina);
})();
