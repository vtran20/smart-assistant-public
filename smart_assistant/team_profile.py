"""Display metadata and validation of a semantic routing choice made by Codex.

This is not an intent router or an eligibility/authorization provider. A caller
must obtain actual catalog eligibility and preflight independently.
"""
from dataclasses import dataclass
from pathlib import Path
import re
from .contracts import GateResult, ValidationError
from .delivery_records import _require, _path
from .delivery_store import _read
from .state import _root_fd, _id

@dataclass(frozen=True)
class TeamRoot:
    display_name: str
    identity: str

@dataclass(frozen=True)
class TeamRole:
    capability_id: str
    display_name: str
    version: str
    state: str
    source_path: str

@dataclass(frozen=True)
class TeamProfile:
    schema_version: int
    id: str
    state: str
    root: TeamRoot
    roles: list[TeamRole]


def _shape(wire,names):
    _require(type(wire) is dict and set(wire)==set(names),'invalid_profile','$','Unexpected profile fields')


def _text(value):
    _require(type(value) is str and bool(value.strip()) and not any(ord(c)<32 for c in value),
        'invalid_profile','$','Expected nonblank text')
    return value


def _state(value):
    _require(value in ('DRAFT','ACTIVE') and type(value) is str,'invalid_profile','$','Invalid source state')
    return value


def team_from_dict(wire) -> TeamProfile:
    _shape(wire,('schema_version','id','state','root','roles'))
    _require(type(wire['schema_version']) is int and wire['schema_version']==1,
        'unsupported_version','$','Unsupported profile schema')
    _id(wire['id']); _state(wire['state'])
    root=wire['root']; _shape(root,('display_name','identity'))
    _require(root['identity']=='bootstrap-root','invalid_profile','$','Root must be bootstrap identity')
    root=TeamRoot(_text(root['display_name']),root['identity'])
    _require(type(wire['roles']) is list,'invalid_profile','$','Expected role list')
    roles=[]; seen=set()
    for role in wire['roles']:
        _shape(role,('capability_id','display_name','version','state','source_path'))
        key=_id(role['capability_id'])
        _require(key not in seen,'invalid_profile','$','Duplicate capability identity'); seen.add(key)
        version=_text(role['version'])
        _require(bool(re.fullmatch(r'\d+\.\d+\.\d+',version)),'invalid_profile','$','Expected semantic version')
        _require(type(role['source_path']) is str,'invalid_profile','$.roles.source_path',
            'Expected source path string')
        _path(role['source_path'],'$.roles.source_path')
        roles.append(TeamRole(key,_text(role['display_name']),version,_state(role['state']),role['source_path']))
    return TeamProfile(1,wire['id'],wire['state'],root,roles)


def team_to_dict(profile: TeamProfile) -> dict:
    from dataclasses import asdict
    _require(type(profile) is TeamProfile,'invalid_profile','$','Expected TeamProfile')
    wire=asdict(profile); team_from_dict(wire)
    return wire


def load_team_profile(path: Path) -> TeamProfile:
    path=Path(path).absolute()
    with _root_fd(path.parent) as root:
        return team_from_dict(_read(root,path.name))


def validate_routing_choice(profile: TeamProfile,*,domain: str,workflow_kind: str,
                            rationale: str,selected_roles: list,eligible_roles: list) -> GateResult:
    """Validate recorded choice; eligible_roles is independent observed catalog input."""
    try:
        profile=team_from_dict(team_to_dict(profile)); _text(domain); _text(rationale)
        _require(workflow_kind in ('bug','feature','document','research'),
            'invalid_routing','$','Unsupported workflow kind')
        for values in (selected_roles,eligible_roles):
            _require(type(values) is list,'invalid_routing','$','Expected identity list')
            for pair in values:
                _require(type(pair) in (tuple,list) and len(pair)==2,
                    'invalid_routing','$','Expected capability ID/version pair')
                _id(pair[0]); _text(pair[1])
            _require(len({tuple(p) for p in values})==len(values),'invalid_routing','$','Duplicate role selection')
        roles={(r.capability_id,r.version):r for r in profile.roles}
        for pair in selected_roles:
            role=roles.get(tuple(pair))
            _require(role is not None and tuple(pair) in {tuple(p) for p in eligible_roles}
                and profile.state=='ACTIVE' and role.state=='ACTIVE',
                'ineligible_role','$','Selected role must be current eligible ACTIVE source')
        return GateResult(True,[])
    except ValidationError as error:
        return GateResult(False,error.errors)
