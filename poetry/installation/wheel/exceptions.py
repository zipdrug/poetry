from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .record import Record


class WheelException(Exception):

    pass


class InvalidRecordHash(WheelException):
    def __init__(self, record: "Record") -> None:
        super().__init__("Hash mismatch for file {}".format(record.path.as_posix()))
