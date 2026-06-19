"""Sonda de diagnóstico da API LAN Govee (unicast).

Uso: python probe.py <ip>

Manda, direto no IP (sem multicast):
  - devStatus  -> porta 4003 (controle)
  - scan       -> porta 4001 (descoberta), unicast
E escuta respostas na porta 4002 por alguns segundos.

Se NADA chegar: a API LAN do dispositivo não está respondendo unicast
(LAN Control off, modelo sem suporte, ou firewall/rede bloqueando 4002).
Se chegar resposta do scan/devStatus: a API LAN está viva e o problema é
outro (payload de cor, multicast só na descoberta, etc.).
"""

import json
import socket
import sys
import time

SCAN_PORT = 4001
RECV_PORT = 4002
CONTROL_PORT = 4003


def main(ip):
    recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        recv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        pass
    recv.bind(("", RECV_PORT))
    recv.settimeout(0.5)

    send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    devstatus = json.dumps({"msg": {"cmd": "devStatus", "data": {}}}).encode()
    scan = json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}).encode()

    print(f"Sondando {ip} (unicast) por 6s...")
    deadline = time.monotonic() + 6.0
    next_send = 0.0
    got = 0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_send:
            send.sendto(devstatus, (ip, CONTROL_PORT))
            send.sendto(scan, (ip, SCAN_PORT))  # scan unicast direto
            next_send = now + 1.0
            print("  -> enviei devStatus(4003) e scan(4001)")
        try:
            raw, addr = recv.recvfrom(2048)
            got += 1
            print(f"  <- RESPOSTA de {addr}: {raw.decode(errors='replace')}")
        except socket.timeout:
            pass

    send.close()
    recv.close()
    print(f"\nTotal de respostas: {got}")
    if got == 0:
        print("=> Nada respondeu unicast. API LAN não está acessível neste IP.")
    else:
        print("=> API LAN responde unicast. O problema está no controle/multicast.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("uso: python probe.py <ip>")
        sys.exit(1)
    main(sys.argv[1])
