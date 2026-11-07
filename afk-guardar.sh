#!/bin/bash
# Guarda el estado del bot de una cuenta, cifrado con AFK_CLAVE: almacen (pg_dump), login Microsoft y logs recientes.
# Uso (desde deploy/vps): bash ../../afk-guardar.sh <salida.enc>
set -u
out=$1
: "${AFK_CLAVE:?falta AFK_CLAVE}"
rm -rf estado; mkdir -p estado/solo/logs-anteriores
pg_dump --clean --if-exists --no-owner --no-privileges > estado/almacen.sql 2>/dev/null || echo "aviso: no se pudo volcar el almacen"
for f in msa.json cuenta reinicios.log comandos.sha; do [ -f data/solo/$f ] && cp data/solo/$f estado/solo/; done
# la cuenta vigia (prueba proxys): su login y sus reinicios; las marcas de los proxys para la tanda siguiente
if [ -d data/vigia ]; then mkdir -p estado/vigia; for f in msa.json cuenta reinicios.log; do [ -f data/vigia/$f ] && cp data/vigia/$f estado/vigia/; done; fi
[ -f ../../proxy-vigia.log ] && tail -n 200 ../../proxy-vigia.log > estado/solo/logs-anteriores/proxy-vigia.log
# cache de proxys que entraron al server: se reusa la proxima tanda (lo que pidio REIDEN)
[ -f data/proxys/cache.tsv ] && { mkdir -p estado/proxys; cp data/proxys/cache.tsv estado/proxys/; }
[ -f data/solo/vigilante.log ] && tail -n 5000 data/solo/vigilante.log > estado/solo/vigilante.log
c=$(ls -t data/solo/logs/cliente-*.out 2>/dev/null | head -1); [ -n "$c" ] && tail -n 4000 "$c" > estado/solo/logs-anteriores/ultimo-cliente.out
echo $(( $(cat ../../tanda-anterior 2>/dev/null || echo 0) + 1 )) > estado/tanda
tar cz estado | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -pass env:AFK_CLAVE -out "$out"
echo "estado guardado: tanda $(cat estado/tanda), $(du -h "$out" | cut -f1) cifrado, login $( [ -s estado/solo/msa.json ] && echo si || echo NO), vigia $( [ -s estado/vigia/msa.json ] && echo si || echo no)"
rm -rf estado
