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


def lan_discover(timeout=2.0):
    iface = local_ip()
    recv = _recv_socket(timeout, True, iface)
    send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    if iface:
        send.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface))
    scan = json.dumps(build_message("scan", {"account_topic": "reserve"})).encode("utf-8")
    found, seen = [], set()
    try:
        send.sendto(scan, (MULTICAST_ADDR, SCAN_PORT))
        while True:
            try:
                raw, _ = recv.recvfrom(2048)
            except socket.timeout:
                break
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
