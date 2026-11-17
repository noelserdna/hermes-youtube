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

  // ── configuración del canal: se ve entera; solo se cambia lo seguro (reglas, listas y el pie de la descripción) ──
  function Tabla({ datos }) {
    return h("table", { style: { width: "100%", fontSize: 13, borderCollapse: "collapse" } }, h("tbody", null,
      Object.entries(datos).map(([k, v]) => h("tr", { key: k },
        h("td", { style: { padding: "3px 8px 3px 0", ...tenue, width: "38%", verticalAlign: "top" } }, k),
        h("td", { style: { padding: 3, wordBreak: "break-word" } }, v == null || v === "" ? "—" : String(v))))));
  }

  function CampoConfig({ slug, c, alGuardar }) {
    const aTexto = (v) => (v == null ? "" : Array.isArray(v) ? v.join(c.tipo === "rango" ? "-" : "\n") : String(v));
    const [editando, setEditando] = useState(false);
    const [v, setV] = useState(aTexto(c.valor));
    const [msg, setMsg] = useState("");
    const [malo, setMalo] = useState(false);
    useEffect(() => { setV(aTexto(c.valor)); }, [JSON.stringify(c.valor)]);
    const guardar = () => enviar("/config/" + slug, { clave: c.clave, valor: v })
      .then(() => { setMsg("✅ Guardado"); setMalo(false); setEditando(false); alGuardar(); })
      .catch((e) => { setMsg(fallo(e)); setMalo(true); });
    const largo = c.tipo === "lista" || c.tipo === "texto";
    const ayuda = [c.ayuda, c.min != null ? "Entre " + c.min + " y " + c.max + "." : ""].filter(Boolean).join(" ");
    return h("div", { style: { borderTop: BORDE, padding: "8px 0" } },
      h("div", { style: { ...fila, justifyContent: "space-between" } },
        h("strong", { style: { fontSize: 14 } }, c.etiqueta),
        editando ? null : h(Button, { size: "sm", variant: "ghost", onClick: () => { setEditando(true); setMsg(""); } }, "Cambiar")),
      ayuda ? h("div", { style: tenue }, ayuda) : null,
      editando
        ? h("div", { style: { marginTop: 6 } },
            largo
              ? h("textarea", { value: v, rows: c.tipo === "lista" ? 6 : 4, "aria-label": c.etiqueta, onChange: (e) => setV(e.target.value),
                  style: { width: "100%", border: BORDE, borderRadius: 6, padding: 8, fontFamily: "inherit", fontSize: 14, background: "transparent", color: "inherit" } })
              : campo({ value: v, "aria-label": c.etiqueta, type: c.tipo === "numero" ? "number" : "text", placeholder: c.tipo === "rango" ? "mínimo-máximo" : "",
                  onChange: (e) => setV(e.target.value), style: { maxWidth: 200 } }),
            h("div", { style: { ...fila, marginTop: 6 } },
              h(Button, { size: "sm", onClick: guardar }, "Guardar"),
              h(Button, { size: "sm", variant: "ghost", onClick: () => { setEditando(false); setV(aTexto(c.valor)); setMsg(""); } }, "Cancelar")))
        : h("div", { style: { whiteSpace: "pre-wrap", marginTop: 4, fontSize: 13 } }, aTexto(c.valor) || "—"),
      h(Aviso, { texto: msg, malo }));
  }

  function Configuracion() {
    const [canal, selector] = usarCanal();
    const [cfg, error, recargar] = usarDatos(canal ? "/config/" + canal : "", 0);
    const seccion = (t, ...hijos) => h("div", { style: caja }, h("strong", null, t), h("div", { style: { marginTop: 8 } }, ...hijos));
    const lista = (xs, vacio) => (xs && xs.length ? h("ul", { style: { margin: "0 0 0 18px", fontSize: 13 } }, xs.map((x, i) => h("li", { key: i }, x))) : h("div", { style: tenue }, vacio));
    return h("div", null, selector,
      error ? h(Aviso, { texto: error, malo: true })
      : !canal ? null
      : !cfg ? h("p", { style: tenue }, "Cargando…")
      : h("div", null,
          seccion("El canal", h(Tabla, { datos: cfg.canal }),
            h("div", { style: { ...tenue, marginTop: 6 } }, "Tiene: " + (cfg.capacidades.join(", ") || "nada cargado aún"))),
          seccion("Pilares", lista(cfg.pilares.map((p) => p.nombre + " (" + p.id + ")" + (p.tipo === "prueba" ? " · en prueba" : "")), "Sin definir.")),
          seccion("Lo que puedes cambiar",
            h("p", { style: tenue }, "Lo cambia quien lleva marketing en el canal. Se aplica en el siguiente trabajo y cada cambio queda en el historial."),
            cfg.editables.map((c) => h(CampoConfig, { key: c.clave, slug: canal, c, alGuardar: recargar }))),
          seccion("Otros vetos y la transcripción", Object.entries(cfg.vetos).map(([t, xs]) =>
            h("div", { key: t, style: { marginBottom: 8 } }, h("div", { style: { fontSize: 13, fontWeight: 600 } }, t), lista(xs, "Ninguno.")))),
          Object.keys(cfg.marca).length ? seccion("Marca", h(Tabla, { datos: cfg.marca })) : null,
          seccion("Personas", !cfg.personas.length ? h("div", { style: tenue }, "Nadie apuntado todavía.")
            : cfg.personas.map((p) => h("div", { key: p.clave, style: { ...fila, padding: "3px 0" } },
                h("strong", { style: { fontSize: 13 } }, p.nombre), p.correo ? h("span", { style: tenue }, p.correo) : null,
                p.roles.map((r) => h(Badge, { key: r, variant: "outline" }, r)))),
            h("p", { style: { ...tenue, marginTop: 6 } }, "Las personas, sus papeles, los ejecutores, los modelos, lo que el canal permite y las claves se cambian con la coordinadora: las claves nunca pasan por aquí.")),
          seccion("Permite", h(Tabla, { datos: Object.fromEntries(Object.entries(cfg.permite).map(([k, v]) => [k.replace(/_/g, " "), v ? "sí" : "no"])) })),
          seccion("Cómo trabaja", cfg.como_trabaja.map((p) => h("div", { key: p.id, style: { marginBottom: 10 } },
            h("div", { style: fila }, h("strong", { style: { fontSize: 13 } }, p.nombre),
              p.propia ? h(Badge, { variant: "outline" }, p.hereda ? "adaptada de «" + p.hereda + "»" : "propia de este canal") : null,
              p.puertas.length ? h("span", { style: tenue }, "🚪 " + p.puertas.map((g) => g.tipo + (g.papel ? " (" + g.papel + ")" : "")).join(" → ")) : null),
            h("div", { style: { ...tenue, marginTop: 2 } }, p.etapas.map((e) => e.id + " (" + (e.skill ? e.skill + ", " : "") + e.ejecutor + (e.modelo && e.modelo !== "el del perfil" ? ", " + e.modelo : "") + ")").join(" → "))))),
          seccion("Historial de cambios", !cfg.historial.length ? h("p", { style: tenue }, "Sin cambios registrados.")
            : cfg.historial.map((r, i) => h("div", { key: i, style: { fontSize: 12, padding: "4px 0", borderTop: BORDE } },
                h("div", null, (r.ts || "").slice(0, 16).replace("T", " ") + " · " + (r.quien || "—") + " · ", h("strong", null, r.clave)),
                h("div", { style: tenue }, r.antes + " → " + r.despues))))));
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

  const SECCIONES = [["Canales", Canales], ["Vídeos", Videos], ["Datos por verificar", Datos], ["Publicados", Publicados], ["Acciones", Acciones], ["Decisiones", Decisiones], ["Configuración", Configuracion]];

  function Pagina() {
    const [sec, setSec] = useState(0);
    return h("div", { style: { padding: 16, maxWidth: 960 } },
      h("h1", { style: { fontSize: 20, fontWeight: 600, marginBottom: 4 } }, "YouTube"),
      h("p", { style: { ...tenue, marginBottom: 12 } }, "Tus canales, sus vídeos, los datos por verificar, lo que espera una decisión y la configuración de cada canal."),
      h("div", { style: { ...fila, marginBottom: 16 } },
        SECCIONES.map(([n], i) => h(Button, { key: n, size: "sm", variant: i === sec ? "default" : "ghost", onClick: () => setSec(i) }, n))),
      h(SECCIONES[sec][1]));
  }
  Pagina.partes = { Canales, Videos, Datos, Publicados, Acciones, Decisiones, Configuracion };
  window.__HERMES_PLUGINS__.register("hermes-youtube", Pagina);
})();
