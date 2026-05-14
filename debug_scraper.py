"""Diagnóstico do scraper: inspeciona HTML da resposta AJAX."""
import re
import requests
from bs4 import BeautifulSoup
import config

s = requests.Session()
s.headers.update(config.HEADERS_BASE)
s.headers["Referer"] = config.URL_FREQUENCIA

# -- Sessão inicial
r = s.get(config.URL_FREQUENCIA, timeout=30)
r.encoding = config.ENCODING_LEGSYS
html = r.text

# Captura sc_init
m = re.search(r"script_case_init['\"]?\s*[=:,]\s*['\"]?(\d{3,6})", html)
sc_init = m.group(1) if m else "0"
print(f"sc_init: {sc_init}")

ep = config.URL_FREQUENCIA + "index.php"

# -- Teste 1: export CSV
r2 = s.post(ep, data={
    "nmgp_opcao": "ajax_navigate",
    "script_case_init": sc_init,
    "opc": "exportar",
    "parm": "",
}, timeout=30)
r2.encoding = config.ENCODING_LEGSYS
print(f"\n[Export] status={r2.status_code} | CT={r2.headers.get('Content-Type','?')}")
print(f"[Export] primeiros 300: {repr(r2.text[:300])}")

# -- Teste 2: interativ_search com parm de abril/2026
parm = "pre_pre_data_presenca__DL__Mês e Ano__DL__dh__DL__2026-04##@@04/2026 __DL__S"
r3 = s.post(ep, data={
    "nmgp_opcao": "ajax_navigate",
    "script_case_init": sc_init,
    "opc": "interativ_search",
    "parm": parm,
}, timeout=30)
r3.encoding = config.ENCODING_LEGSYS
print(f"\n[Search abril/2026] status={r3.status_code} | len={len(r3.text)}")

soup = BeautifulSoup(r3.text, "lxml")

# Salva HTML para inspeção
with open("logs/debug_response.html", "w", encoding="utf-8") as f:
    f.write(r3.text)
print("[Search] HTML salvo em logs/debug_response.html")

# Procura padrão de paginação
text = soup.get_text(" ", strip=True)
m2 = re.search(r"(\d+)\s+a\s+(\d+)\s+de\s+(\d+)", text)
if m2:
    print(f"[Search] Paginação: {m2.group(0)}")
else:
    print("[Search] Padrão de paginação NÃO encontrado no texto")

# Mostra tabelas encontradas
tables = soup.find_all("table")
print(f"[Search] Tabelas encontradas: {len(tables)}")
for i, t in enumerate(tables[:3]):
    rows = t.find_all("tr")
    print(f"  Tabela {i}: {len(rows)} linhas")
    if rows:
        hdrs = [c.get_text(strip=True) for c in rows[0].find_all(["th","td"])]
        print(f"  Headers: {hdrs[:6]}")

# Mostra snippet do texto
print(f"\n[Search] Texto (primeiros 500 chars):")
print(text[:500])

# -- Teste 3: nav_first (sem filtro)
r4 = s.post(ep, data={
    "nmgp_opcao": "ajax_navigate",
    "script_case_init": sc_init,
    "opc": "nav_first",
    "parm": "",
}, timeout=30)
r4.encoding = config.ENCODING_LEGSYS
soup4 = BeautifulSoup(r4.text, "lxml")
text4 = soup4.get_text(" ", strip=True)
m4 = re.search(r"(\d+)\s+a\s+(\d+)\s+de\s+(\d+)", text4)
print(f"\n[nav_first] Paginação: {m4.group(0) if m4 else 'NÃO ENCONTRADO'}")
tables4 = soup4.find_all("table")
print(f"[nav_first] Tabelas: {len(tables4)}")
for i, t in enumerate(tables4[:3]):
    rows = t.find_all("tr")
    print(f"  Tabela {i}: {len(rows)} linhas | headers: {[c.get_text(strip=True) for c in rows[0].find_all(['th','td'])][:5] if rows else []}")

# Busca opções de meses disponíveis no HTML inicial
print("\n--- Meses disponíveis no HTML inicial ---")
pattern = re.compile(r"nm_proc_int_search\([^)]*?'(\d{4}-\d{2})##@@([^']+?)'")
meses = pattern.findall(html)
print(f"Meses encontrados: {meses[:10]}")
