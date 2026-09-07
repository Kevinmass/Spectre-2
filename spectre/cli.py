"""CLI de Spectre.

Estado PR-19: subcomandos reales `config` (rutas resueltas), `db`
(migraciones), `csjn` (`catalog` lista los tomos del sitio oficial: número,
volumen, año, id CSJN; `download` baja el PDF de un tomo con reintentos y
caché), `pdf` (`stats` mide extracción/offset, `clean` mide la limpieza de
texto, `quality` mide caracteres por página y clasifica digital/requiere_ocr,
`index` parsea el índice por nombres de las partes, `segment` arma los fallos
con su cita, `meta` extrae fecha / jueces / recurso / tribunal / partes,
`sections` parte cada fallo en dictamen / mayoría / votos / disidencias,
`citations` extrae las citas `Fallos: N:N` a precedentes, `chunks` fragmenta
cada sección en ventanas de ~400 palabras), `embed` (`status` dice qué chunks
hay que reindexar, `probe` embebe un texto con el modelo real), `index`
(`status` mira los índices vectorial LanceDB y léxico FTS5, `buscar` corre una
consulta contra el léxico solo), `search` (`buscar` fusiona léxico +
vectorial por RRF, con filtros de año / tribunal / sección), `ingest`
(corre el pipeline completo — descargar/extraer/limpiar/segmentar/
estructurar/fragmentar/embeber/indexar — sobre un tomo, por etapa y
reanudable, y persiste todo en SQLite) y `serve` (PR-20: levanta el servidor
FastAPI que sirve `spectre/web/` en localhost y abre el navegador; layout,
navegación y estados vacíos honestos — buscar y biblioteca todavía no hacen
nada más que eso, llega en PR-21/PR-23).
"""

from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Sequence

from spectre import __version__
from spectre.config import PROJECT_ROOT, get_settings
from spectre.db import connect, migraciones_disponibles, migrate


