"""Runtime guard: no outbound Internet sockets, DNS, telemetry or image uploads."""
import sys


def install_network_guard():
    def audit(event, args):
        if event == "socket.connect":
            address = args[1]
            if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", 8991):
                raise PermissionError("Charlie desktop blocks external network connections")
        elif event == "socket.getaddrinfo":
            if args[0] not in ("127.0.0.1", None):
                raise PermissionError("Charlie desktop blocks external DNS lookups")
        elif event == "socket.bind":
            address = args[1]
            if isinstance(address, tuple) and address[0] != "127.0.0.1":
                raise PermissionError("Charlie services bind only to loopback")
    sys.addaudithook(audit)
