"""Refresh data.json for the Spanish macro dashboard.

Sources (all public, no keys):
  * INE        - Tempus3 JSON API (servicios.ine.es/wstempus)
  * Banco de España - BIE / boletín CSV files (bde.es/webbe/.../csv/<table>.csv)
  * Ministerio de Economía, Comercio y Empresa - BDSICE full download (BdsiceCSV.zip)

Nothing is estimated. Transformations are limited to year-on-year rates computed from
levels, rolling 4-quarter / 12-month sums and simple ratios, each one stated in the
series' metadata. Run:  python update_data.py data.json
"""
import csv, datetime as dt, io, json, sys, zipfile, time
import requests

UA = {"User-Agent": "spain-macro-dashboard/1.0 (+github pages; public statistics)"}
INE = "https://servicios.ine.es/wstempus/js/ES/DATOS_SERIE/{c}?date=19950101:"
INE_LINK = "https://www.ine.es/consul/serie.do?s={c}"
BDE = "https://www.bde.es/webbe/es/estadisticas/compartido/datos/csv/{t}.csv"
BDE_LINK = "https://www.bde.es/webbe/es/estadisticas/temas/{t}"
MINECO_ZIP = "https://portal.mineco.gob.es/es-es/economiayempresa/EconomiaInformesMacro/Documents/BdsiceCSV.zip"
MINECO_LINK = "https://portal.mineco.gob.es/es-es/economiayempresa/EconomiaInformesMacro/Paginas/bdsice.aspx"
START = "2005-01-01"          # history kept in data.json
DAILY_START = "2021-01-01"    # daily market series

