import re
import zipfile

from email.message import Message
from email.parser import BytesParser
from pathlib import Path
from typing import BinaryIO
from typing import List

from poetry.installation.wheel.record import RecordSet

from ._typing import GenericPath


class Wheel:

    NAME_REGEX = re.compile(
        r"""
        ^
        (?P<namever>(?P<name>.+?)(-(?P<ver>\d.+?))?)
        ((-(?P<build>\d.*?))?-(?P<pyver>.+?)-(?P<abi>.+?)-(?P<plat>.+?)
        \.whl|\.dist-info)
        $
        """,
        re.VERBOSE,
    )

    def __init__(self, path: GenericPath) -> None:
        self._path = Path(path)
        self._file_info = self.NAME_REGEX.match(self._path.name)
        self._info = None
        self._metadata = None
        self._zip = zipfile.ZipFile(self._path)

    @property
    def name(self) -> str:
        return self._file_info.group("name")

    @property
    def version(self) -> str:
        return self._file_info.group("ver")

    @property
    def dist_info_name(self) -> str:
        return f"{self.name}-{self.version}.dist-info"

    @property
    def data_name(self) -> str:
        return f"{self.name}-{self.version}.data"

    @property
    def info(self) -> Message:
        if self._info is not None:
            return self._info

        self._info = self.parse_metadata(self.read_from_dist_info("WHEEL"))

        return self._info

    @property
    def metadata(self) -> Message:
        if self._metadata is not None:
            return self._metadata

        self._metadata = self.parse_metadata(self.read_from_dist_info("METADATA"))

        return self._metadata

    @property
    def records(self) -> RecordSet:
        return RecordSet.from_content(self.read_from_dist_info("RECORD"))

    @property
    def files(self) -> List[Path]:
        return [Path(name) for name in self._zip.namelist()]

    @classmethod
    def parse_metadata(cls, raw_metadata: bytes) -> Message:
        parser = BytesParser()

        return parser.parsebytes(raw_metadata)

    def read_from_dist_info(self, path: str) -> bytes:
        return self.read(f"{self.dist_info_name}/{path}")

    def read(self, path: str) -> bytes:
        return self._zip.read(path)

    def open(self, path: str) -> BinaryIO:
        return self._zip.open(path)
