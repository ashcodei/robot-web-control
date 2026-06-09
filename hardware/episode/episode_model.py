"""
Episode Orchestrator Data Models
编排器数据模型

Defines the data structures for multi-component episode orchestration.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any

from app_core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ActionGroup:
    """Metadata for an action group (UI-level concept)."""
    name: str = "Group"
    collapsed: bool = False
    parent_group_id: str = ""  # empty = top-level, else nested inside parent

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {'name': self.name, 'collapsed': self.collapsed}
        if self.parent_group_id:
            d['parent_group_id'] = self.parent_group_id
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'ActionGroup':
        return cls(
            name=data.get('name', 'Group'),
            collapsed=data.get('collapsed', False),
            parent_group_id=data.get('parent_group_id', ''),
        )


@dataclass
class ComponentAction:
    """A single component action within an episode."""
    component: str = "dual_arm"          # "dual_arm", "lebai", "wok"
    action_type: str = "play_step"       # "play_step", "replay_trajectory", "wok_command"
    recording_file: str = ""             # path to JSON file
    step_index: int = 0                  # which step (dual_arm only)
    wok_command: str = ""                # "working_pos", "pour_pos", etc.
    dependency: str = "none"             # "none", "starts_with", "starts_after"
    dependency_target: str = ""          # component name of dependency
    parameters: Dict[str, Any] = field(default_factory=dict)  # extra params (sauce pulse, recipe id)
    group_id: str = ""                   # group membership (empty = ungrouped)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'ComponentAction':
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    def display_name(self) -> str:
        """Human-readable summary for listbox display."""
        comp = self.component.replace("_", " ").title()
        if self.action_type == "wok_command":
            detail = self.wok_command.replace("_", " ").title()
            if self.parameters:
                param_str = ", ".join(f"{k}={v}" for k, v in self.parameters.items())
                detail = f"{detail} ({param_str})"
        elif self.action_type == "play_step":
            fname = os.path.basename(self.recording_file) if self.recording_file else "?"
            detail = f"{fname} [Step {self.step_index}]"
        elif self.action_type == "replay_trajectory":
            fname = os.path.basename(self.recording_file) if self.recording_file else "?"
            detail = fname
        elif self.action_type == "wait":
            duration = self.parameters.get("duration", 0)
            detail = f"{duration}s"
        else:
            detail = self.action_type

        dep = ""
        if self.dependency == "starts_with" and self.dependency_target:
            dep = f"  (with: #{int(self.dependency_target) + 1})" if self.dependency_target.isdigit() else f"  (with: {self.dependency_target})"
        elif self.dependency == "starts_after" and self.dependency_target:
            dep = f"  (after: #{int(self.dependency_target) + 1})" if self.dependency_target.isdigit() else f"  (after: {self.dependency_target})"
        return f"[{comp}] {detail}{dep}"


@dataclass
class Episode:
    """An episode containing ordered component actions."""
    name: str = "Episode 1"
    actions: List[ComponentAction] = field(default_factory=list)
    groups: Dict[str, ActionGroup] = field(default_factory=dict)
    created: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            'name': self.name,
            'actions': [a.to_dict() for a in self.actions],
            'created': self.created,
        }
        if self.groups:
            d['groups'] = {gid: g.to_dict() for gid, g in self.groups.items()}
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'Episode':
        actions = [ComponentAction.from_dict(a) for a in data.get('actions', [])]
        groups_raw = data.get('groups', {})
        groups = {gid: ActionGroup.from_dict(g) for gid, g in groups_raw.items()}
        return cls(
            name=data.get('name', 'Episode'),
            actions=actions,
            groups=groups,
            created=data.get('created', ''),
        )


@dataclass
class EpisodeSet:
    """A set of episodes that can be saved/loaded as a file."""
    episodes: List[Episode] = field(default_factory=list)
    version: str = "1.0"
    saved_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'episodes': [e.to_dict() for e in self.episodes],
            'version': self.version,
            'saved_at': self.saved_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'EpisodeSet':
        episodes = [Episode.from_dict(e) for e in data.get('episodes', [])]
        return cls(
            episodes=episodes,
            version=data.get('version', '1.0'),
            saved_at=data.get('saved_at', ''),
        )

    def save(self, filepath: str):
        """Save episode set to JSON file."""
        self.saved_at = datetime.now().isoformat()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Episode set saved to {filepath}")

    @classmethod
    def load(cls, filepath: str) -> 'EpisodeSet':
        """Load episode set from JSON file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        es = cls.from_dict(data)
        logger.info(f"Episode set loaded from {filepath} ({len(es.episodes)} episodes)")
        return es
