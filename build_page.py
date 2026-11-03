"""Embed data.json into template.html.
   index.html    -> full document for GitHub Pages (works offline too)
   artifact.html -> body-only version for the claude.ai artifact preview
Run: python build_page.py"""
import json, sys
tpl = open("template.html", encoding="utf-8").read()
data = json.dumps(json.load(open("data.json", encoding="utf-8")), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
body = tpl.replace("__DATA__", data)
open("artifact.html", "w", encoding="utf-8").write(body)
head, rest = body.split("</style>", 1)
doc = ('<!doctype html>\n<html lang="es"><head><meta charset="utf-8">'
       '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
       '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
       'body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n'
       + head + "</style>\n</head><body>" + rest + "\n</body></html>\n")
open("index.html", "w", encoding="utf-8").write(doc)
print("index.html and artifact.html written", len(doc)//1024, "KB")