def _cmd_config(_args: argparse.Namespace) -> int:
    s = get_settings()
    filas = [
        ("project_root", PROJECT_ROOT),
        ("data_dir", s.data_dir),
        ("tomos_dir", s.tomos_dir),
        ("db_path", s.db_path),
        ("vectors_dir", s.vectors_dir),
        ("embedding_model", s.embedding_model),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    return 0


def _cmd_db_migrate(_args: argparse.Namespace) -> int:
    s = get_settings()
    s.ensure_dirs()
    conn = connect(s.db_path)
    try:
        nuevas = migrate(conn)
    finally:
        conn.close()
    if nuevas:
        print(f"aplicadas en {s.db_path}:")
        for version in nuevas:
            print(f"  {version}")
    else:
        print(f"sin migraciones pendientes ({s.db_path})")
    return 0


def _cmd_db_status(_args: argparse.Namespace) -> int:
    s = get_settings()
    disponibles = [p.stem for p in migraciones_disponibles()]
    print(f"base: {s.db_path}")

    if not s.db_path.exists():
        print("  (la base no existe todavía — corré `spectre db migrate`)")
        for version in disponibles:
            print(f"  [pendiente] {version}")
        return 0

    conn = connect(s.db_path)
    try:
        try:
            aplicadas = {
                row["version"]
                for row in conn.execute("SELECT version FROM _migraciones")
            }
        except sqlite3.OperationalError:
            aplicadas = set()
    finally:
        conn.close()

    if not disponibles:
        print("  (no hay migraciones)")
    for version in disponibles:
        marca = "aplicada " if version in aplicadas else "pendiente"
        print(f"  [{marca}] {version}")
    huerfanas = aplicadas - set(disponibles)
    for version in sorted(huerfanas):
        print(f"  [huérfana ] {version}  (registrada pero sin archivo)")
    return 0


def _cmd_pdf_stats(args: argparse.Namespace) -> int:
    # Import perezoso: pdfplumber es pesado y solo `pdf` lo necesita.
    from spectre.corpus.pdf import calcular_offset, extraer_texto

    paginas = extraer_texto(args.pdf)
    r = calcular_offset(paginas)
    filas = [
        ("pdf", args.pdf),
        ("páginas", r.total),
        ("con nº oficial", f"{r.detectadas}  ({r.cobertura:.1%})"),
        ("offset", r.offset),
        ("consistencia", f"{r.consistentes}/{r.detectadas}  ({r.consistencia:.1%})"),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    if r.discrepancias:
        muestra = ", ".join(str(n) for n in r.discrepancias[:15])
        cola = " ..." if len(r.discrepancias) > 15 else ""
        etq = "discrepancias".ljust(ancho)
        print(f"{etq}  {len(r.discrepancias)} en pdf_page {muestra}{cola}")
    return 0


def _cmd_pdf_clean(args: argparse.Namespace) -> int:
    from spectre.corpus.pdf import contar_palabras, extraer_texto, limpiar

    paginas = extraer_texto(args.pdf)
    cuerpo = [p for p in paginas if p.pagina_oficial is not None]
    crudas = sum(contar_palabras(p.texto) for p in cuerpo)
    limpias = sum(contar_palabras(limpiar(p.texto)) for p in cuerpo)
    reduccion = (crudas - limpias) / crudas if crudas else 0.0
    filas = [
        ("pdf", args.pdf),
        ("páginas de cuerpo", len(cuerpo)),
        ("palabras crudas", crudas),
        ("palabras limpias", limpias),
        ("reducción", f"{reduccion:.2%}  (des-hifenado)"),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    if args.muestra is not None:
        elegida = next((p for p in paginas if p.pdf_page == args.muestra), None)
        if elegida is None:
            raise SystemExit(f"el PDF no tiene pdf_page {args.muestra}")
        print(f"\n--- pdf_page {args.muestra} limpia ---\n{limpiar(elegida.texto)}")
    return 0


def _cmd_pdf_quality(args: argparse.Namespace) -> int:
    from spectre.corpus.pdf import extraer_texto, medir_calidad

    paginas = extraer_texto(args.pdf)
    r = medir_calidad(paginas)
    filas = [
        ("pdf", args.pdf),
        ("calidad", r.calidad),
        ("páginas", r.total),
        ("con texto", f"{r.con_texto}  ({r.cobertura:.1%})"),
        ("caracteres/página", f"{r.caracteres_por_pagina:.0f}"),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    return 0


def _cmd_pdf_index(args: argparse.Namespace) -> int:
    from spectre.corpus.fallo import analizar_indice

    r = analizar_indice(args.pdf)
    citadas = r.paginas_citadas
    filas = [
        ("pdf", args.pdf),
        ("páginas del índice", f"pdf_page {r.paginas_indice[0]}–{r.paginas_indice[1]}"),
        ("carátulas", r.caratulas),
        ("referencias de página", r.referencias),
        ("páginas citadas", f"{min(citadas)}–{max(citadas)}"),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    multi = [e for e in r.entradas if len(e.paginas) > 1]
    if multi:
        print(f"\ncarátulas en varios fallos ({len(multi)}):")
        for e in multi:
            paginas = ", ".join(str(p) for p in e.paginas)
            print(f"  [{paginas}]  {e.caratula}")
    if args.muestra is not None:
        print(f"\n--- primeras {args.muestra} entradas ---")
        for e in r.entradas[: args.muestra]:
            paginas = ",".join(str(p) for p in e.paginas)
            print(f"  p.{paginas:<9} {e.caratula}")
    return 0


def _tomo_de_nombre(pdf: str) -> int | None:
    import re
    from pathlib import Path

    m = re.search(r"\d{2,4}", Path(pdf).stem)
    return int(m.group()) if m else None


def _cmd_pdf_segment(args: argparse.Namespace) -> int:
    from spectre.corpus.fallo import parsear_indice, segmentar
    from spectre.corpus.pdf import extraer_texto

    tomo = args.tomo or _tomo_de_nombre(args.pdf)
    if tomo is None:
        raise SystemExit("no pude inferir el número de tomo del nombre; pasá --tomo")

    paginas = extraer_texto(args.pdf)
    try:
        entradas = parsear_indice(args.pdf)
    except ValueError:
        entradas = None
    r = segmentar(entradas, paginas, tomo_numero=tomo)

    ini, fin = r.cobertura
    metodo = r.metodo + ("  (dudosa)" if r.dudosa else "")
    filas = [
        ("pdf", args.pdf),
        ("método", metodo),
        ("fallos", r.cantidad),
        ("cobertura", f"página {ini} a {fin}"),
        ("solapamientos", len(r.solapamientos)),
        ("huecos", len(r.huecos)),
        ("fallo más largo", f"{r.pagina_mas_larga} páginas"),
        ("mediana", f"{r.mediana_paginas:g} páginas"),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    for a, b in r.solapamientos:
        print(f"  solapa: {a} con {b}")
    for a, b in r.huecos:
        print(f"  hueco: entre página {a} y {b}")
    if args.muestra is not None:
        print(f"\n--- primeros {args.muestra} fallos ---")
        for f in r.fallos[: args.muestra]:
            print(f"  Fallos: {f.cita:10} ({f.paginas:>2} pág)  {f.caratula}")
    return 0


def _cmd_pdf_meta(args: argparse.Namespace) -> int:
    from spectre.corpus.fallo import (
        extraer_metadatos,
        parsear_indice,
        segmentar,
        texto_del_fallo,
    )
    from spectre.corpus.pdf import extraer_texto

    tomo = args.tomo or _tomo_de_nombre(args.pdf)
    if tomo is None:
        raise SystemExit("no pude inferir el número de tomo del nombre; pasá --tomo")

    paginas = extraer_texto(args.pdf)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin_cuerpo = max(por_oficial)
    try:
        entradas = parsear_indice(args.pdf)
    except ValueError:
        entradas = None
    r = segmentar(entradas, paginas, tomo_numero=tomo)

    metas = []
    for i, f in enumerate(r.fallos):
        siguiente = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        texto = texto_del_fallo(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=siguiente,
            pagina_fin_cuerpo=fin_cuerpo,
        )
        metas.append((f, extraer_metadatos(texto, caratula=f.caratula)))

    n = len(metas)
    con_fecha = sum(1 for _, m in metas if m.fecha)
    con_jueces = sum(1 for _, m in metas if m.jueces)
    ambos = sum(1 for _, m in metas if m.fecha and m.jueces)
    con_trib = sum(1 for _, m in metas if m.tribunal_origen)
    con_tipo = sum(1 for _, m in metas if m.tipo_recurso)
    con_dem = sum(1 for _, m in metas if m.demandado)
    filas = [
        ("pdf", args.pdf),
        ("fallos", n),
        ("con fecha", f"{con_fecha}/{n}  ({con_fecha / n:.1%})"),
        ("con jueces", f"{con_jueces}/{n}  ({con_jueces / n:.1%})"),
        ("con fecha y jueces", f"{ambos}/{n}  ({ambos / n:.1%})"),
        ("con tribunal origen", f"{con_trib}/{n}  ({con_trib / n:.1%})"),
        ("con tipo de recurso", f"{con_tipo}/{n}  ({con_tipo / n:.1%})"),
        ("con demandado", f"{con_dem}/{n}  (resto: una sola parte)"),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")

    sin = [f.cita for f, m in metas if not (m.fecha and m.jueces)]
    if sin:
        print(f"\nsin fecha o jueces ({len(sin)}): {', '.join(sin)}")
    if args.muestra is not None:
        print(f"\n--- primeros {args.muestra} fallos ---")
        for f, m in metas[: args.muestra]:
            print(f"  Fallos: {f.cita}")
            print(f"    fecha:     {m.fecha}")
            print(f"    jueces:    {', '.join(m.jueces) or '—'}")
            print(f"    recurso:   {m.tipo_recurso or '—'}")
            print(f"    t. origen: {m.tribunal_origen or '—'}")
            print(f"    partes:    {m.actor or '—'}  c/  {m.demandado or '—'}")
    return 0


def _cmd_pdf_sections(args: argparse.Namespace) -> int:
    import re

    from spectre.corpus.fallo import (
        parsear_indice,
        partir_secciones,
        segmentar,
        texto_del_fallo,
    )
    from spectre.corpus.pdf import extraer_texto

    marcador = re.compile(
        r"^(FALLO DE LA CORTE SUPREMA|Considerando\s*:|Autos y [Vv]istos.*|"
        r"Suprema Corte\s*:|Dictamen de la Procuraci.*|Vistos( los autos)?.*|"
        r"Resulta\s*:|voto (?:del?|de la|de los)\b.*|"
        r"[Dd]isidencia (?:del?|de la|de los)\b.*|-?[IVX]{1,6}-?\)?\s*$)",
        re.IGNORECASE,
    )

    tomo = args.tomo or _tomo_de_nombre(args.pdf)
    if tomo is None:
        raise SystemExit("no pude inferir el número de tomo del nombre; pasá --tomo")

    paginas = extraer_texto(args.pdf)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin_cuerpo = max(por_oficial)
    try:
        entradas = parsear_indice(args.pdf)
    except ValueError:
        entradas = None
    r = segmentar(entradas, paginas, tomo_numero=tomo)

    if args.cita:
        objetivo = next((f for f in r.fallos if f.cita == args.cita), None)
        if objetivo is None:
            raise SystemExit(f"no hay un fallo con cita {args.cita}")
        i = r.fallos.index(objetivo)
        sig = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        texto = texto_del_fallo(
            por_oficial,
            pagina_inicio=objetivo.pagina_inicio,
            pagina_inicio_siguiente=sig,
            pagina_fin_cuerpo=fin_cuerpo,
        )
        print(f"Fallos: {objetivo.cita}  {objetivo.caratula}\n")
        for s in partir_secciones(texto):
            palabras = len(s.texto.split())
            print(
                f"  [{s.orden}] {s.tipo:11} {s.autor or '—':40} {palabras:5} palabras"
            )
        return 0

    con_dict = con_voto = con_disi = una_sola = 0
    huerfanas = total = 0
    for i, f in enumerate(r.fallos):
        sig = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        texto = texto_del_fallo(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=sig,
            pagina_fin_cuerpo=fin_cuerpo,
        )
        secciones = partir_secciones(texto)
        tipos = {s.tipo for s in secciones}
        con_dict += "dictamen" in tipos
        con_voto += "voto" in tipos
        con_disi += "disidencia" in tipos
        una_sola += len(secciones) <= 1
        orig = [ln.strip() for ln in texto.splitlines() if ln.strip()]
        cubierto: list[str] = []
        for s in secciones:
            cubierto += [ln.strip() for ln in s.texto.splitlines() if ln.strip()]
        from collections import Counter

        falta = Counter(orig) - Counter(cubierto)
        huerfanas += sum(1 for ln in falta.elements() if not marcador.match(ln))
        total += len(orig)

    n = len(r.fallos)
    filas = [
        ("pdf", args.pdf),
        ("fallos", n),
        ("con dictamen", f"{con_dict}/{n}"),
        ("con >=1 voto", f"{con_voto}/{n}"),
        ("con >=1 disidencia", f"{con_disi}/{n}"),
        ("una sola sección", f"{una_sola}/{n}"),
        (
            "líneas de contenido huérfanas",
            f"{huerfanas}/{total}  ({huerfanas / total:.2%})",
        ),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    return 0


def _cmd_pdf_citations(args: argparse.Namespace) -> int:
    from collections import Counter

    from spectre.corpus.fallo import (
        contar_referencias,
        extraer_citas,
        parsear_indice,
        segmentar,
        texto_del_fallo,
    )
    from spectre.corpus.pdf import extraer_texto

    tomo = args.tomo or _tomo_de_nombre(args.pdf)
    if tomo is None:
        raise SystemExit("no pude inferir el número de tomo del nombre; pasá --tomo")

    paginas = extraer_texto(args.pdf)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin_cuerpo = max(por_oficial)
    try:
        entradas = parsear_indice(args.pdf)
    except ValueError:
        entradas = None
    r = segmentar(entradas, paginas, tomo_numero=tomo)

    por_fallo: list[tuple[str, list, int]] = []
    for i, f in enumerate(r.fallos):
        sig = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        texto = texto_del_fallo(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=sig,
            pagina_fin_cuerpo=fin_cuerpo,
        )
        por_fallo.append((f.cita, extraer_citas(texto), contar_referencias(texto)))

    if args.cita:
        elegido = next((c for c in por_fallo if c[0] == args.cita), None)
        if elegido is None:
            raise SystemExit(f"no hay un fallo con cita {args.cita}")
        cita, citas, refs = elegido
        print(f"Fallos: {cita}  ({refs} referencias, {len(citas)} fallos citados)\n")
        for c in citas:
            print(f"  Fallos: {c.tomo_citado}:{c.pagina_citada}")
            print(f"    {c.contexto}")
        return 0

    todas = [c for _, citas, _ in por_fallo for c in citas]
    destinos = Counter((c.tomo_citado, c.pagina_citada) for c in todas)
    citantes = sum(1 for _, citas, _ in por_fallo if citas)
    filas = [
        ("pdf", args.pdf),
        ("fallos", len(por_fallo)),
        ("referencias Fallos: N:N", sum(refs for _, _, refs in por_fallo)),
        ("citas (fallo a fallo)", len(todas)),
        ("destinos distintos", len(destinos)),
        ("fallos citantes", f"{citantes}/{len(por_fallo)}"),
        ("tomos citados distintos", len({t for t, _ in destinos})),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    mas_citados = destinos.most_common(5)
    if mas_citados:
        print("\nmás citados:")
        for (t, p), n in mas_citados:
            print(f"  Fallos: {t}:{p}  ({n})")
    return 0


def _cmd_pdf_chunks(args: argparse.Namespace) -> int:
    from statistics import mean, median

    from spectre.chunking import (
        fragmentar_fallo,
        normalizar_espacios,
        ubicar_pagina,
    )
    from spectre.corpus.fallo import (
        parsear_indice,
        partir_secciones,
        segmentar,
        texto_del_fallo_paginado,
    )
    from spectre.corpus.pdf import contar_palabras, extraer_texto, limpiar

    tomo = args.tomo or _tomo_de_nombre(args.pdf)
    if tomo is None:
        raise SystemExit("no pude inferir el número de tomo del nombre; pasá --tomo")
    if not 0 <= args.solape < args.objetivo:
        raise SystemExit("--solape tiene que ser >=0 y menor que --objetivo")

    paginas = extraer_texto(args.pdf)
    por_oficial = {p.pagina_oficial: p for p in paginas if p.pagina_oficial is not None}
    fin_cuerpo = max(por_oficial)
    try:
        entradas = parsear_indice(args.pdf)
    except ValueError:
        entradas = None
    r = segmentar(entradas, paginas, tomo_numero=tomo)

    por_fallo = []  # (fallo, secciones, chunks, ubicados)
    for i, f in enumerate(r.fallos):
        sig = r.fallos[i + 1].pagina_inicio if i + 1 < len(r.fallos) else None
        paginado = texto_del_fallo_paginado(
            por_oficial,
            pagina_inicio=f.pagina_inicio,
            pagina_inicio_siguiente=sig,
            pagina_fin_cuerpo=fin_cuerpo,
        )
        texto = "\n".join(t for _, t in paginado)
        secciones = partir_secciones(texto)
        chunks = fragmentar_fallo(
            secciones,
            paginado,
            cita=f.cita,
            pagina_inicio=f.pagina_inicio,
            objetivo=args.objetivo,
            solape=args.solape,
        )
        paginas_norm = [(o, normalizar_espacios(t)) for o, t in paginado]
        ubicados = sum(
            1
            for c in chunks
            if ubicar_pagina(normalizar_espacios(c.texto), paginas_norm) is not None
        )
        por_fallo.append((f, secciones, chunks, ubicados))

    if args.cita:
        elegido = next((x for x in por_fallo if x[0].cita == args.cita), None)
        if elegido is None:
            raise SystemExit(f"no hay un fallo con cita {args.cita}")
        f, secciones, chunks, _ = elegido
        print(f"Fallos: {f.cita}  {f.caratula}")
        print(f"  {len(secciones)} secciones, {len(chunks)} chunks\n")
        for c in chunks:
            ini = " ".join(c.texto.split()[:12])
            autor = c.seccion_autor or "-"
            print(
                f"  [{c.seccion_orden}.{c.orden}] {c.seccion_tipo:10} {autor:26.26} "
                f"p.{c.pagina_oficial}  {c.n_palabras:4}p  {ini}..."
            )
        return 0

    todos = [c for _, _, cs, _ in por_fallo for c in cs]
    if not todos:
        raise SystemExit(
            "no se generó ningún chunk: el tomo no tiene secciones con texto"
        )
    n_sec = sum(len(s) for _, s, _, _ in por_fallo)
    # D-4: cada chunk tiene que ser una ventana contigua de palabras de UNA
    # sección (la suya). Si eso vale, ningún chunk mezcla mayoría con disidencia.
    fuera_de_seccion = 0
    for _f, secciones, chunks, _u in por_fallo:
        por_orden = {s.orden: s.texto.split() for s in secciones}
        for c in chunks:
            pal = por_orden.get(c.seccion_orden, [])
            w = c.texto.split()
            if not any(pal[k : k + len(w)] == w for k in range(len(pal) - len(w) + 1)):
                fuera_de_seccion += 1
    en_rango = sum(
        1
        for f, _s, cs, _u in por_fallo
        for c in cs
        if f.pagina_inicio <= (c.pagina_oficial or -1) <= f.pagina_fin
    )
    ubicados = sum(u for _f, _s, _cs, u in por_fallo)

    cuerpo = [p for p in paginas if p.pagina_oficial is not None]
    cuerpo_palabras = sum(contar_palabras(limpiar(p.texto)) for p in cuerpo)
    paso = args.objetivo - args.solape
    filas = [
        ("pdf", args.pdf),
        ("fallos", len(por_fallo)),
        ("secciones", n_sec),
        ("chunks", len(todos)),
        (
            "referencia global",
            f"{cuerpo_palabras} palabras / paso {paso} ~ {cuerpo_palabras // paso}",
        ),
        ("chunks por fallo", f"{mean(len(cs) for _f, _s, cs, _u in por_fallo):.1f}"),
        ("palabras por chunk", f"mediana {median(c.n_palabras for c in todos):g}"),
        ("chunks fuera de su sección", fuera_de_seccion),
        ("página dentro del rango", f"{en_rango}/{len(todos)}"),
        ("página ubicada por texto", f"{ubicados}/{len(todos)}"),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    return 0


def _cmd_embed_status(_args: argparse.Namespace) -> int:
    from spectre.db import Repo, connect

    s = get_settings()
    modelo = s.embedding_model
    print(f"{'modelo (config)'.ljust(28)}  {modelo}")
    if not s.db_path.exists():
        print(
            f"{'base'.ljust(28)}  {s.db_path}  (no existe — corré `spectre db migrate`)"
        )
        return 0
    conn = connect(s.db_path)
    try:
        total = Repo(conn).contar_chunks()
        pendientes = Repo(conn).contar_chunks_pendientes(modelo)
    finally:
        conn.close()
    print(f"{'base'.ljust(28)}  {s.db_path}")
    print(f"{'chunks'.ljust(28)}  {total}")
    print(
        f"{'pendientes de embedding'.ljust(28)}  {pendientes}/{total}  (con {modelo})"
    )
    return 0


def _cmd_embed_probe(args: argparse.Namespace) -> int:
    from spectre.embed import cargar_modelo

    modelo = cargar_modelo(args.modelo)
    try:
        vectores = modelo.embed(args.textos)
        dimension = modelo.dimension
    except ModuleNotFoundError as e:
        raise SystemExit(str(e)) from e
    print(f"modelo     {modelo.nombre}")
    print(f"dimension  {dimension}")
    for texto, vector in zip(args.textos, vectores, strict=True):
        cabeza = ", ".join(f"{x:+.4f}" for x in vector[:8])
        print(f"  [{cabeza}, ...]  {texto[:60]}")
    return 0


def _cmd_index_status(_args: argparse.Namespace) -> int:
    from spectre.db import Repo, connect
    from spectre.index import IndiceLexico, IndiceVectorial

    s = get_settings()
    idx = IndiceVectorial(s.vectors_dir)
    total_vectores = idx.contar()
    dim = idx.dimension
    filas: list[tuple[str, object]] = [
        ("vectors_dir", s.vectors_dir),
        (
            "índice vectorial",
            f"{total_vectores} vectores"
            + (f", dimensión {dim}" if dim else "  (sin crear todavía)"),
        ),
    ]
    for modelo, n in sorted(idx.modelos().items()):
        filas.append((f"  con modelo {modelo}", n))

    if s.db_path.exists():
        conn = connect(s.db_path)
        try:
            repo = Repo(conn)
            total_chunks = repo.contar_chunks()
            pendientes = repo.contar_chunks_pendientes(s.embedding_model)
            total_fts = IndiceLexico(conn).contar()
        finally:
            conn.close()
        filas += [
            ("chunks en SQLite", total_chunks),
            ("chunks sin embedding", f"{pendientes}  (modelo {s.embedding_model})"),
            ("chunks en el índice vectorial", len(idx.ids())),
            ("chunks en el índice léxico (FTS5)", total_fts),
        ]
    else:
        filas.append(("base", f"{s.db_path}  (no existe — corré `spectre db migrate`)"))

    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    return 0


def _cmd_index_buscar(args: argparse.Namespace) -> int:
    from spectre.db import Repo, connect
    from spectre.index import IndiceLexico

    s = get_settings()
    if not s.db_path.exists():
        raise SystemExit(
            f"la base no existe todavía ({s.db_path}) — corré `spectre db migrate`"
        )

    conn = connect(s.db_path)
    try:
        resultados = IndiceLexico(conn).buscar(args.consulta, k=args.k)
        repo = Repo(conn)
        print(f"consulta: {args.consulta!r}  ({len(resultados)} resultados)\n")
        for r in resultados:
            chunk = repo.get_chunk(r.chunk_id)
            fallo = repo.get_fallo(chunk.fallo_id) if chunk else None
            cita = fallo.cita if fallo else "?"
            caratula = fallo.caratula if fallo else "?"
            extracto = " ".join(chunk.texto.split())[:120] if chunk else ""
            print(f"  [rank {r.rank:+.3f}]  Fallos: {cita}  {caratula}")
            print(f"    {extracto}...")
    finally:
        conn.close()
    return 0


def _cmd_search_buscar(args: argparse.Namespace) -> int:
    from spectre.db import Repo, connect
    from spectre.index import IndiceVectorial
    from spectre.search import buscar_hibrido

    s = get_settings()
    if not s.db_path.exists():
        raise SystemExit(
            f"la base no existe todavía ({s.db_path}) — corré `spectre db migrate`"
        )

    vector = None
    if not args.solo_lexico:
        from spectre.embed import cargar_modelo

        modelo = cargar_modelo()
        try:
            vector = modelo.embed_uno(args.consulta)
        except ModuleNotFoundError as e:
            raise SystemExit(f"{e}  (o corré con --solo-lexico)") from e

    conn = connect(s.db_path)
    try:
        idx_vec = IndiceVectorial(s.vectors_dir)
        repo = Repo(conn)
        resultados = buscar_hibrido(
            conn,
            idx_vec,
            args.consulta,
            vector,
            k=args.k,
            candidatos=args.candidatos,
            anio_desde=args.anio_desde,
            anio_hasta=args.anio_hasta,
            tribunal_origen=args.tribunal,
            tipo_seccion=args.seccion,
        )
        print(f"consulta: {args.consulta!r}  ({len(resultados)} resultados)\n")
        for r in resultados:
            chunk = repo.get_chunk(r.chunk_id)
            fallo = repo.get_fallo(chunk.fallo_id) if chunk else None
            cita = fallo.cita if fallo else "?"
            caratula = fallo.caratula if fallo else "?"
            extracto = " ".join(chunk.texto.split())[:120] if chunk else ""
            en = []
            if r.rank_lexico is not None:
                en.append(f"léxico #{r.rank_lexico + 1}")
            if r.rank_vectorial is not None:
                en.append(f"vectorial #{r.rank_vectorial + 1}")
            print(
                f"  [rrf {r.score:.4f}]  ({', '.join(en)})  Fallos: {cita}  {caratula}"
            )
            print(f"    {extracto}...")
    finally:
        conn.close()
    return 0


def _cmd_csjn_catalog(args: argparse.Namespace) -> int:
    from spectre.corpus.csjn import listar_catalogo

    entradas = listar_catalogo()
    numeros = {e.numero for e in entradas}
    por_numero: dict[int, list] = {}
    for e in entradas:
        por_numero.setdefault(e.numero, []).append(e)
    multivolumen = {n: es for n, es in por_numero.items() if len(es) > 1}

    filas = [
        ("filas del catálogo", len(entradas)),
        ("números de tomo distintos", len(numeros)),
        ("rango de números", f"{min(numeros)}–{max(numeros)}" if numeros else "—"),
        ("con más de un volumen", f"{len(multivolumen)} números"),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")

    if args.muestra is not None:
        print(f"\n--- primeras {args.muestra} filas ---")
        for e in entradas[: args.muestra]:
            etiqueta = f"{e.numero}-{e.volumen}" if e.volumen else str(e.numero)
            print(f"  {etiqueta:>8}  {e.anio:<10}  tomoId={e.csjn_tomo_id}")
    return 0


def _cmd_csjn_download(args: argparse.Namespace) -> int:
    from pathlib import Path

    from spectre.corpus.csjn import descargar_tomo

    destino = Path(args.destino)
    r = descargar_tomo(args.tomo_id, destino, forzar=args.forzar)
    filas = [
        ("ruta", r.ruta),
        ("bytes", r.bytes),
        ("sha256", r.sha256),
        ("ya estaba en disco", "sí" if r.reutilizada else "no (se descargó ahora)"),
    ]
    ancho = max(len(k) for k, _ in filas)
    for k, v in filas:
        print(f"{k.ljust(ancho)}  {v}")
    return 0


def _cmd_csjn_sumario(args: argparse.Namespace) -> int:
    from spectre.corpus.csjn import buscar_sumarios

    sumarios = buscar_sumarios(args.tomo, args.pagina)
    print(f"tomo {args.tomo}, página {args.pagina}: {len(sumarios)} sumario(s)")
    if not sumarios:
        print(
            "  (ese fallo no tiene sumarios en la base de la Secretaría, "
            "o la página no es el inicio de un fallo)"
        )
        return 0
    for i, s in enumerate(sumarios, 1):
        print(f"\n--- sumario {i}/{len(sumarios)} ---")
        if s.caratula:
            print(f"  carátula: {s.caratula}")
        if s.fecha:
            print(f"  fecha:    {s.fecha}")
        print(f"  voces:    {' · '.join(s.voces) if s.voces else '(sin voces)'}")
        print(f"  texto:    {s.texto}")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    from spectre.db import Repo
    from spectre.jobs import correr_pipeline, iniciar_tomo, progreso, siguiente_etapa

    s = get_settings()
    s.ensure_dirs()
    conn = connect(s.db_path)
    try:
        migrate(conn)
        repo = Repo(conn)
        tomo_id = iniciar_tomo(
            repo,
            numero=args.numero,
            pdf_path=args.pdf,
            csjn_tomo_id=args.csjn_tomo_id,
        )
        resultado = correr_pipeline(conn, [tomo_id])
        tomo = resultado[tomo_id]
        hechas, total = progreso(tomo)

        filas = [
            ("tomo", tomo.numero),
            ("estado", tomo.estado),
            ("calidad", tomo.calidad),
            ("etapas", f"{hechas}/{total}"),
        ]
        if tomo.estado == "indexado":
            filas += [
                ("fallos", len(repo.list_fallos(tomo_id))),
                ("chunks", len(repo.list_chunks_de_tomo(tomo_id))),
            ]
        ancho = max(len(k) for k, _ in filas)
        for k, v in filas:
            print(f"{k.ljust(ancho)}  {v}")

        if tomo.estado == "extraido" and tomo.calidad == "requiere_ocr":
            print(
                "\nrequiere OCR (D-10): no se sigue procesando: queda en la "
                "cola visible (tomos con calidad='requiere_ocr')."
            )
            return 0

        pendiente = siguiente_etapa(tomo)
        if pendiente is not None:
            # No terminó y no está frenado por calidad: alguna etapa falló.
            etapa, _ = pendiente
            fila = conn.execute(
                "SELECT error FROM jobs WHERE tipo = ? AND estado = 'fallido'"
                " ORDER BY id DESC LIMIT 1",
                (f"pipeline.{etapa}",),
            ).fetchone()
            detalle = fila["error"] if fila else "sin detalle (revisá `jobs`)"
            raise SystemExit(f"se frenó en la etapa '{etapa}': {detalle}")
        return 0
    finally:
        conn.close()


def _cmd_serve(args: argparse.Namespace) -> int:
    import webbrowser

    import uvicorn

    from spectre.api import crear_app

    s = get_settings()
    s.ensure_dirs()
    conn = connect(s.db_path)
    try:
        migrate(conn)
    finally:
        conn.close()

    url = f"http://{args.host}:{args.port}/"
    on_startup = None if args.no_browser else (lambda: webbrowser.open(url))
    app = crear_app(on_startup=on_startup)

    print(f"spectre serve: {url}  (Ctrl+C para cortar)")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spectre",
        description="Motor de búsqueda semántica sobre Fallos de la CSJN.",
    )
    parser.add_argument("--version", action="version", version=f"spectre {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<subcomando>")

    p_config = sub.add_parser("config", help="Imprime la configuración resuelta")
    p_config.set_defaults(func=_cmd_config)

    p_db = sub.add_parser("db", help="Esquema SQLite: migraciones y estado")
    db_sub = p_db.add_subparsers(dest="db_command", required=True, metavar="<acción>")
    p_db_migrate = db_sub.add_parser(
        "migrate", help="Aplica las migraciones pendientes (crea la base si falta)"
    )
    p_db_migrate.set_defaults(func=_cmd_db_migrate)
    p_db_status = db_sub.add_parser(
        "status", help="Lista migraciones aplicadas y pendientes"
    )
    p_db_status.set_defaults(func=_cmd_db_status)

    p_csjn = sub.add_parser("csjn", help="Catálogo de tomos en el sitio de la CSJN")
    csjn_sub = p_csjn.add_subparsers(
        dest="csjn_command", required=True, metavar="<acción>"
    )
    p_csjn_catalog = csjn_sub.add_parser(
        "catalog",
        help="Lista los tomos disponibles (número, volumen, año, id CSJN)",
    )
    p_csjn_catalog.add_argument(
        "--muestra", type=int, metavar="N", help="imprime las primeras N filas"
    )
    p_csjn_catalog.set_defaults(func=_cmd_csjn_catalog)
    p_csjn_download = csjn_sub.add_parser(
        "download",
        help="Descarga el PDF de un tomo (por su id de la CSJN) a disco",
    )
    p_csjn_download.add_argument("tomo_id", help="csjn_tomo_id (lo da `csjn catalog`)")
    p_csjn_download.add_argument("destino", help="ruta donde guardar el PDF")
    p_csjn_download.add_argument(
        "--forzar",
        action="store_true",
        help="vuelve a descargar aunque el destino ya exista",
    )
    p_csjn_download.set_defaults(func=_cmd_csjn_download)
    p_csjn_sumario = csjn_sub.add_parser(
        "sumario",
        help="Sumarios oficiales + voces de un fallo (por tomo y página). Mide, "
        "no persiste (PR-C2)",
    )
    p_csjn_sumario.add_argument("tomo", type=int, help="tomo de Fallos")
    p_csjn_sumario.add_argument(
        "pagina", type=int, help="página de inicio del fallo (la de la cita N:N)"
    )
    p_csjn_sumario.set_defaults(func=_cmd_csjn_sumario)

    p_pdf = sub.add_parser("pdf", help="Lectura de PDFs de tomos")
    pdf_sub = p_pdf.add_subparsers(
        dest="pdf_command", required=True, metavar="<acción>"
    )
    p_pdf_stats = pdf_sub.add_parser(
        "stats",
        help="Extrae el texto de un tomo y mide cobertura de nº oficial y offset",
    )
    p_pdf_stats.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_stats.set_defaults(func=_cmd_pdf_stats)

    p_pdf_clean = pdf_sub.add_parser(
        "clean",
        help="Limpia el texto del cuerpo y mide la reducción de palabras",
    )
    p_pdf_clean.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_clean.add_argument(
        "--muestra", type=int, metavar="PDF_PAGE", help="imprime esa página ya limpia"
    )
    p_pdf_clean.set_defaults(func=_cmd_pdf_clean)

    p_pdf_quality = pdf_sub.add_parser(
        "quality",
        help="Mide caracteres por página y clasifica el tomo digital/requiere_ocr",
    )
    p_pdf_quality.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_quality.set_defaults(func=_cmd_pdf_quality)

    p_pdf_index = pdf_sub.add_parser(
        "index",
        help="Parsea el índice por nombres de las partes y cuenta las carátulas",
    )
    p_pdf_index.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_index.add_argument(
        "--muestra", type=int, metavar="N", help="imprime las primeras N entradas"
    )
    p_pdf_index.set_defaults(func=_cmd_pdf_index)

    p_pdf_segment = pdf_sub.add_parser(
        "segment",
        help="Arma los fallos del tomo (rango de página + cita) desde el índice",
    )
    p_pdf_segment.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_segment.add_argument(
        "--tomo", type=int, help="número de tomo (si no, se infiere del nombre)"
    )
    p_pdf_segment.add_argument(
        "--muestra", type=int, metavar="N", help="imprime los primeros N fallos"
    )
    p_pdf_segment.set_defaults(func=_cmd_pdf_segment)

    p_pdf_meta = pdf_sub.add_parser(
        "meta",
        help="Extrae fecha, jueces, recurso, tribunal y partes de cada fallo",
    )
    p_pdf_meta.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_meta.add_argument(
        "--tomo", type=int, help="número de tomo (si no, se infiere del nombre)"
    )
    p_pdf_meta.add_argument(
        "--muestra", type=int, metavar="N", help="imprime los primeros N fallos"
    )
    p_pdf_meta.set_defaults(func=_cmd_pdf_meta)

    p_pdf_sections = pdf_sub.add_parser(
        "sections",
        help="Parte cada fallo en dictamen / mayoría / votos / disidencias",
    )
    p_pdf_sections.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_sections.add_argument(
        "--tomo", type=int, help="número de tomo (si no, se infiere del nombre)"
    )
    p_pdf_sections.add_argument(
        "--cita", help="detalla las secciones de un fallo (ej. 348:113)"
    )
    p_pdf_sections.set_defaults(func=_cmd_pdf_sections)

    p_pdf_citations = pdf_sub.add_parser(
        "citations",
        help="Extrae las citas `Fallos: N:N` a precedentes de cada fallo",
    )
    p_pdf_citations.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_citations.add_argument(
        "--tomo", type=int, help="número de tomo (si no, se infiere del nombre)"
    )
    p_pdf_citations.add_argument(
        "--cita", help="lista las citas de un fallo con su contexto (ej. 348:113)"
    )
    p_pdf_citations.set_defaults(func=_cmd_pdf_citations)

    p_pdf_chunks = pdf_sub.add_parser(
        "chunks",
        help="Fragmenta cada sección en ventanas de ~400 palabras con 80 de solape",
    )
    p_pdf_chunks.add_argument("pdf", help="ruta al PDF del tomo")
    p_pdf_chunks.add_argument(
        "--tomo", type=int, help="número de tomo (si no, se infiere del nombre)"
    )
    p_pdf_chunks.add_argument(
        "--cita", help="lista los chunks de un fallo (ej. 348:113)"
    )
    p_pdf_chunks.add_argument(
        "--objetivo", type=int, default=400, metavar="N", help="palabras por chunk"
    )
    p_pdf_chunks.add_argument(
        "--solape", type=int, default=80, metavar="N", help="palabras de solape"
    )
    p_pdf_chunks.set_defaults(func=_cmd_pdf_chunks)

    p_embed = sub.add_parser("embed", help="Modelo de embeddings: estado y prueba")
    embed_sub = p_embed.add_subparsers(
        dest="embed_command", required=True, metavar="<acción>"
    )
    p_embed_status = embed_sub.add_parser(
        "status", help="Modelo configurado y chunks pendientes de (re)embedding"
    )
    p_embed_status.set_defaults(func=_cmd_embed_status)
    p_embed_probe = embed_sub.add_parser(
        "probe", help="Carga el modelo y embebe uno o más textos de prueba"
    )
    p_embed_probe.add_argument("textos", nargs="+", help="texto(s) a embeber")
    p_embed_probe.add_argument(
        "--modelo", help="usar este modelo en vez del de la config"
    )
    p_embed_probe.set_defaults(func=_cmd_embed_probe)

    p_index = sub.add_parser(
        "index", help="Índices vectorial y léxico: estado y búsqueda"
    )
    index_sub = p_index.add_subparsers(
        dest="index_command", required=True, metavar="<acción>"
    )
    p_index_status = index_sub.add_parser(
        "status", help="Vectores/chunks en cada índice y qué falta indexar"
    )
    p_index_status.set_defaults(func=_cmd_index_status)
    p_index_buscar = index_sub.add_parser(
        "buscar", help="Busca una consulta en el índice léxico (FTS5)"
    )
    p_index_buscar.add_argument("consulta", help="texto a buscar")
    p_index_buscar.add_argument(
        "--k", type=int, default=10, metavar="N", help="cuántos resultados traer"
    )
    p_index_buscar.set_defaults(func=_cmd_index_buscar)

    p_search = sub.add_parser("search", help="Búsqueda híbrida: léxico + vectorial")
    search_sub = p_search.add_subparsers(
        dest="search_command", required=True, metavar="<acción>"
    )
    p_search_buscar = search_sub.add_parser(
        "buscar", help="Fusiona FTS5 y LanceDB por RRF, con filtros opcionales"
    )
    p_search_buscar.add_argument("consulta", help="texto a buscar")
    p_search_buscar.add_argument(
        "--k", type=int, default=10, metavar="N", help="cuántos resultados traer"
    )
    p_search_buscar.add_argument(
        "--candidatos",
        type=int,
        default=50,
        metavar="N",
        help="candidatos por índice antes de fusionar y filtrar",
    )
    p_search_buscar.add_argument(
        "--anio-desde", type=int, metavar="AAAA", help="año del fallo, piso inclusivo"
    )
    p_search_buscar.add_argument(
        "--anio-hasta", type=int, metavar="AAAA", help="año del fallo, techo inclusivo"
    )
    p_search_buscar.add_argument(
        "--tribunal", help="filtra por tribunal de origen (match exacto)"
    )
    p_search_buscar.add_argument(
        "--seccion",
        choices=["mayoria", "voto", "disidencia", "dictamen"],
        help="filtra por tipo de sección",
    )
    p_search_buscar.add_argument(
        "--solo-lexico",
        action="store_true",
        help="no embebe la consulta: solo busca en el índice léxico",
    )
    p_search_buscar.set_defaults(func=_cmd_search_buscar)

    p_ingest = sub.add_parser(
        "ingest",
        help="Corre el pipeline completo sobre un tomo (descargar..indexar)",
    )
    p_ingest.add_argument("numero", type=int, help="número de tomo")
    p_ingest.add_argument(
        "--pdf", help="ruta a un PDF ya en disco (subida manual, D-9)"
    )
    p_ingest.add_argument(
        "--csjn-tomo-id", help="id de la CSJN para descargarlo (lo da `csjn catalog`)"
    )
    p_ingest.set_defaults(func=_cmd_ingest)

    p_serve = sub.add_parser(
        "serve", help="Levanta el servidor local y abre el navegador"
    )
    p_serve.add_argument("--host", default="127.0.0.1", help="interfaz de red")
    p_serve.add_argument("--port", type=int, default=8000, help="puerto TCP")
    p_serve.add_argument(
        "--no-browser",
        action="store_true",
        help="no abre el navegador automáticamente",
    )
    p_serve.set_defaults(func=_cmd_serve)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