# ----------------------------------------------------------------------------------------
# Catalogue: id -> (source, code, label, unit, freq, block, extra)
#   source: ine | bde:<table> | mineco
#   extra:  dict with optional 'transform' ('yoy' = % change on a year earlier) and 'note'
# ----------------------------------------------------------------------------------------
CAT = [
    # Actividad - Contabilidad Nacional Trimestral (INE), datos CVEC, índices de volumen
    ("pib_qoq", "ine", "CNTR6653", "PIB · variación trimestral", "%", "Q", "actividad", {}),
    ("pib_yoy", "ine", "CNTR6654", "PIB · variación interanual", "%", "Q", "actividad", {}),
    ("dn_yoy", "ine", "CNTR7148", "Demanda nacional", "% a/a", "Q", "actividad", {}),
    ("ch_yoy", "ine", "CNTR7163", "Consumo de los hogares", "% a/a", "Q", "actividad", {}),
    ("cp_yoy", "ine", "CNTR7188", "Consumo de las AAPP", "% a/a", "Q", "actividad", {}),
    ("fbcf_yoy", "ine", "CNTR7213", "Formación bruta de capital fijo", "% a/a", "Q", "actividad", {}),
    ("x_yoy", "ine", "CNTR7267", "Exportaciones de bienes y servicios", "% a/a", "Q", "actividad", {}),
    ("m_yoy", "ine", "CNTR7287", "Importaciones de bienes y servicios", "% a/a", "Q", "actividad", {}),
    ("ap_dn", "ine", "CNTR7150", "Aportación de la demanda nacional", "pp", "Q", "actividad", {}),
    ("ap_de", "ine", "CNTR7264", "Aportación de la demanda externa", "pp", "Q", "actividad", {}),
    ("vab_agr", "ine", "CNTR6659", "VAB agricultura", "% a/a", "Q", "actividad", {}),
    ("vab_ind", "ine", "CNTR6664", "VAB industria", "% a/a", "Q", "actividad", {}),
    ("vab_con", "ine", "CNTR6674", "VAB construcción", "% a/a", "Q", "actividad", {}),
    ("vab_ser", "ine", "CNTR6679", "VAB servicios", "% a/a", "Q", "actividad", {}),
    ("pib_nom", "ine", "CNTR6548", "PIB a precios corrientes (sin ajustar)", "M€", "Q", "aux", {}),
    # Coyuntura mensual
    ("ipi_yoy", "ine", "IPI15374", "Producción industrial (CVEC)", "% a/a", "M", "coyuntura", {}),
    ("icm_yoy", "ine", "ICM3859", "Ventas del comercio minorista, precios constantes", "% a/a", "M", "coyuntura", {}),
    ("isa_ind", "mineco", "220000", "Indicador sintético de actividad · industria", "% a/a", "M", "coyuntura", {"transform": "yoy"}),
    ("isa_ser", "mineco", "240000", "Indicador sintético de actividad · servicios", "% a/a", "M", "coyuntura", {"transform": "yoy"}),
    ("isa_con", "mineco", "230090", "Indicador sintético de actividad · construcción", "% a/a", "M", "coyuntura", {"transform": "yoy"}),
    ("esi", "mineco", "680024", "Indicador de sentimiento económico (CE)", "índice", "M", "coyuntura", {}),
    ("conf_cons", "mineco", "684024", "Confianza del consumidor (CE)", "saldo", "M", "coyuntura", {}),
    ("cli", "mineco", "689024", "Indicador adelantado compuesto OCDE (CLI)", "índice", "M", "coyuntura", {}),
    ("matric", "mineco", "271300", "Matriculaciones de turismos", "% a/a", "M", "coyuntura", {"transform": "yoy"}),
    ("elec", "mineco", "255010", "Consumo eléctrico corregido de temperatura y calendario", "% a/a", "M", "coyuntura", {}),
    ("turistas", "mineco", "247100", "Entrada de turistas internacionales (Frontur)", "% a/a", "M", "coyuntura", {"transform": "yoy"}),
    ("gasto_tur", "mineco", "247321", "Gasto de turistas internacionales (Egatur)", "% a/a", "M", "coyuntura", {"transform": "yoy"}),
    ("hipotecas", "ine", "HPT34618", "Hipotecas sobre viviendas (número)", "% a/a", "M", "coyuntura", {"transform": "yoy"}),
    # Mercado laboral
    ("paro_epa", "ine", "EPA423474", "Tasa de paro (EPA)", "%", "Q", "empleo", {}),
    ("ocup_epa", "ine", "EPA387796", "Ocupados (EPA)", "miles", "Q", "empleo", {}),
    ("ocup_epa_yoy", "ine", "EPA387796", "Ocupados (EPA)", "% a/a", "Q", "empleo", {"transform": "yoy"}),
    ("afil_sa", "mineco", "190000m.d", "Afiliados a la Seguridad Social (CVEC)", "miles", "M", "empleo", {}),
    ("afil_yoy", "mineco", "190000m", "Afiliados a la Seguridad Social (media mensual)", "% a/a", "M", "empleo", {"transform": "yoy"}),
    ("paro_reg", "mineco", "170000n.d", "Paro registrado (CVEC)", "miles", "M", "empleo", {}),
    ("paro_reg_yoy", "mineco", "170000n", "Paro registrado", "% a/a", "M", "empleo", {"transform": "yoy"}),
    # Precios
    ("ipc", "ine", "IPC290750", "IPC general", "% a/a", "M", "precios", {}),
    ("ipc_sub", "ine", "IPC292510", "IPC subyacente", "% a/a", "M", "precios", {}),
    ("ipc_ene", "ine", "IPC292458", "IPC productos energéticos", "% a/a", "M", "precios", {}),
    ("ipc_ali", "ine", "IPC292534", "IPC alimentos, bebidas y tabaco", "% a/a", "M", "precios", {}),
    ("ipc_ser", "ine", "IPC292494", "IPC servicios", "% a/a", "M", "precios", {}),
    ("ipca", "ine", "IPCA8090", "IPCA (armonizado)", "% a/a", "M", "precios", {}),
    ("dif_uem", "mineco", "409096c", "Diferencial de inflación IPCA España − UEM", "pp", "M", "precios", {}),
    ("ipv", "ine", "IPV1376", "Precio de la vivienda (IPV)", "% a/a", "Q", "precios", {}),
    # Sector público
    ("deuda", "bde:be1102", "DTNPDE2010_P0000P_PS_APU", "Deuda de las AAPP (PDE)", "% PIB", "Q", "publico", {}),
    ("deficit_q", "mineco", "770t000000", "Capacidad/necesidad de financiación AAPP", "M€", "Q", "aux", {}),
    ("deficit_m", "mineco", "770m1000001p", "Saldo AC+CCAA+SS acumulado en el año", "% PIB", "M", "publico", {}),
    # Sector exterior (Banco de España, balanza de pagos)
    ("cc_m", "bde:be1701", "DEEM.N.ES.W1.S1.S1.T.B.CA._Z._Z._Z.EUR._T._X.N.ALL", "Saldo por cuenta corriente", "M€", "M", "aux", {}),
    ("bys_m", "bde:be1701", "DEEM.N.ES.W1.S1.S1.T.B.GS._Z._Z._Z.EUR._T._X.N.ALL", "Saldo de bienes y servicios", "M€", "M", "aux", {}),
    ("tur_ing_m", "bde:be1703", "DEEM.N.ES.W1.S1.S1.T.C.SD._Z._Z._Z.EUR._T._X.N.ALL", "Ingresos por turismo", "M€", "M", "aux", {}),
    # Financiero
    ("bono_es", "mineco", "867320q", "Rentabilidad bono 10 años · España", "%", "D", "financiero", {}),
    ("bono_de", "mineco", "867321q", "Rentabilidad bono 10 años · Alemania", "%", "D", "financiero", {}),
    ("bce_dfr", "mineco", "867104q", "BCE · facilidad de depósito", "%", "D", "financiero", {}),
    ("euribor12", "bde:be1901", "D_1NBAF472", "Euríbor a 12 meses", "%", "M", "financiero", {}),
    ("tipo_viv", "bde:be1904", "DN_1TI2T0002", "Tipo nuevas hipotecas (TEDR)", "%", "M", "financiero", {}),
    ("credito_osr", "bde:be0403", "D_BEEA1000", "Crédito a otros sectores residentes (saldo)", "% a/a", "M", "financiero", {"transform": "yoy", "note": "Variación del saldo vivo; no corrige saneamientos ni reclasificaciones."}),
    ("depositos_osr", "bde:be0405", "D_BEEP0000N", "Depósitos de otros sectores residentes (saldo)", "% a/a", "M", "financiero", {"transform": "yoy"}),
]

