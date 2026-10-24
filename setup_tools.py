"""Скачивает Eclipse JDT LS и плагин отладки Microsoft (java-debug) в ./tools"""
import re
import sys
import tarfile
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

TOOLS = Path(__file__).parent / "tools"
MAVEN = "https://repo1.maven.org/maven2/com/microsoft/java/com.microsoft.java.debug.plugin"
JDTLS = "https://download.eclipse.org/jdtls/snapshots/jdt-language-server-latest.tar.gz"


def get(url: str) -> bytes:
    print("↓", url)
    with urllib.request.urlopen(url, timeout=180) as r:
        return r.read()


def main() -> None:
    TOOLS.mkdir(exist_ok=True)

    meta = get(f"{MAVEN}/maven-metadata.xml").decode()
    m = re.search(r"<release>([^<]+)</release>", meta) or re.search(r"<latest>([^<]+)</latest>", meta)
    ver = m.group(1) if m else "0.53.1"
    jar = get(f"{MAVEN}/{ver}/com.microsoft.java.debug.plugin-{ver}.jar")
    zipfile.ZipFile(BytesIO(jar)).testzip()  # проверка целостности
    (TOOLS / f"com.microsoft.java.debug.plugin-{ver}.jar").write_bytes(jar)
    print("✔ java-debug plugin", ver)

    if not (TOOLS / "jdtls" / "bin" / "jdtls").exists():
        data = get(JDTLS)
        dest = TOOLS / "jdtls"
        dest.mkdir(exist_ok=True)
        with tarfile.open(fileobj=BytesIO(data), mode="r:gz") as t:
            try:
                t.extractall(dest, filter="data")
            except TypeError:  # старый Python без filter=
                t.extractall(dest)
    print("✔ JDT LS")
    print("Готово. Теперь: cd server && uvicorn main:app --port 8000")


if __name__ == "__main__":
    sys.exit(main())
