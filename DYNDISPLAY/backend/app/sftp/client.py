import os
import paramiko

from app.core.config import get_settings

settings = get_settings()


class SFTPClient:
    def __init__(self):
        self.host = settings.SFTP_HOST
        self.port = settings.SFTP_PORT
        self.username = settings.SFTP_USERNAME
        self.password = settings.SFTP_PASSWORD
        self.root_path = settings.SFTP_ROOT_PATH
        self._transport = None
        self._sftp = None

    def connect(self):
        self._transport = paramiko.Transport((self.host, self.port))
        self._transport.connect(username=self.username, password=self.password)
        self._sftp = paramiko.SFTPClient.from_transport(self._transport)

    def disconnect(self):
        if self._sftp:
            self._sftp.close()
        if self._transport:
            self._transport.close()
        self._sftp = None
        self._transport = None

    def _ensure_remote_dir(self, remote_dir: str):
        if not self._sftp:
            raise ConnectionError("SFTP not connected")
        parts = remote_dir.strip("/").split("/")
        current = ""
        for part in parts:
            current = f"{current}/{part}" if current else f"/{part}"
            try:
                self._sftp.stat(current)
            except FileNotFoundError:
                self._sftp.mkdir(current)

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        if not self._sftp:
            raise ConnectionError("SFTP not connected")
        remote_dir = os.path.dirname(remote_path)
        self._ensure_remote_dir(remote_dir)
        self._sftp.put(local_path, remote_path)
        return True

    def upload_bytes(self, data: bytes, remote_path: str) -> bool:
        if not self._sftp:
            raise ConnectionError("SFTP not connected")
        remote_dir = os.path.dirname(remote_path)
        self._ensure_remote_dir(remote_dir)
        with self._sftp.open(remote_path, "wb") as f:
            f.write(data)
        return True

    def open_remote(self, remote_path: str, mode: str = "rb"):
        if not self._sftp:
            raise ConnectionError("SFTP not connected")
        return self._sftp.open(remote_path, mode)

    def remove_file(self, remote_path: str) -> bool:
        if not self._sftp:
            raise ConnectionError("SFTP not connected")
        try:
            self._sftp.remove(remote_path)
            return True
        except FileNotFoundError:
            return False

    def copy_file(self, src: str, dst: str) -> bool:
        if not self._sftp:
            raise ConnectionError("SFTP not connected")
        remote_dir = os.path.dirname(dst)
        self._ensure_remote_dir(remote_dir)
        with self._sftp.open(src, "rb") as r, self._sftp.open(dst, "wb") as w:
            while True:
                chunk = r.read(1024 * 1024)
                if not chunk:
                    break
                w.write(chunk)
        return True

    def remote_file_size(self, remote_path: str) -> int | None:
        if not self._sftp:
            raise ConnectionError("SFTP not connected")
        try:
            stat = self._sftp.stat(remote_path)
            return stat.st_size
        except FileNotFoundError:
            return None

    def list_files(self, path: str = "/") -> list[str]:
        if not self._sftp:
            raise ConnectionError("SFTP not connected")
        return self._sftp.listdir(path)

    def exists(self, path: str) -> bool:
        if not self._sftp:
            raise ConnectionError("SFTP not connected")
        try:
            self._sftp.stat(path)
            return True
        except FileNotFoundError:
            return False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
