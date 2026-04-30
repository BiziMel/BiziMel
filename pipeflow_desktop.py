import os
import platform
import socket
import subprocess
import threading
import webbrowser
from contextlib import closing

from app import app
from version_info import APP_NAME, APP_VERSION


def port_is_free(port):
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.connect_ex(("localhost", port)) != 0


def choose_port():
    preferred_port = int(os.environ.get("PIPEFLOW_PORT", "5050"))

    if port_is_free(preferred_port):
        return preferred_port

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("localhost", 0))
        return sock.getsockname()[1]


def open_pipeflow(port):
    url = f"http://localhost:{port}"

    if platform.system() == "Darwin":
        subprocess.Popen(["open", url])
    elif platform.system() == "Windows":
        os.startfile(url)
    else:
        webbrowser.open_new(url)


if __name__ == "__main__":
    print(f"{APP_NAME} {APP_VERSION}")
    port = choose_port()
    if os.environ.get("PIPEFLOW_NO_BROWSER") != "1":
        threading.Timer(1.0, open_pipeflow, args=(port,)).start()
    app.run(host="localhost", port=port, debug=False, use_reloader=False)
