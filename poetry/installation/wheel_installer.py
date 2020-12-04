from pathlib import Path
from typing import BinaryIO
from typing import List
from typing import Optional

from poetry.utils.env import Env

from .wheel.exceptions import InvalidRecordHash
from .wheel.installer import Decision
from .wheel.installer import Installer
from .wheel.installer import SchemeDecisionHandler
from .wheel.record import Record
from .wheel.wheel import Wheel


class DecisionHandler(SchemeDecisionHandler):
    def __init__(self, env: Env, check_hashes: bool = True) -> None:
        self._env = env
        self._check_hashes = check_hashes

    def handle_decision(
        self, decision: Decision, io: BinaryIO
    ) -> Optional[List[Record]]:
        scheme = decision.scheme
        destination = Path(self._env.paths[scheme.value], decision.path)
        content = io.read()

        if self._check_hashes and decision.record:
            if not decision.record.check(content):
                raise InvalidRecordHash(decision.record)

        print(decision)
        print(destination)


class WheelInstaller:
    def __init__(self, env: Env, check_hashes: bool = True) -> None:
        self._env = env
        self._installer = Installer("poetry")
        self._decision_handler = DecisionHandler(self._env, check_hashes=check_hashes)

    def install(self, wheel: Wheel) -> None:
        self._installer.install(wheel, self._decision_handler)
