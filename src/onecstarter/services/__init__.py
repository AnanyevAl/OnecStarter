"""Сценарии поверх config, domain и platform_1c. Qt здесь запрещён."""

from onecstarter.services.errors import ServicesError
from onecstarter.services.groups import GroupRemoval
from onecstarter.services.workspace import Workspace, WorkspacePaths

__all__ = ["GroupRemoval", "ServicesError", "Workspace", "WorkspacePaths"]