SOURCE_NAME = {"ine": "INE", "bde": "Banco de España", "mineco": "Ministerio de Economía (BDSICE)"}
MESES = {m: i + 1 for i, m in enumerate("ENE FEB MAR ABR MAY JUN JUL AGO SEP OCT NOV DIC".split())}


def get(url, tries=3, **kw):
    for k in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=180, **kw); r.raise_for_status(); return r
        except Exception:
            if k == tries - 1: raise
            time.sleep(3 * (k + 1))


# ---------------------------------------------------------------- INE
def ine_series(code):
    d = get(INE.format(c=code)).json()
    out = []
    for x in d.get("Data", []):
        if x.get("Valor") is None or x.get("Secreto"): continue
        y, p = x["Anyo"], x["FK_Periodo"]
        if 1 <= p <= 12: date = f"{y}-{p:02d}-01"
        elif 19 <= p <= 22: date = f"{y}-{(p - 19) * 3 + 1:02d}-01"
        else:  # fall back to the timestamp (Madrid midnight, so add 12h before taking the date)
            date = dt.datetime.utcfromtimestamp(x["Fecha"] / 1000 + 43200).strftime("%Y-%m-01")
        out.append([date, float(x["Valor"]), 1 if x.get("FK_TipoDato") == 3 else 0])
    out.sort()
    return d.get("Nombre", "").strip(), out


# ---------------------------------------------------------------- Banco de España
_BDE = {}
def bde_table(t):
    if t not in _BDE:
        txt = get(BDE.format(t=t)).content.decode("latin1")
        _BDE[t] = list(csv.reader(io.StringIO(txt)))
    return _BDE[t]

