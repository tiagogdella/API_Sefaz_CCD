import sys
import xmlsec
xmlsec.enable_debug_trace(True)

from app.services.manifestacao import send_awareness_event

access_key = sys.argv[1]
c_stat, x_motivo = send_awareness_event(access_key)

print(f"cStat: {c_stat}")
print(f"xMotivo: {x_motivo}")
