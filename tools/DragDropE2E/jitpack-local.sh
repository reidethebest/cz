#!/bin/bash
# jitpack hoy devuelve "gitError"/404 para varios com.github.*. Arma uno desde GitHub (javac de src/main/java, sin
# dependencias) y lo deja en ~/.m2 con un pom vacio, para que mavenLocal() lo encuentre. Uso: jitpack-local.sh grupo:artefacto:version
set -e
IFS=: read -r G A V <<< "$1"
OWNER=${G#com.github.}
D=/tmp/jp/$A-$V; rm -rf "$D"; mkdir -p "$D"
git clone -q "https://github.com/$OWNER/$A" "$D/src"
git -C "$D/src" checkout -q "$V"
mkdir -p "$D/out"
find "$D/src/src/main/java" -name '*.java' > "$D/files"
javac -nowarn -encoding UTF-8 -source 8 -target 8 -d "$D/out" @"$D/files"
[ -d "$D/src/src/main/resources" ] && cp -r "$D/src/src/main/resources/." "$D/out/"
M=~/.m2/repository/${G//.//}/$A/$V; mkdir -p "$M"
jar cf "$M/$A-$V.jar" -C "$D/out" .
printf '<?xml version="1.0"?>\n<project><modelVersion>4.0.0</modelVersion><groupId>%s</groupId><artifactId>%s</artifactId><version>%s</version></project>\n' "$G" "$A" "$V" > "$M/$A-$V.pom"
echo "local: $1 ($(find "$D/out" -name '*.class' | wc -l) clases)"
