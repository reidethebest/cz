import re, sys
log = open(sys.argv[1], errors="replace").read().splitlines()
ROW1 = "STONE COBBLESTONE LOG WOOD SAND GRAVEL GLASS WOOL BRICK".split()
ROW2 = "COAL IRON_INGOT GOLD_INGOT DIAMOND REDSTONE STICK STRING FEATHER BONE".split()
passes, cur = {}, None
for l in log:
    m = re.search(r"DD MARK (\d+) (\S+)", l)
    if m: cur = m.group(2); passes[cur] = []; continue
    m = re.search(r"DD DROP (\d+) (\S+) (\d+)", l)
    if m: passes.setdefault(cur, []).append((int(m.group(1)), m.group(2), int(m.group(3))))
for k, v in passes.items():
    print(k, [(t, a) for _, t, a in v])
ok = True
def expect(name, got, want):
    global ok
    good = got == want
    ok &= good
    print(("PASA " if good else "FALLA ") + name + ("" if good else f": esperado {want}, hubo {got}"))
A = passes.get("A", []); B = passes.get("B", []); C = passes.get("C", []); D = passes.get("D", [])
expect("A: las 9 pilas enteras de la fila 1, en orden, una vez cada una (salto rapido incluido, sin casco)",
       [(t, a) for _, t, a in A], [(t, 16) for t in ROW1])
expect("B: 1 item de cada slot de la fila 2, una vez cada uno", [(t, a) for _, t, a in B], [(t, 1) for t in ROW2])
gaps = [b[0] - a[0] for a, b in zip(B, B[1:])]
expect("B: delay respetado (>=100 ms entre tiros en el server)", all(g >= 100 for g in gaps) and len(gaps) == 8, True)
print("   gaps B (ms):", gaps)
expect("C: RedropOnReenter (COAL x3, IRON_INGOT x2)", sorted((t, a) for _, t, a in C),
       sorted([("COAL", 1)] * 3 + [("IRON_INGOT", 1)] * 2))
expect("D: modulo apagado = Q vanilla (1 item del slot apuntado)", [(t, a) for _, t, a in D], [("LOG", 1)])
print("RESULTADO:", "PASA" if ok else "FALLA")
sys.exit(0 if ok else 1)
