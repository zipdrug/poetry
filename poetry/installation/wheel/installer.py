import posixpath

from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from typing import List
from typing import NamedTuple
from typing import Optional

from .record import Record
from .record import RecordSet
from .wheel import Wheel


class Scheme(Enum):

    PURELIB = "purelib"
    PLATLIB = "platlib"
    DATA = "data"
    SCRIPTS = "scripts"
    HEADERS = "headers"


class Decision(NamedTuple):

    path: Path
    scheme: Scheme
    record: Optional[Record]


class SchemeDecisionMaker:
    def __init__(self, wheel: Wheel, root_scheme: Scheme) -> None:
        self._wheel = wheel
        self._records = wheel.records
        self._data_name = wheel.data_name
        self._root_scheme = root_scheme

    def decide(self) -> List[Decision]:
        decisions = []
        for path in self._wheel.files:
            decisions.append(self.decide_for_path(path))

        return decisions

    def decide_for_path(self, path: Path) -> Decision:
        if (
            not posixpath.commonprefix([self._data_name, path.as_posix()])
            == self._data_name
        ):
            return Decision(path, self._root_scheme, self._records.record(path))

        left, right = posixpath.split(path)
        while left != self._data_name:
            left, right = posixpath.split(left)

        scheme_name = right
        # TODO: raise an error if scheme is invalid

        return Scheme.__members__[scheme_name]


class SchemeDecisionHandler:
    def handle_decision(
        self, decision: Decision, io: BinaryIO
    ) -> Optional[List[Record]]:
        raise NotImplementedError()


class Installer:
    def __init__(self, name: str) -> None:
        self._name = name

    def install(self, wheel: Wheel, handler: SchemeDecisionHandler) -> None:
        metadata = wheel.metadata

        # TODO: Check wheel format version
        root_scheme = Scheme.PURELIB
        if not metadata["Root-Is-Purelib"]:
            root_scheme = Scheme.PLATLIB

        decisions = self.get_decisions(wheel, root_scheme)

        records = RecordSet(wheel.records.records)
        for decision in decisions:
            new_records = handler.handle_decision(
                decision, wheel.open(decision.path.as_posix())
            )
            if new_records:
                for new_record in new_records:
                    records.add(new_record)

        # Write the RECORD file with new records
        handler.handle_decision(
            Decision(Path(wheel.dist_info_name, "RECORD"), Scheme.PURELIB, None),
            BytesIO(records.content.encode()),
        )

    def get_decisions(self, wheel: Wheel, root_scheme: Scheme) -> List[Decision]:
        decision_maker = SchemeDecisionMaker(wheel, root_scheme)

        return decision_maker.decide()
