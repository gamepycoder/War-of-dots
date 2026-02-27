from socket import AF_INET, IPPROTO_TCP, SOCK_STREAM, TCP_NODELAY, socket

####### https://docs.python.org/3/library/socket.html#socket.socket.sendfile #######
# socket.gethostbyname(str(socket.gethostname()))#

HEADER, FORMAT = 64, "utf-8"


class Client:
    def __init__(self, servip: str, port: int) -> None:
        self.servip = servip
        self.port = port

    def connect(self) -> None:
        self.client = socket(AF_INET, SOCK_STREAM)
        self.client.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
        ADDR = (self.servip, self.port)
        self.client.connect(ADDR)

    def send(self, msg: str) -> None:
        message = msg.encode(FORMAT)
        msg_length = len(message)
        send_length = str(msg_length).encode(FORMAT)
        send_length += b" " * (HEADER - len(send_length))
        self.client.sendall(send_length)
        self.client.sendall(message)

    def rcv(self) -> str:
        msg_length = self.client.recv(HEADER).decode(FORMAT)
        total_received = 0
        if msg_length:
            msg = []
            while total_received < int(msg_length):
                data = self.client.recv(int(msg_length))
                total_received += len(data)
                msg.append(data)
            return b"".join(msg).decode(FORMAT)
        return ""

    def close(self) -> None:
        self.client.close()


class Server:
    def __init__(self, ip: str, port: int) -> None:
        self.ip = ip
        self.port = port

    def start(self) -> None:
        self.server = socket(AF_INET, SOCK_STREAM)
        ADDR = (self.ip, self.port)
        self.server.bind(ADDR)
        self.conns: list[socket] = []

    def lsn(self, num_conns: int = 0) -> None:
        if num_conns > 0:
            self.server.listen(num_conns)
        else:
            self.server.listen()

    def accept(self) -> tuple[socket, str]:
        conn, addr = self.server.accept()
        conn.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
        self.conns.append(conn)
        return conn, addr

    def send(self, conns: list[socket], msg: str) -> None:
        message = msg.encode(FORMAT)
        msg_length = len(message)
        send_length = str(msg_length).encode(FORMAT)
        send_length += b" " * (HEADER - len(send_length))
        for conn in conns:
            conn.sendall(send_length)
            conn.sendall(message)

    def rcv(self, conn: socket) -> str:
        msg_length = conn.recv(HEADER).decode(FORMAT)
        total_received = 0
        if msg_length:
            msg = []
            while total_received < int(msg_length):
                data = conn.recv(int(msg_length))
                total_received += len(data)
                msg.append(data)
            return b"".join(msg).decode(FORMAT)
        return ""

    def close(self, conn: socket) -> None:
        conn.close()
        self.conns.remove(conn)
