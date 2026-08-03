"""state_store.py (T009b): quan ly savepoint (checkpoint) cho batch ingest.

Trach nhiem duy nhat cua module nay (constitution Dieu 5): doc/ghi mot file
JSON nho ghi lai "batch index cuoi cung da hoan tat toan bo" - khong chua
logic vong lap batch/ingest (do la app/ingest.py, T009d), khong biet gi ve
Neo4j/parse/extract.

research.md ADR-002 (batch ingest + savepoint): mot lan crash giua chung
(mat dien, loi mang, exception tren mot van ban xau...) trong qua trinh
ingest ~61k van ban KHONG duoc lam mat tien do da hoan tat - lan chay lai
phai resume tu ngay sau batch cuoi cung DA XAC NHAN hoan tat, khong phai tu
dau. File checkpoint nay la nguon su that duy nhat cho "da hoan tat den
dau".

Atomic write (bat buoc theo ADR-002): ghi vao file tam trong CUNG thu muc
voi state_file, roi `os.replace(tmp, state_file)` - atomic tren ca POSIX
lan Windows (may dev cua du an nay la Windows, khong dung trick atomic-
rename kieu Unix-only nhu `os.rename` + fsync thu cong).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class IngestCheckpointStore:
    """Doc/ghi savepoint ingest qua mot file JSON tai `state_file`.

    Duong dan la tham so constructor (khong hard-code trong module) de test
    tro duoc vao temp path (constitution Dieu 4/5) - caller thuc te
    (app/ingest.py) dung mac dinh `.state/ingest_checkpoint.json` (da nam
    trong .gitignore).
    """

    def __init__(self, state_file: Path | str) -> None:
        self.state_file = Path(state_file)

    def get_last_completed_batch(self) -> int | None:
        """Tra ve index batch cuoi cung DA HOAN TAT, hoac None neu chua co
        batch nao hoan tat (chua co file, hoac file rong/hong).

        Quyet dinh ve JSON hong/corrupt (brief T009b, muc 6 - "your call"):
        COI NHU CHUA CO CHECKPOINT (tra ve None, log mot canh bao ro rang)
        thay vi raise. Ly do: file checkpoint nay CHI la mot toi uu hoa
        resume, khong phai nguon du lieu chinh (Neo4j moi la nguon su that
        cho nhung gi da duoc ghi that su, nho MERGE idempotent - xem
        upsert.py). Neu file hong (vd crash dung luc ghi truoc khi co
        atomic write, hoac bi sua tay), buoc an toan hon la ingest lai tu
        dau (cham hon nhung dung, vi MERGE idempotent nen ingest lai
        khong tao du lieu trung) thay vi raise va chan dung toan bo qua
        trinh resume (nguoc lai voi chinh muc dich cua checkpoint - "khong
        de mot loi nho chan dung tien trinh nhieu gio").
        """
        if not self.state_file.exists():
            return None
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            logger.warning(
                "Checkpoint file %s bi loi/khong doc duoc (%s) - coi nhu "
                "chua co checkpoint hop le, se bat dau ingest lai tu batch 0 "
                "(an toan vi moi upsert deu idempotent qua MERGE).",
                self.state_file,
                exc,
            )
            return None
        value = data.get("last_completed_batch") if isinstance(data, dict) else None
        if value is None:
            return None
        return int(value)

    def mark_batch_done(self, batch_index: int) -> None:
        """Ghi lai `batch_index` la batch cuoi cung DA hoan tat toan bo.

        CHI duoc goi boi caller (app/ingest.py) SAU KHI moi van ban trong
        batch da duoc upsert thanh cong khong loi - ham nay khong tu kiem
        tra dieu do, chi ghi gia tri duoc truyen vao.
        """
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_completed_batch": batch_index,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Ghi atomic: file tam CUNG thu muc voi state_file (bat buoc de
        # os.replace la atomic - khac filesystem/volume thi khong dam bao),
        # roi os.replace() - atomic tren ca Windows lan POSIX (khac
        # os.rename tren Windows, os.replace se ghi de neu dich da ton tai
        # thay vi raise FileExistsError).
        tmp_path = self.state_file.with_name(self.state_file.name + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp_path, self.state_file)