def bde_date(s):
    p = s.strip().split()
    if len(p) == 2 and p[0] in MESES: return f"{int(p[1])}-{MESES[p[0]]:02d}-01"
    if len(p) == 3 and p[1] in MESES: return f"{int(p[2])}-{MESES[p[1]]:02d}-{int(p[0]):02d}"
    return None

def bde_series(t, code):
    rows = bde_table(t); codes = [c.strip() for c in rows[0][1:]]
    i = codes.index(code) + 1
    desc = next((r[i] for r in rows[:8] if r and r[0].startswith("DESCRIPCI")), "")
    out = []
    for r in rows:
        if not r: continue
        d = bde_date(r[0])
        if not d or i >= len(r) or r[i] in ("", "_"): continue
        try: out.append([d, float(r[i]), 0])
        except ValueError: pass
    return desc, out


# ---------------------------------------------------------------- Ministerio (BDSICE)
_ZIP = None
def mineco_series(code):
    global _ZIP
    if _ZIP is None: _ZIP = zipfile.ZipFile(io.BytesIO(get(MINECO_ZIP).content))
    raw = _ZIP.read(code + ".csv").decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(raw), delimiter=";"))
    h = rows[0]; iobs = h.index("Observaciones"); title = rows[1][h.index("Título")]
    per = h[:iobs]; out = []
    for r in rows[1:]:
        if len(r) <= iobs or r[iobs].strip() == "": continue
        y = int(r[0])
        if len(per) == 1: d = f"{y}-01-01"
        elif per[1].startswith("Trimestre"): d = f"{y}-{(int(r[1]) - 1) * 3 + 1:02d}-01"
        elif len(per) == 2: d = f"{y}-{int(r[1]):02d}-01"
        else: d = f"{y}-{int(r[1]):02d}-{int(r[2]):02d}"
        try: out.append([d, float(r[iobs].replace(",", ".")), 0])
        except ValueError: continue   # 'ND' and other non-numeric markers
    out.sort()
    return title, out


# ---------------------------------------------------------------- transforms
def yoy(obs, freq):
    lag = {"M": 12, "Q": 4}[freq]; out = []
    idx = {o[0]: o[1] for o in obs}
    for d, v, f in obs:
        y, m = int(d[:4]), d[5:7]
        prev = idx.get(f"{y - 1}-{m}-01")
        if prev not in (None, 0): out.append([d, round(100 * (v / prev - 1), 2), f])
    return out

def rolling_sum(obs, n):
    out = []
    for i in range(n - 1, len(obs)):
        w = obs[i - n + 1:i + 1]
        # require consecutive periods
        out.append([obs[i][0], sum(x[1] for x in w), max(x[2] for x in w)])
    return out

def ratio_pct(num, den):
    di = {d: v for d, v, _ in den}; out = []
    for d, v, f in num:
        if d in di and di[d]: out.append([d, round(100 * v / di[d], 2), f])
    return out

def q_of(d): return f"{d[:4]}-{(int(d[5:7]) - 1) // 3 * 3 + 1:02d}-01"


