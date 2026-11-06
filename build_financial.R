# Build interactive Plotly charts for the Financiero section.
# Run this script from the project directory containing data.json.
# Required packages: jsonlite, plotly, htmltools.

required <- c("jsonlite", "plotly", "htmltools")
missing <- required[!vapply(required, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) {
  stop("Install these packages in R first: install.packages(c(",
       paste(sprintf("\"%s\"", missing), collapse = ", "), "))")
}

args <- commandArgs(trailingOnly = TRUE)
input <- if (length(args) >= 1L) args[1] else "data.json"
index_path <- if (length(args) >= 2L) args[2] else "index.html"
if (!file.exists(input)) stop("Could not find ", input, " in the current directory.")

macro <- jsonlite::fromJSON(input, simplifyVector = FALSE)
series <- macro$series

series_frame <- function(id) {
  s <- series[[id]]
  if (is.null(s) || is.null(s$data) || !length(s$data)) return(NULL)
  rows <- lapply(s$data, function(x) data.frame(
    date = as.Date(x[[1]]),
    value = as.numeric(x[[2]]),
    flag = as.integer(x[[3]] %||% 0L)
  ))
  d <- do.call(rbind, rows)
  d <- d[is.finite(d$value) & !is.na(d$date), , drop = FALSE]
  d[order(d$date), , drop = FALSE]
}

`%||%` <- function(x, y) if (is.null(x)) y else x

COLORS <- c("#1F3FD1", "#8A86F0", "#D8732A", "#1C9AAB")

make_plot <- function(title, subtitle, ids, type = "line", unit = "") {
  p <- plotly::plot_ly()
  used <- 0L
  for (i in seq_along(ids)) {
    id <- ids[[i]]
    s <- series[[id]]
    d <- series_frame(id)
    if (is.null(s) || is.null(d) || !nrow(d)) next
    used <- used + 1L
    label <- s$label %||% id
    color <- COLORS[(i - 1L) %% length(COLORS) + 1L]
    hover <- paste0(
      "Fecha: ", format(d$date, "%d/%m/%Y"),
      "<br>", label, ": ", format(d$value, trim = TRUE, decimal.mark = ","),
      if (nzchar(unit)) paste0(" ", unit) else "",
      ifelse(d$flag != 0L, "<br>Dato provisional", "")
    )
    if (identical(type, "bar")) {
      p <- plotly::add_bars(p, data = d, x = ~date, y = ~value,
        name = label, marker = list(color = color), text = hover,
        hoverinfo = "text")
    } else {
      p <- plotly::add_lines(p, data = d, x = ~date, y = ~value,
        name = label, line = list(color = color, width = 2),
        text = hover, hoverinfo = "text")
    }
  }
  if (!used) return(htmltools::tags$div(class = "empty", "No hay datos disponibles para este gráfico."))
  plotly::layout(p,
    title = list(text = paste0("<b>", title, "</b><br><sup>", subtitle, "</sup>"), x = 0),
    hovermode = "x unified", dragmode = "zoom", autosize = TRUE,
    paper_bgcolor = "#ffffff", plot_bgcolor = "#ffffff",
    font = list(family = "Arial, sans-serif", color = "#000519", size = 12),
    legend = list(orientation = "h", x = 0, y = -0.24),
    margin = list(l = 58, r = 22, t = 72, b = 68),
    xaxis = list(type = "date", showgrid = TRUE, gridcolor = "#E6EBF0",
      rangeslider = list(visible = TRUE, thickness = 0.08),
      rangeselector = list(buttons = list(
        list(count = 1, label = "1a", step = "year", stepmode = "backward"),
        list(count = 5, label = "5a", step = "year", stepmode = "backward"),
        list(step = "all", label = "Todo")
      ))),
    yaxis = list(title = unit, showgrid = TRUE, gridcolor = "#E6EBF0",
      zeroline = TRUE, zerolinecolor = "#AAB5C5")
  )
}

charts <- list(
  make_plot("Rentabilidad de la deuda a 10 años", "Datos diarios", c("bono_es", "bono_de"), unit = "%"),
  make_plot("Prima de riesgo", "España − Alemania a 10 años", c("prima"), unit = "pb"),
  make_plot("Tipos de interés", "BCE, Euríbor a 12 meses y nuevas hipotecas", c("bce_dfr", "euribor12", "tipo_viv"), unit = "%"),
  make_plot("Crédito y depósitos", "Variación interanual del saldo vivo", c("credito_osr", "depositos_osr"), unit = "%"),
  make_plot("Compraventa con hipoteca", "Número de hipotecas sobre viviendas, variación interanual", c("hipotecas"), type = "bar", unit = "%")
)

cards <- lapply(charts, function(chart) htmltools::tags$section(class = "card", chart))
page <- htmltools::tagList(
  htmltools::tags$head(
    htmltools::tags$meta(charset = "utf-8"),
    htmltools::tags$meta(name = "viewport", content = "width=device-width, initial-scale=1"),
    htmltools::tags$title("BBVA Research · Financiero"),
    htmltools::tags$style(htmltools::HTML("html,body{margin:0;background:#F7F8F8;color:#000519;font-family:Arial,sans-serif}.head{background:#001391;color:#fff;padding:22px 28px}.head h1{margin:0;font-size:24px}.head p{margin:6px 0 0;color:#DCEBFF}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;padding:18px}.card{min-width:0;background:#fff;border:1px solid #D5DEE8;border-radius:8px;padding:10px}.card:last-child{grid-column:1/-1}.empty{padding:36px;color:#46536D}@media(max-width:760px){.grid{grid-template-columns:1fr;padding:10px}.card:last-child{grid-column:auto}}"))
  ),
  htmltools::tags$body(
    htmltools::tags$header(class = "head",
      htmltools::tags$h1("Financiero · BBVA Research"),
      htmltools::tags$p(paste("Datos actualizados:", macro$meta$refreshed %||% "sin fecha"))
    ),
    htmltools::tags$main(class = "grid", cards)
  )
)

htmltools::save_html(page, file = "financiero.html", libdir = "financiero_files", background = "#F7F8F8")

# Replace only the Financiero panel with the interactive R page. The other
# dashboard tabs keep their original JavaScript charts.
if (!file.exists(index_path)) stop("Could not find ", index_path, ".")
index <- paste(readLines(index_path, warn = FALSE, encoding = "UTF-8"), collapse = "\n")
marker <- "/*FINANCIAL_R_WIDGET*/"
if (!grepl(marker, index, fixed = TRUE)) {
  needle <- "function viewBlock(key){"
  where <- regexpr(needle, index, fixed = TRUE)[1]
  if (where < 0L) stop("Could not locate the dashboard's viewBlock(key) renderer in ", index_path, ".")
  embed <- paste0(
    needle, marker,
    "if(key==='financiero'){panel.innerHTML=`<div class=\"sechead\"><h2>${esc(TITLES[key])}</h2></div>",
    "<iframe title=\"Gráficos financieros interactivos\" src=\"financiero.html\" loading=\"lazy\" style=\"width:100%;height:1360px;border:0;background:#fff\"></iframe>`;return;}"
  )
  tail_start <- where + nchar(needle)
  index <- paste0(substr(index, 1L, where - 1L), embed, substr(index, tail_start, nchar(index)))
  writeLines(index, index_path, useBytes = TRUE)
}
message("Created financiero.html, financiero_files/ dependencies, and updated only the Financiero tab in ", index_path, ".")
