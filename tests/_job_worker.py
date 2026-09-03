"""Worker de un solo job, para el test de caída de proceso de PR-03.

No es parte de `spectre`: el guion bajo lo mantiene fuera de la colección de
pytest. `test_jobs.py` lo lanza como proceso aparte y lo mata a mitad del
handler para comprobar que el runner reanuda sin perder ni duplicar.

Uso: python tests/_job_worker.py <db_path> <marker_path>

El handler inserta una fila en `_efectos`, escribe el marker (señal para el
test de que ya entró al handler) y se cuelga. El test mata el proceso acá:
la fila insertada está sin commitear y se descarta; el reclamo del job sí
quedó commiteado.
"""

import sys
import time
from pathlib import Path

from spectre.db import connect
from spectre.jobs import Runner


def main() -> None:
    db_path, marker = sys.argv[1], Path(sys.argv[2])
    conn = connect(db_path)

    def handler_lento(c, job):
        c.execute(
            "INSERT INTO _efectos (job_id, nota) VALUES (?, ?)",
            (job.id, job.payload["nota"]),
        )
        marker.write_text("dentro del handler", encoding="utf-8")
        time.sleep(60)  # el test manda SIGKILL/TerminateProcess acá

    runner = Runner(conn)
    runner.registrar("lento", handler_lento)
    runner.run()


if __name__ == "__main__":
    main()
