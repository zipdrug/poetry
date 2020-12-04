import hashlib
import json
import tarfile
import zipfile

from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

import tomlkit

from poetry.core.packages import dependency_from_pep_508
from poetry.core.packages.dependency import Dependency
from poetry.core.packages.utils.link import Link
from poetry.utils.helpers import temporary_directory

from .chooser import InvalidWheelName
from .chooser import Wheel


if TYPE_CHECKING:
    from typing import List
    from typing import Optional

    from poetry.config.config import Config
    from poetry.utils.env import Env


class BuildBackend:
    def __init__(self, module: ModuleType, name: Optional[str] = None) -> None:
        self._module = module
        self._name = name
        self._backend = module

        if self._name:
            self._backend = getattr(self._backend, self._name)

    def build_wheel(
        self,
        wheel_directory: str,
        config_settings: Optional[Dict[str, Any]] = None,
        metadata_directory: Optional[str] = None,
    ) -> str:
        return self._backend.build_wheel(
            wheel_directory,
            config_settings=config_settings,
            metadata_directory=metadata_directory,
        )

    def build_wheel(
        self,
        sdist_directory: str,
        config_settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self._backend.build_sdist(
            sdist_directory, config_settings=config_settings
        )

    def get_requires_for_build_wheel(
        self, config_settings: Optional[Dict[str, Any]]
    ) -> List[Dependency]:
        return [
            dependency_from_pep_508(r)
            for r in self._backend.get_requires_for_build_wheel()
        ]

    def get_requires_for_build_sdist(
        self, config_settings: Optional[Dict[str, Any]]
    ) -> List[Dependency]:
        return [
            dependency_from_pep_508(r)
            for r in self._backend.get_requires_for_build_sdist()
        ]

    def __repr__(self) -> str:
        if not self._name:
            return f"{self.__class__.__name__}('{self._module.__name__}')"

        return f"{self.__class__.__name__}('{self._module.__name__}', '{self._name}')"


class BuildSystem:
    def __init__(
        self, requires: List[str], backend: str, backend_path: Optional[str] = None
    ) -> None:
        self._requires = [dependency_from_pep_508(r) for r in requires]
        self._backend = backend
        self._backend_path = backend_path

        backend_parts = backend.split(":")
        self._backend_module = backend_parts[0]
        self._backend_name = None

        if len(backend_parts) > 1:
            self._backend_name = backend_parts[1]

    def load_backend(self) -> BuildBackend:
        module = import_module(f"{self._backend_module}")

        return BuildBackend(module, name=self._backend_name)


class SdistCooker:

    DEFAULT_BUILD_SYSTEM = BuildSystem(
        ["setuptools", "wheel"], "setuptools.build_meta:__legacy__"
    )

    @classmethod
    def get_build_system(
        cls, archive: Union[zipfile.ZipFile, tarfile.TarFile]
    ) -> BuildSystem:
        # Trying to find a build backend inside the archive,
        # defaulting to a standard one if none is found
        pyproject = Path(
            cls.get_sdist_directory(Path(archive.name).name), "pyproject.toml"
        ).as_posix()
        if pyproject not in archive.getnames():
            return cls.DEFAULT_BUILD_SYSTEM

        if isinstance(archive, zipfile.ZipFile):
            with archive.open(pyproject) as f:
                pyproject_content = tomlkit.parse(f.read().decode("utf-8"))
        else:
            pyproject_content = tomlkit.parse(
                archive.extractfile(archive.getmember(pyproject)).read().decode("utf-8")
            )

        if "build-system" not in pyproject_content:
            return cls.DEFAULT_BUILD_SYSTEM

        return BuildSystem(
            pyproject_content["build-system"]["requires"],
            pyproject_content["build-system"]["build-backend"],
            pyproject_content["build-system"].get("backend-path"),
        )

    @classmethod
    def get_sdist_directory(cls, archive_name: str) -> str:
        suffix = Path(archive_name).suffix

        if suffix != ".zip":
            if suffix == ".bz2":
                suffixes = path.suffixes
                if len(suffixes) > 1 and suffixes[-2] == ".tar":
                    suffix = ".tar.bz2"
            else:
                suffix = ".tar.gz"

        return archive_name.rstrip(suffix)

    def cook(self, sdist: Path) -> Path:
        suffix = sdist.suffix

        if suffix == ".zip":
            context = zipfile.ZipFile
        else:
            if suffix == ".bz2":
                suffixes = path.suffixes
                if len(suffixes) > 1 and suffixes[-2] == ".tar":
                    suffix = ".tar.bz2"
            else:
                suffix = ".tar.gz"

            context = tarfile.open

        with context(sdist.as_posix()) as archive:
            build_system = self.get_build_system(archive)
            backend = build_system.load_backend()

            print(backend)


class Chef:
    def __init__(self, config, env):  # type: (Config, Env) -> None
        self._config = config
        self._env = env
        self._cache_dir = (
            Path(config.get("cache-dir")).expanduser().joinpath("artifacts")
        )

    def prepare(self, archive):  # type: (Path) -> Path
        return archive

    def prepare_sdist(self, archive):  # type: (Path) -> Path
        return archive

    def prepare_wheel(self, archive):  # type: (Path) -> Path
        return archive

    def should_prepare(self, archive):  # type: (Path) -> bool
        return not self.is_wheel(archive)

    def is_wheel(self, archive):  # type: (Path) -> bool
        return archive.suffix == ".whl"

    def get_cached_archive_for_link(self, link):  # type: (Link) -> Optional[Link]
        # If the archive is already a wheel, there is no need to cache it.
        if link.is_wheel:
            pass

        archives = self.get_cached_archives_for_link(link)

        if not archives:
            return link

        candidates = []
        for archive in archives:
            if not archive.is_wheel:
                candidates.append((float("inf"), archive))
                continue

            try:
                wheel = Wheel(archive.filename)
            except InvalidWheelName:
                continue

            if not wheel.is_supported_by_environment(self._env):
                continue

            candidates.append(
                (wheel.get_minimum_supported_index(self._env.supported_tags), archive),
            )

        if not candidates:
            return link

        return min(candidates)[1]

    def get_cached_archives_for_link(self, link):  # type: (Link) -> List[Link]
        cache_dir = self.get_cache_directory_for_link(link)

        archive_types = ["whl", "tar.gz", "tar.bz2", "bz2", "zip"]
        links = []
        for archive_type in archive_types:
            for archive in cache_dir.glob("*.{}".format(archive_type)):
                links.append(Link(archive.as_uri()))

        return links

    def get_cache_directory_for_link(self, link):  # type: (Link) -> Path
        key_parts = {"url": link.url_without_fragment}

        if link.hash_name is not None and link.hash is not None:
            key_parts[link.hash_name] = link.hash

        if link.subdirectory_fragment:
            key_parts["subdirectory"] = link.subdirectory_fragment

        key_parts["interpreter_name"] = self._env.marker_env["interpreter_name"]
        key_parts["interpreter_version"] = "".join(
            self._env.marker_env["interpreter_version"].split(".")[:2]
        )

        key = hashlib.sha256(
            json.dumps(
                key_parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode("ascii")
        ).hexdigest()

        split_key = [key[:2], key[2:4], key[4:6], key[6:]]

        return self._cache_dir.joinpath(*split_key)
