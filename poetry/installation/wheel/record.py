import base64
import csv
import hashlib

from io import StringIO
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

from ._typing import GenericPath


class RecordSet:
    def __init__(self, records: Optional[List["Record"]] = None) -> None:
        self._records: Dict[Path, Record] = {}

        if records is None:
            records = []

        for record in records:
            self.add(record)

    @property
    def records(self) -> List["Record"]:
        return list(self._records.values())

    @property
    def content(self) -> str:
        content = StringIO()
        writer = csv.writer(content, delimiter=",", quotechar='"', lineterminator="\n")
        for record in sorted(self._records.values(), key=lambda r: r.path.as_posix()):
            writer.writerow([record.path.as_posix(), record.hash_value, record.size])

        return content.getvalue()

    @classmethod
    def from_content(cls, content: Union[str, bytes]) -> "RecordSet":
        if isinstance(content, bytes):
            content = content.decode()

        content = StringIO(content)

        records = cls()
        reader = csv.reader(content, delimiter=",", quotechar='"', lineterminator="\n")
        for row in reader:
            records.add(Record(*row))

        return records

    def add(self, record: "Record") -> None:
        self._records[record.path] = record

    def remove(self, record: "Record") -> None:
        del self._records[record.path]

    def record(self, path: GenericPath) -> "Record":
        path = Path(path)

        if path not in self._records:
            raise ValueError(
                'Record for path "{}" does not exist'.format(path.as_posix())
            )

        return self._records[path]

    def write_to(self, path: GenericPath) -> None:
        path.write_text(self.content)


class Record:
    def __init__(
        self,
        path: GenericPath,
        hash_value: Optional[str] = None,
        size: Optional[int] = None,
    ) -> None:
        self._path = Path(path)
        self._size = size

        if hash_value:
            self._hash_name, self._hash_value = hash_value.split("=", 1)
        else:
            self._hash_name, self._hash_value = None, None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def hash_value(self) -> Optional[str]:
        return self._hash_value

    @property
    def size(self) -> Optional[int]:
        return self._size

    def check(self, data: bytes) -> bool:
        if not self._hash_name:
            return True

        hashsum = hashlib.new(self._hash_name, data).digest()
        encoded_hash = base64.urlsafe_b64encode(hashsum).decode("ascii").rstrip("=")

        return encoded_hash == self._hash_value

    def __hash__(self) -> int:
        return hash(self._path.as_posix())

    def __repr__(self) -> str:
        return "{}({}, {}, {})".format(
            self.__class__.__name__, self._path.as_posix(), self._hash_value, self._size
        )
