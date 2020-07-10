import os

from typing import TYPE_CHECKING
from typing import cast

from cleo.helpers import argument

from ..init import InitCommand


if TYPE_CHECKING:
    from pathlib import Path

    from poetry.console.commands.update import UpdateCommand
    from poetry.packages.project_package import ProjectPackage
    from poetry.repositories.installed_repository import InstalledRepository


class PluginInstallCommand(InitCommand):

    name = "plugin install"

    description = "Install a new plugin."

    arguments = [
        argument("plugins", "The names of the plugins to install.", multiple=True)
    ]

    def handle(self) -> int:
        from pathlib import Path

        from cleo.io.inputs.string_input import StringInput
        from cleo.io.io import IO

        from poetry.factory import Factory
        from poetry.installation.installer import Installer
        from poetry.packages.locker import Locker
        from poetry.packages.project_package import ProjectPackage
        from poetry.puzzle.provider import Provider
        from poetry.repositories.installed_repository import InstalledRepository
        from poetry.repositories.pool import Pool
        from poetry.repositories.pypi_repository import PyPiRepository
        from poetry.repositories.repository import Repository
        from poetry.utils.env import EnvManager

        plugins = self.argument("plugins")
        plugins = self._determine_requirements(plugins)

        # Plugins should be installed in the system env to be globally available
        system_env = EnvManager.get_system_env()
        installed_repository = InstalledRepository.load(
            system_env, with_dependencies=True
        )
        repository = Repository()

        root_package = None
        for package in installed_repository.packages:
            if package.name in Provider.UNSAFE_PACKAGES:
                continue

            if package.name == "poetry":
                root_package = ProjectPackage(package.name, package.version)
                for dependency in package.requires:
                    root_package.add_dependency(dependency)

                continue

            repository.add_package(package)

        plugin_names = []
        for plugin in plugins:
            plugin_name = plugin.pop("name")
            root_package.add_dependency(Factory.create_dependency(plugin_name, plugin))
            plugin_names.append(plugin_name)

        root_package.python_versions = ".".join(
            str(v) for v in system_env.version_info[:3]
        )

        pool = Pool()
        pool.add_repository(PyPiRepository())

        env_dir = Path(
            os.getenv("POETRY_HOME") if os.getenv("POETRY_HOME") else system_env.path
        )
        self.create_pyproject_from_package(root_package, env_dir)

        locker = Locker(env_dir.joinpath("poetry.lock"), {})
        if not locker.is_locked():
            locker.set_lock_data(root_package, repository.packages)

        installer = Installer(
            self._io,
            system_env,
            root_package,
            locker,
            pool,
            self.poetry.config,
            repository,
        )
        installer.remove_untracked(False)

        update_command: "UpdateCommand" = cast(
            "UpdateCommand", self.application.find("update")
        )
        update_command.set_poetry(Factory().create_poetry(env_dir))
        update_command.set_env(system_env)
        update_command.set_installer(installer)
        update_command.run(
            IO(
                StringInput("update " + " ".join(plugin_names)),
                self._io.output,
                self._io.error_output,
            )
        )

    def create_pyproject_from_package(
        self, package: "ProjectPackage", path: "Path"
    ) -> None:
        import tomlkit

        from poetry.layouts.layout import POETRY_DEFAULT

        pyproject = tomlkit.loads(POETRY_DEFAULT)
        content = pyproject["tool"]["poetry"]

        content["name"] = package.name
        content["version"] = package.version.text
        content["description"] = package.description
        content["authors"] = package.authors

        dependency_section = content["dependencies"]
        dependency_section["python"] = package.python_versions

        for dep in package.requires:
            constraint = tomlkit.inline_table()
            if dep.is_vcs():
                constraint[dep.vcs] = dep.source_url

                if dep.reference:
                    constraint["rev"] = dep.reference
            elif dep.is_file() or dep.is_directory():
                constraint["path"] = dep.source_url
            else:
                constraint["version"] = str(dep.constraint)

            if dep.extras:
                constraint["extras"] = list(sorted(dep.extras))

            dependency_section[dep.name] = constraint

        path.joinpath("pyproject.toml").write_text(
            pyproject.as_string(), encoding="utf-8"
        )