def main(path):
    series, errors = {}, []
    for sid, src, code, label, unit, freq, block, extra in CAT:
        try:
            if src == "ine": name, obs = ine_series(code); link = INE_LINK.format(c=code); sname = "INE"
            elif src.startswith("bde:"):
                t = src.split(":")[1]; name, obs = bde_series(t, code); link = BDE.format(t=t); sname = "Banco de España"
            else: name, obs = mineco_series(code); link = MINECO_LINK; sname = "Ministerio de Economía (BDSICE)"
            tr = extra.get("transform")
            if tr == "yoy": obs = yoy(obs, freq)
            start = DAILY_START if freq == "D" else START
            obs = [[d, round(v, 4), f] for d, v, f in obs if d >= start]
            if freq == "Q": obs = [[q_of(d), v, f] for d, v, f in obs]   # BdE dates quarters by their last month
            if not obs: raise ValueError("sin observaciones")
            series[sid] = dict(label=label, unit=unit, freq=freq, block=block, source=sname, code=code,
                               table=src.split(":")[1] if ":" in src else None, original_name=name, link=link,
                               transform=tr, note=extra.get("note"), data=obs)
            print(f"ok  {sid:14s} {obs[-1][0]}  {obs[-1][1]}")
        except Exception as e:
            errors.append(f"{sid} ({code}): {e}"); print("ERR", sid, e)

    # ---- derived series (stated in 'transform')
    def add(sid, label, unit, freq, block, data, src, how, codes):
        series[sid] = dict(label=label, unit=unit, freq=freq, block=block, source=src, code=codes, table=None,
                           original_name=None, link=None, transform=how, note=None, data=data)
    try:
        gdp4 = rolling_sum(series["pib_nom"]["data"], 4)
        # IGAE quarterly series is cumulative within each year: undo the accumulation first
        ytd = series["deficit_q"]["data"]; flows = []
        for i, (d, v, f) in enumerate(ytd):
            prev = ytd[i - 1] if i else None
            flows.append([d, v - prev[1] if prev and d[5:7] != "01" and prev[0][:4] == d[:4] else v, f])
        deff = rolling_sum(flows, 4)
        add("deficit_4q", "Saldo de las AAPP (suma 4 trimestres)", "% PIB", "Q", "publico",
            ratio_pct(deff, gdp4), "IGAE vía Ministerio de Economía; PIB INE",
            "saldo IGAE desacumulado, suma móvil de 4 trimestres / suma de 4 trimestres del PIB nominal", "770t000000 / CNTR6548")
        # current account: 12-month sum over nominal GDP of the last 4 available quarters
        gdpq = {d: v for d, v, _ in gdp4}
        def over_gdp(m):
            s12 = rolling_sum(series[m]["data"], 12); out = []
            for d, v, f in s12:
                q = q_of(d); keys = sorted(k for k in gdpq if k <= q)
                if keys: out.append([d, round(100 * v / gdpq[keys[-1]], 2), f])
            return out
        add("cc_pib", "Saldo por cuenta corriente (12 meses)", "% PIB", "M", "exterior", over_gdp("cc_m"),
            "Banco de España; PIB INE", "suma de 12 meses / PIB nominal de los 4 últimos trimestres disponibles", "BE_17_1.1")
        add("bys_pib", "Saldo de bienes y servicios (12 meses)", "% PIB", "M", "exterior", over_gdp("bys_m"),
            "Banco de España; PIB INE", "suma de 12 meses / PIB nominal de los 4 últimos trimestres disponibles", "BE_17_1.2")
        tur = rolling_sum(series["tur_ing_m"]["data"], 12)
        add("tur_ing_12m", "Ingresos por turismo (12 meses)", "M€", "M", "exterior", [[d, round(v), f] for d, v, f in tur],
            "Banco de España", "suma móvil de 12 meses", "BE_17_3.3")
        es = {d: v for d, v, _ in series["bono_es"]["data"]}
        add("prima", "Prima de riesgo España − Alemania (10 años)", "pb", "D", "financiero",
            [[d, round(100 * (es[d] - v)), 0] for d, v, _ in series["bono_de"]["data"] if d in es],
            "Banco de España vía Ministerio de Economía", "diferencia diaria × 100", "867320q − 867321q")
    except Exception as e:
        errors.append(f"derivadas: {e}"); print("ERR derived", e)

    now = dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=1)))
    out = dict(meta=dict(title="Monitor macro · Economía española", refreshed=now.strftime("%Y-%m-%d %H:%M"),
                         timezone="Europe/Madrid", sources=["INE", "Banco de España", "Ministerio de Economía, Comercio y Empresa (BDSICE)"],
                         errors=errors, n_series=len(series)), series=series)
    with open(path, "w", encoding="utf-8") as fh: json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    with open("update_log.md", "a", encoding="utf-8") as fh:
        fh.write(f"- {out['meta']['refreshed']}: {len(series)} series" + (f"; errores: {'; '.join(errors)}" if errors else "") + "\n")
    print(f"\n{len(series)} series written to {path}; {len(errors)} errors")
    return 0 if len(series) > 40 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data.json"))
