#!/bin/bash
# Resumen para el log publico: sin coordenadas, sin config, sin logs del juego.
q() { psql -At -F ' ' -c "$1" 2>/dev/null; }
tot=$(q "select count(*), coalesce(sum(case when applied >= required then 1 else 0 end),0) from bom")
[ -n "$tot" ] || { echo "[resumen $(date -u +%H:%M)] almacen vacio"; exit 0; }
set -- $tot
echo "[resumen $(date -u +%H:%M)] set: $2 de $1 lineas completas"
q "select '  falta ' || spec_key || ' ' || applied || '/' || required from bom where applied < required order by spec_key limit 15"
q "select '  compras ' || status || ': ' || count(*) || ' (' || coalesce(sum(qty*unit_price),0) || ' de plata)' from purchase group by status order by status"
l=$(q "select ((extract(epoch from now()) * 1000)::bigint - max(at)) / 1000 from event")
[ -n "$l" ] && echo "  ultimo latido del bot: hace ${l} s"
# botellas: cuantas quedan (inventario + /pv + cofres) y si todavia faltan runas de botella. Sin botellas y con runas
# pendientes, una linea "AVISO SIN BOTELLAS" (Claude la busca en el log y le avisa a REIDEN para que cargue mas)
bot=$(q "select coalesce(sum(split_part(l, E'\t', 2)::int), 0) from snapshot, regexp_split_to_table(contents, E'\n') l where l like 'BOTTLE|%'")
pend=$(q "select coalesce(sum(qty - made), 0) from rune_order where state not in ('DONE', 'CANCELLED') and made < qty")
[ -n "$bot" ] && echo "  botellas: $bot, runas pendientes de botellas: ${pend:-0}"
[ "${bot:-1}" = "0" ] && [ "${pend:-0}" != "0" ] && echo "  AVISO SIN BOTELLAS: faltan ${pend} runas y no queda ninguna botella (cargar mas en /pv 1)"
if [ -s data/proxys/estado.json ]; then
  python3 - <<'PY' 2>/dev/null
import json, time
e = json.load(open("data/proxys/estado.json"))
print("  proxys: %d candidatos, %d sanos, %d para comprar, mediana %s ms; en 1 h %d entradas buenas y %d cortes (hace %d s)"
      % (e["candidatos"], e["sanos"], e["comprador"], e["ms_mediana"], e["entradas_buenas_1h"], e["cortes_1h"], time.time() - e["at"]))
PY
  c=$(ls -t data/solo/logs/cliente-*.out 2>/dev/null | head -1)
  [ -n "$c" ] && echo "  conexiones del comprador: $(grep -ac '\[PROXY\] uso' "$c") por proxy, $(grep -ac 'ningun proxy sano' "$c") esperando proxy, $(grep -ac '\[PROXY\] .* malo' "$c") proxys caidos"
fi
[ -s data/solo-cli.jar ] && java -jar data/solo-cli.jar --pg jdbc:postgresql://127.0.0.1:5432/pipeline --user pipeline --pass pipeline lista 2>/dev/null | head -40 | sed 's/^/  /'
exit 0
