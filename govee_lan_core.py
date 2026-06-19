"""Govee H6046 via API LAN local (UDP). Apenas stdlib."""

import json
import socket

MULTICAST_ADDR = "239.255.255.250"
SCAN_PORT = 4001
RECV_PORT = 4002
CONTROL_PORT = 4003


def build_message(cmd, data):
    return {"msg": {"cmd": cmd, "data": data}}


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((MULTICAST_ADDR, SCAN_PORT))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def local_ips():
    """Todos os IPv4 locais. Em PCs com várias NICs (Hyper-V/WSL/VPN) o scan
    precisa sair por todas as interfaces — não só a da rota padrão — senão o
    multicast pode ir pela placa errada e a lâmpada nunca recebe o scan."""
    ips = set()
    primary = local_ip()
    if primary:
        ips.add(primary)
    try:
        _, _, addrs = socket.gethostbyname_ex(socket.gethostname())
        ips.update(a for a in addrs if not a.startswith("127."))
    except OSError:
        pass
    return list(ips)


def send_command(ip, cmd, data):
    msg = json.dumps(build_message(cmd, data)).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(msg, (ip, CONTROL_PORT))
    finally:
        sock.close()


def _recv_socket(timeout, join_group, iface):
    recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        recv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        pass
    recv.bind(("", RECV_PORT))
    if join_group and iface:
        mreq = socket.inet_aton(MULTICAST_ADDR) + socket.inet_aton(iface)
        recv.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    recv.settimeout(timeout)
    return recv


def lan_discover(timeout=8.0, scan_interval=1.0):
    """Descobre dispositivos Govee na LAN.

    Reenvia o pacote de scan a cada ``scan_interval`` segundos durante ``timeout``
    segundos no total. UDP não garante entrega, então um único scan pode se perder
    (ou a resposta do dispositivo) — reenviar é o que torna a descoberta confiável.
    """
    import time

    ifaces = local_ips()
    recv = _recv_socket(0.5, True, ifaces[0] if ifaces else None)
    # Junta o grupo multicast em cada interface, para receber a resposta venha
    # ela de onde vier.
    for ip in ifaces:
        try:
            mreq = socket.inet_aton(MULTICAST_ADDR) + socket.inet_aton(ip)
            recv.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except OSError:
            pass
    send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    scan = json.dumps(build_message("scan", {"account_topic": "reserve"})).encode("utf-8")

    def broadcast():
        # Manda o scan por TODAS as interfaces; sem isso o multicast sai só
        # pela rota padrão e some em placas virtuais (Hyper-V/WSL/VPN).
        targets = ifaces or [None]
        for ip in targets:
            try:
                if ip:
                    send.setsockopt(
                        socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip)
                    )
                send.sendto(scan, (MULTICAST_ADDR, SCAN_PORT))
            except OSError:
                pass

    found, seen = [], set()
    deadline = time.monotonic() + timeout
    next_scan = 0.0
    try:
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_scan:
                broadcast()
                next_scan = now + scan_interval
            try:
                raw, _ = recv.recvfrom(2048)
            except socket.timeout:
                continue
            data = json.loads(raw.decode("utf-8")).get("msg", {}).get("data", {})
            ip = data.get("ip")
            if ip and ip not in seen:
                seen.add(ip)
                found.append({"ip": ip, "sku": data.get("sku"), "device": data.get("device")})
    finally:
        send.close()
        recv.close()
    return found


def query_status(ip, timeout=2.0):
    recv = _recv_socket(timeout, False, None)
    try:
        send_command(ip, "devStatus", {})
        try:
            raw, _ = recv.recvfrom(2048)
        except socket.timeout:
            return None
        return json.loads(raw.decode("utf-8")).get("msg", {}).get("data", {})
    finally:
        recv.close()
