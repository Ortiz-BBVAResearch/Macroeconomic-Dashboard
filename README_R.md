# Gráficos interactivos de Financiero con R

Este complemento reemplaza solo los gráficos de la pestaña **Financiero** por gráficos Plotly generados con R. Las demás pestañas conservan sus gráficos actuales.

## Ejecutar en RStudio

1. Copia `build_financial.R` a la carpeta del proyecto que contiene `data.json` e `index.html`.
2. Instala los paquetes una vez: `install.packages(c("jsonlite", "plotly", "htmltools"))`.
3. Abre esa carpeta como proyecto en RStudio y ejecuta `source("build_financial.R")`.
4. El script genera `financiero.html` y `financiero_files/`, y modifica únicamente la pestaña Financiero en `index.html` para mostrar esos gráficos interactivos.
5. Abre el dashboard con un servidor local (por ejemplo, `python -m http.server 8000`) para que el HTML y sus dependencias se carguen desde la misma carpeta.

Los gráficos permiten pasar el cursor, activar/desactivar series, hacer zoom y elegir periodos desde la barra de rango.

## Actualizaciones en GitHub

Copia también `.github/workflows/build-financial.yml` al repositorio. La acción genera los gráficos cuando cambian `data.json`, `index.html` o `build_financial.R`, y publica los archivos generados en `main`. Para que el sitio publique los cambios, GitHub Pages debe servir la carpeta raíz de `main`.

RStudio es el entorno de desarrollo; el script requiere que R esté instalado y que los tres paquetes anteriores estén disponibles.
