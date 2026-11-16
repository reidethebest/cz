"""Writes mc/servers.dat with one entry: DragDropE2E -> 127.0.0.1 (uncompressed NBT, as Minecraft reads it)."""
import struct, sys
def s(t): b = t.encode(); return struct.pack(">H", len(b)) + b
def tag_str(name, v): return b"\x08" + s(name) + s(v)
entry = tag_str("name", "DragDropE2E") + tag_str("ip", "127.0.0.1") + b"\x00"
data = b"\x0a" + s("") + b"\x09" + s("servers") + b"\x0a" + struct.pack(">i", 1) + entry + b"\x00"
open(sys.argv[1], "wb").write(data)
