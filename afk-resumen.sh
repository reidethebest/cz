#!/bin/bash
# Resumen para el log publico: sin coordenadas, sin config, sin logs del juego.
q() { psql -At -F ' ' -c "$1" 2>/dev/null; }
tot=$(q "select count(*), coalesce(sum(case when applied >= required then 1 else 0 end),0) from bom")
[ -n "$tot" ] || { echo "[resumen $(date -u +%H:%M)] almacen vacio"; exit 0; }
set -- $tot
echo "[resumen $(date -u +%H:%M)] set: $2 de $1 lineas completas"
q "select '  falta ' || spec_key || ' ' || applied || '/' || required from bom where applied < required order by spec_key limit 15"
q "select '  compras ' || status || ': ' || count(*) || ' (' || coalesce(sum(qty*unit_price),0) || ' de plata)' from purchase group by status order by status"
l=$(q "select extract(epoch from now() - max(at))::int from event where bot like '%solo%'")
[ -n "$l" ] && echo "  ultimo latido del bot: hace ${l} s"
[ -s data/solo-cli.jar ] && java -jar data/solo-cli.jar --pg jdbc:postgresql://127.0.0.1:5432/pipeline --user pipeline --pass pipeline lista 2>/dev/null | head -40 | sed 's/^/  /'
exit 0
